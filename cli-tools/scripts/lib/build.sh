#!/usr/bin/env bash
# Transactional build, backup, restore, and verification logic.

ZCODE_HOME="${NDDEV_TARGET:-${ZCODE_TARGET:-$HOME/.zcode}}"
BACKUPS_DIR="${NDDEV_BACKUPS_DIR:-${ZCODE_BACKUPS_DIR:-$HOME/.zcode-backups}}"
MARKETPLACES_ROOT="$(nddev::repo_root)/zcode_tools/marketplaces"
SOURCE_DIR=""
RESTORE_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/restore.sh"

NDDEV_BACKUP_PATH=""
NDDEV_STAGE_PATH=""
NDDEV_STAGE_IDENTITY=""
NDDEV_LOCK_PATHS=()
NDDEV_ORIGINAL_TARGET_IDENTITY=""
NDDEV_ROLLBACK_BACKUP=""
NDDEV_ROLLBACK_IDENTITY=""
NDDEV_ROLLBACK_ENVELOPE=""
NDDEV_ROLLBACK_ENVELOPE_IDENTITY=""
NDDEV_REPLACED_BACKUP_HOLD=""
NDDEV_REPLACED_BACKUP_HOLD_IDENTITY=""
NDDEV_REPLACED_BACKUP_ORIGINAL=""
NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY=""
NDDEV_LIVE_SWAPPED=0
NDDEV_LIVE_RENAME_PENDING=0
NDDEV_LIVE_SOURCE_ID=""
NDDEV_LIVE_IDENTITY=""
NDDEV_FINISHING=0
NDDEV_RESTORE_SOURCE=""

nddev::prepare_paths() {
  local target backups
  target="$(nddev::validate_directory_endpoint "install target" "$ZCODE_HOME")" || return 2
  backups="$(nddev::validate_directory_endpoint "backup root" "$BACKUPS_DIR")" || return 2
  if ! nddev::validate_disjoint_roots "$target" "$backups"; then
    nddev::log "error" "target and backup roots must be disjoint"
    return 2
  fi
  ZCODE_HOME="$target"
  BACKUPS_DIR="$backups"
  export NDDEV_TARGET="$ZCODE_HOME"
  export NDDEV_BACKUPS_DIR="$BACKUPS_DIR"

  local target_parent backup_parent parent
  target_parent="$(dirname "$ZCODE_HOME")"
  backup_parent="$(dirname "$BACKUPS_DIR")"
  for parent in "$target_parent" "$backup_parent"; do
    if [ -L "$parent" ] || [ ! -d "$parent" ]; then
      nddev::log "error" "transaction parent must be an existing real directory: $parent"
      return 2
    fi
  done

  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    nddev::ensure_dir "$BACKUPS_DIR" || return 1
  fi
  if ! nddev::same_filesystem "$ZCODE_HOME" "$BACKUPS_DIR"; then
    nddev::log "error" "target and backup root must be on the same filesystem for atomic rollback"
    return 1
  fi
}

nddev::validate_marketplace() {
  local mp_dir=$1
  local required=(
    "AGENTS.md"
    "marketplace.json"
    "cli-config.template.json"
    "v2-config.template.json"
    "v2-setting.template.json"
  )
  if [ -L "$mp_dir" ]; then
    nddev::log "error" "marketplace must not be a symlink: $mp_dir"
    return 1
  fi
  nddev::assert_safe_tree "$mp_dir" || return 1
  local file
  for file in "${required[@]}"; do
    if [ ! -f "$mp_dir/$file" ] || [ -L "$mp_dir/$file" ]; then
      nddev::log "error" "marketplace '$(basename "$mp_dir")' is not self-contained: missing safe $file"
      return 1
    fi
  done
  for file in marketplace.json cli-config.template.json v2-config.template.json v2-setting.template.json; do
    nddev::validate_json "$mp_dir/$file" >/dev/null || {
      nddev::log "error" "marketplace contains invalid JSON: $file"
      return 1
    }
  done
  python3 -I - "$mp_dir" "$NDDEV_SEMVER_PATTERN" <<'PY'
import json
import os
import re
import stat
import sys

root = os.path.realpath(sys.argv[1])
semver = re.compile(sys.argv[2])
expected_marketplace = os.path.basename(root)
marketplace_name = re.compile(r"[a-z0-9][a-z0-9-]*")
plugin_name = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
with open(os.path.join(root, "marketplace.json"), encoding="utf-8") as stream:
    marketplace = json.load(stream)
if marketplace.get("name") != expected_marketplace or not marketplace_name.fullmatch(expected_marketplace):
    raise SystemExit("marketplace manifest name must match its safe directory name")
plugins = marketplace.get("plugins")
if not isinstance(plugins, list):
    raise SystemExit("marketplace plugins must be a JSON array")
seen_names = set()
seen_sources = set()
declared_directories = set()
for entry in plugins:
    if not isinstance(entry, dict):
        raise SystemExit("marketplace plugin entries must be JSON objects")
    name = entry.get("name")
    source = entry.get("source")
    version = entry.get("version")
    if not isinstance(name, str) or not plugin_name.fullmatch(name):
        raise SystemExit("marketplace plugin name is unsafe")
    expected_source = f"./plugins/{name}"
    if source != expected_source:
        raise SystemExit("marketplace plugin source must be exactly ./plugins/<name>")
    if name in seen_names or source in seen_sources:
        raise SystemExit("marketplace plugin names and sources must be unique")
    if not isinstance(version, str) or not semver.fullmatch(version):
        raise SystemExit("marketplace plugin version must be SemVer")
    seen_names.add(name)
    seen_sources.add(source)
    declared_directories.add(name)

    plugin_root = os.path.join(root, "plugins", name)
    manifest_path = os.path.join(plugin_root, ".zcode-plugin", "plugin.json")
    for path, role in ((plugin_root, "plugin directory"), (manifest_path, "plugin manifest")):
        try:
            metadata = os.lstat(path)
        except FileNotFoundError as exc:
            raise SystemExit(f"missing {role}") from exc
        expected_type = stat.S_ISDIR if role == "plugin directory" else stat.S_ISREG
        if stat.S_ISLNK(metadata.st_mode) or not expected_type(metadata.st_mode):
            raise SystemExit(f"unsafe {role}")
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise SystemExit("plugin manifest must be a JSON object")
    if manifest.get("name") != name:
        raise SystemExit("plugin manifest name must match marketplace entry")
    if manifest.get("version") != version or not semver.fullmatch(version):
        raise SystemExit("plugin manifest version must match marketplace entry")

plugins_root = os.path.join(root, "plugins")
if os.path.lexists(plugins_root):
    metadata = os.lstat(plugins_root)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SystemExit("marketplace plugins endpoint is unsafe")
    actual_directories = {
        entry.name
        for entry in os.scandir(plugins_root)
        if entry.is_dir(follow_symlinks=False)
    }
    if actual_directories != declared_directories:
        raise SystemExit("marketplace plugin directories must match declared plugins exactly")
elif declared_directories:
    raise SystemExit("marketplace declares plugins without a plugins directory")
PY
}

nddev::select_marketplace() {
  local mp_name=$1 mp_dir
  if ! printf '%s\n' "$mp_name" | grep -qE '^[a-z0-9][a-z0-9-]*$'; then
    nddev::log "error" "invalid marketplace name"
    return 2
  fi
  mp_dir="$MARKETPLACES_ROOT/$mp_name"
  if [ ! -d "$mp_dir" ] || [ -L "$mp_dir" ]; then
    nddev::log "error" "marketplace not found: $mp_name"
    nddev::log "info" "available marketplaces:"
    local directory available_name
    for directory in "$MARKETPLACES_ROOT"/*/; do
      [ -d "$directory" ] && [ ! -L "$directory" ] || continue
      available_name="$(basename "$directory")"
      printf '%s\n' "$available_name" | grep -qE '^[a-z0-9][a-z0-9-]*$' || continue
      nddev::log "info" "  - $available_name"
    done
    return 1
  fi
  nddev::validate_marketplace "$mp_dir" || return 1
  SOURCE_DIR="$mp_dir"
  nddev::log "info" "selected marketplace: $mp_name ($mp_dir)"
}

# --- Transaction lifecycle -------------------------------------------------

nddev::acquire_lock() {
  local parent name target_lock backup_lock lock
  parent="$(dirname "$ZCODE_HOME")"
  name="$(basename "$ZCODE_HOME")"
  target_lock="$parent/.${name}.nddev-lock"
  backup_lock="$BACKUPS_DIR/.nddev-backups-lock"
  nddev::assert_direct_child "$parent" "$target_lock" || return 1
  nddev::assert_direct_child "$BACKUPS_DIR" "$backup_lock" || return 1
  NDDEV_LOCK_PATHS=()

  # Canonical lexical ordering prevents deadlock when the same roots are used
  # by concurrent processes in different combinations.
  while IFS= read -r lock; do
    [ -n "$lock" ] || continue
    if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
      printf '[DRY-RUN] acquire lock %q\n' "$lock"
      NDDEV_LOCK_PATHS+=("$lock")
      continue
    fi
    if ! mkdir -m 700 "$lock" 2>/dev/null; then
      nddev::log "error" "another installer transaction holds the lock: $lock"
      nddev::log "error" "inspect owner metadata manually only after validating $lock/owner"
      nddev::release_lock
      return 1
    fi
    NDDEV_LOCK_PATHS+=("$lock")
    if ! printf 'pid=%s\nstarted_at=%s\ntarget=%s\nbackups=%s\n' \
      "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ZCODE_HOME" "$BACKUPS_DIR" > "$lock/owner" \
      || ! chmod 600 "$lock/owner"; then
      nddev::log "error" "failed to initialize transaction lock: $lock"
      nddev::release_lock
      return 1
    fi
  done < <(printf '%s\n%s\n' "$target_lock" "$backup_lock" | LC_ALL=C sort -u)
}

nddev::release_lock() {
  local index lock errors=0
  local -a remaining=()
  for ((index=${#NDDEV_LOCK_PATHS[@]} - 1; index >= 0; index--)); do
    lock="${NDDEV_LOCK_PATHS[$index]}"
    if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
      printf '[DRY-RUN] release lock %q\n' "$lock"
    elif [ -d "$lock" ] && [ ! -L "$lock" ]; then
      if ! nddev::remove_direct_child_tree "$(dirname "$lock")" "$lock"; then
        nddev::log "error" "transaction state is preserved, but lock cleanup failed: $lock"
        remaining+=("$lock")
        errors=1
      fi
    elif [ -e "$lock" ] || [ -L "$lock" ]; then
      nddev::log "error" "transaction lock endpoint changed type; inspect manually: $lock"
      remaining+=("$lock")
      errors=1
    fi
  done
  # Bash 3.2 treats an empty "${array[@]}" expansion as an unbound variable
  # under `set -u`. Reset first and copy only when an element exists.
  NDDEV_LOCK_PATHS=()
  if [ "${#remaining[@]}" -gt 0 ]; then
    NDDEV_LOCK_PATHS=("${remaining[@]}")
  fi
  return "$errors"
}

nddev::reconcile_live_rename() {
  local stage_identity="" live_identity=""
  [ "$NDDEV_LIVE_RENAME_PENDING" -eq 1 ] || return 0
  if [ -n "$NDDEV_STAGE_PATH" ] && [ -e "$NDDEV_STAGE_PATH" ] && [ ! -L "$NDDEV_STAGE_PATH" ]; then
    stage_identity="$(nddev::path_identity "$NDDEV_STAGE_PATH" directory 2>/dev/null || true)"
  fi
  if [ -e "$ZCODE_HOME" ] && [ ! -L "$ZCODE_HOME" ]; then
    live_identity="$(nddev::path_identity "$ZCODE_HOME" directory 2>/dev/null || true)"
  fi
  if [ "$live_identity" = "$NDDEV_LIVE_SOURCE_ID" ] \
    && { [ ! -e "$NDDEV_STAGE_PATH" ] && [ ! -L "$NDDEV_STAGE_PATH" ]; }; then
    NDDEV_LIVE_SWAPPED=1
    NDDEV_LIVE_RENAME_PENDING=0
    NDDEV_LIVE_IDENTITY="$NDDEV_LIVE_SOURCE_ID"
    NDDEV_STAGE_PATH=""
    return 0
  fi
  if [ "$stage_identity" = "$NDDEV_LIVE_SOURCE_ID" ]; then
    # The exclusive rename did not consume the stage. Any destination that
    # appeared belongs to another actor and must remain untouched.
    NDDEV_LIVE_SWAPPED=0
    NDDEV_LIVE_RENAME_PENDING=0
    return 0
  fi
  nddev::log "error" "live rename state is ambiguous; preserving transaction paths and locks for inspection"
  return 1
}

nddev::transaction_identity_preflight() {
  local success=$1 hold_payload="$NDDEV_REPLACED_BACKUP_HOLD/original"
  [ "${NDDEV_DRY_RUN:-1}" -eq 0 ] || return 0

  if [ "$NDDEV_LIVE_SWAPPED" -eq 1 ] \
    && ! nddev::identity_matches "$ZCODE_HOME" directory "$NDDEV_LIVE_IDENTITY"; then
    nddev::log "error" "live target identity changed; preserving recovery state and transaction locks"
    return 1
  fi
  if [ -n "$NDDEV_STAGE_PATH" ]; then
    if [ ! -e "$NDDEV_STAGE_PATH" ] && [ ! -L "$NDDEV_STAGE_PATH" ]; then
      nddev::log "error" "staging endpoint disappeared; preserving recovery state and transaction locks"
      return 1
    fi
    if ! nddev::identity_matches "$NDDEV_STAGE_PATH" directory "$NDDEV_STAGE_IDENTITY"; then
      nddev::log "error" "staging identity changed; preserving recovery state and transaction locks"
      return 1
    fi
  fi

  if [ -n "$NDDEV_ROLLBACK_BACKUP" ]; then
    if [ -e "$NDDEV_ROLLBACK_BACKUP" ] || [ -L "$NDDEV_ROLLBACK_BACKUP" ]; then
      if ! nddev::identity_matches "$NDDEV_ROLLBACK_BACKUP" directory "$NDDEV_ROLLBACK_IDENTITY"; then
        nddev::log "error" "rollback source identity changed; preserving recovery state and transaction locks"
        return 1
      fi
    elif [ "$NDDEV_LIVE_SWAPPED" -eq 0 ] \
      && nddev::identity_matches "$ZCODE_HOME" directory "$NDDEV_ROLLBACK_IDENTITY"; then
      : # The old-target move did not occur; the original endpoint is intact.
    else
      nddev::log "error" "rollback source disappeared; preserving recovery state and transaction locks"
      return 1
    fi
  fi

  if [ -n "$NDDEV_ROLLBACK_ENVELOPE" ]; then
    if [ -e "$NDDEV_ROLLBACK_ENVELOPE" ] || [ -L "$NDDEV_ROLLBACK_ENVELOPE" ]; then
      if ! nddev::identity_matches \
        "$NDDEV_ROLLBACK_ENVELOPE" directory "$NDDEV_ROLLBACK_ENVELOPE_IDENTITY"; then
        nddev::log "error" "adoption envelope identity changed; preserving recovery state and transaction locks"
        return 1
      fi
    elif [ -z "$NDDEV_ROLLBACK_ENVELOPE_IDENTITY" ]; then
      NDDEV_ROLLBACK_ENVELOPE=""
    else
      nddev::log "error" "adoption envelope disappeared; preserving recovery state and transaction locks"
      return 1
    fi
  fi

  if [ -n "$NDDEV_REPLACED_BACKUP_HOLD" ]; then
    if [ -e "$NDDEV_REPLACED_BACKUP_HOLD" ] || [ -L "$NDDEV_REPLACED_BACKUP_HOLD" ]; then
      if ! nddev::identity_matches \
        "$NDDEV_REPLACED_BACKUP_HOLD" directory "$NDDEV_REPLACED_BACKUP_HOLD_IDENTITY"; then
        nddev::log "error" "backup hold identity changed; preserving recovery state and transaction locks"
        return 1
      fi
      if [ -e "$hold_payload" ] || [ -L "$hold_payload" ]; then
        if ! nddev::identity_matches \
          "$hold_payload" directory "$NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY"; then
          nddev::log "error" "held backup identity changed; preserving recovery state and transaction locks"
          return 1
        fi
      elif ! nddev::identity_matches \
        "$NDDEV_REPLACED_BACKUP_ORIGINAL" directory "$NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY"; then
        nddev::log "error" "held backup disappeared; preserving recovery state and transaction locks"
        return 1
      fi
    elif [ "$success" -eq 1 ]; then
      # Idempotent success cleanup may be re-entered after the hold was removed
      # but before the shell cleared its in-memory paths.
      NDDEV_REPLACED_BACKUP_HOLD=""
      NDDEV_REPLACED_BACKUP_HOLD_IDENTITY=""
      NDDEV_REPLACED_BACKUP_ORIGINAL=""
      NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY=""
    else
      nddev::log "error" "backup hold disappeared; preserving recovery state and transaction locks"
      return 1
    fi
  fi
}

nddev::transaction_cleanup() {
  local success=$1 rollback_complete=0 rollback_performed=0 recovery_incomplete=0 failed_tree="" errors=0

  # A signal may arrive after the native rename completed but before the shell
  # recorded it. Reconcile by inode before any rollback or deletion decision.
  if ! nddev::reconcile_live_rename; then
    return 1
  fi
  if ! nddev::transaction_identity_preflight "$success"; then
    return 1
  fi

  if [ "$success" -ne 1 ]; then
    if [ -z "$NDDEV_ROLLBACK_BACKUP" ]; then
      if [ "$NDDEV_LIVE_SWAPPED" -eq 1 ] && [ -d "$ZCODE_HOME" ] && [ ! -L "$ZCODE_HOME" ]; then
        # A fresh install failed after its atomic rename. Restore the exact
        # pre-state (no target) by moving the new tree aside before deleting it.
        if failed_tree="$(mktemp -d "$(dirname "$ZCODE_HOME")/.nddev-failed.XXXXXX")" \
          && rmdir "$failed_tree" \
          && nddev::rename_noreplace \
            "$ZCODE_HOME" "$failed_tree" directory "$NDDEV_LIVE_IDENTITY"; then
          rollback_complete=1
          if ! nddev::remove_direct_child_tree \
            "$(dirname "$failed_tree")" "$failed_tree" "$NDDEV_LIVE_IDENTITY"; then
            nddev::log "error" "fresh-install rollback removed the live target but preserved failed state at $failed_tree"
            errors=1
          fi
        else
          errors=1
          nddev::log "error" "failed to remove the newly committed target during fresh-install rollback: $ZCODE_HOME"
        fi
      elif [ "$NDDEV_LIVE_SWAPPED" -eq 1 ] \
        && { [ -e "$ZCODE_HOME" ] || [ -L "$ZCODE_HOME" ]; }; then
        errors=1
        nddev::log "error" "fresh-install target changed type during rollback; inspect manually: $ZCODE_HOME"
      else
        # The stage was never made live, or its rename failed before visibility.
        rollback_complete=1
      fi
    elif [ -d "$NDDEV_ROLLBACK_BACKUP" ] && [ ! -L "$NDDEV_ROLLBACK_BACKUP" ]; then
      if [ "$NDDEV_LIVE_SWAPPED" -eq 1 ] && [ -d "$ZCODE_HOME" ] && [ ! -L "$ZCODE_HOME" ]; then
        if failed_tree="$(mktemp -d "$(dirname "$ZCODE_HOME")/.nddev-failed.XXXXXX")" \
          && rmdir "$failed_tree"; then
          if nddev::rename_noreplace \
            "$ZCODE_HOME" "$failed_tree" directory "$NDDEV_LIVE_IDENTITY"; then
            if nddev::rename_noreplace \
              "$NDDEV_ROLLBACK_BACKUP" "$ZCODE_HOME" directory "$NDDEV_ROLLBACK_IDENTITY"; then
              rollback_complete=1
              rollback_performed=1
              if ! nddev::remove_direct_child_tree \
                "$(dirname "$failed_tree")" "$failed_tree" "$NDDEV_LIVE_IDENTITY"; then
                nddev::log "error" "rollback restored the previous target but could not remove failed staged state: $failed_tree"
                errors=1
              fi
            else
              errors=1
              nddev::log "error" "failed to restore the previous target from $NDDEV_ROLLBACK_BACKUP"
              if [ ! -e "$ZCODE_HOME" ] && [ ! -L "$ZCODE_HOME" ]; then
                if nddev::rename_noreplace \
                  "$failed_tree" "$ZCODE_HOME" directory "$NDDEV_LIVE_IDENTITY"; then
                  nddev::log "error" "the failed new target was put back; the previous target remains recoverable at $NDDEV_ROLLBACK_BACKUP"
                else
                  nddev::log "error" "both target states require manual recovery: $failed_tree and $NDDEV_ROLLBACK_BACKUP"
                fi
              fi
            fi
          else
            errors=1
            nddev::log "error" "failed to move the new target aside for rollback: $ZCODE_HOME"
          fi
        else
          errors=1
          nddev::log "error" "failed to reserve a same-filesystem path for rollback"
        fi
      elif [ ! -e "$ZCODE_HOME" ] && [ ! -L "$ZCODE_HOME" ]; then
        if nddev::rename_noreplace \
          "$NDDEV_ROLLBACK_BACKUP" "$ZCODE_HOME" directory "$NDDEV_ROLLBACK_IDENTITY"; then
          rollback_complete=1
          rollback_performed=1
        else
          errors=1
          nddev::log "error" "failed to restore the previous target from $NDDEV_ROLLBACK_BACKUP"
        fi
      else
        errors=1
        nddev::log "error" "rollback state is ambiguous; preserve and inspect $ZCODE_HOME and $NDDEV_ROLLBACK_BACKUP"
      fi
    elif [ -d "$ZCODE_HOME" ] && [ ! -L "$ZCODE_HOME" ] \
      && [ ! -e "$NDDEV_ROLLBACK_BACKUP" ] && [ ! -L "$NDDEV_ROLLBACK_BACKUP" ]; then
      # The destructive move did not happen; the original target is intact.
      rollback_complete=1
    else
      errors=1
      nddev::log "error" "rollback source is missing or unsafe; inspect $NDDEV_ROLLBACK_BACKUP"
    fi
    if [ "$rollback_performed" -eq 1 ]; then
      nddev::log "warn" "rolled back previous target after failed transaction"
    fi
    if [ "$rollback_complete" -eq 1 ] && [ -n "$NDDEV_ROLLBACK_ENVELOPE" ]; then
      if [ -d "$NDDEV_ROLLBACK_ENVELOPE" ] && [ ! -L "$NDDEV_ROLLBACK_ENVELOPE" ]; then
        if ! nddev::remove_direct_child_tree \
          "$BACKUPS_DIR" "$NDDEV_ROLLBACK_ENVELOPE" "$NDDEV_ROLLBACK_ENVELOPE_IDENTITY"; then
          nddev::log "error" "rollback succeeded but empty adoption envelope cleanup failed: $NDDEV_ROLLBACK_ENVELOPE"
          errors=1
        fi
      elif [ -e "$NDDEV_ROLLBACK_ENVELOPE" ] || [ -L "$NDDEV_ROLLBACK_ENVELOPE" ]; then
        nddev::log "error" "adoption envelope changed type during rollback; inspect manually: $NDDEV_ROLLBACK_ENVELOPE"
        errors=1
      fi
    fi
    if [ -n "$NDDEV_REPLACED_BACKUP_HOLD" ] && [ -d "$NDDEV_REPLACED_BACKUP_HOLD/original" ] \
      && [ ! -L "$NDDEV_REPLACED_BACKUP_HOLD/original" ]; then
      if [ "$rollback_complete" -eq 1 ] \
        && [ ! -e "$NDDEV_REPLACED_BACKUP_ORIGINAL" ] && [ ! -L "$NDDEV_REPLACED_BACKUP_ORIGINAL" ]; then
        if ! nddev::rename_noreplace \
          "$NDDEV_REPLACED_BACKUP_HOLD/original" "$NDDEV_REPLACED_BACKUP_ORIGINAL" \
          directory "$NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY"; then
          nddev::log "error" "failed to restore the occupied backup slot; recovery copy remains at $NDDEV_REPLACED_BACKUP_HOLD/original"
          errors=1
          recovery_incomplete=1
        fi
      else
        nddev::log "error" "preserved occupied-slot recovery copy for manual inspection: $NDDEV_REPLACED_BACKUP_HOLD/original"
        errors=1
        recovery_incomplete=1
      fi
    fi
    [ "$rollback_complete" -eq 1 ] || recovery_incomplete=1
  fi

  if [ -n "$NDDEV_STAGE_PATH" ]; then
    if [ -d "$NDDEV_STAGE_PATH" ] && [ ! -L "$NDDEV_STAGE_PATH" ]; then
      if ! nddev::remove_direct_child_tree \
        "$(dirname "$NDDEV_STAGE_PATH")" "$NDDEV_STAGE_PATH" "$NDDEV_STAGE_IDENTITY"; then
        nddev::log "error" "failed to remove transaction staging tree; inspect manually: $NDDEV_STAGE_PATH"
        errors=1
      fi
    elif [ -e "$NDDEV_STAGE_PATH" ] || [ -L "$NDDEV_STAGE_PATH" ]; then
      nddev::log "error" "transaction staging endpoint changed type; inspect manually: $NDDEV_STAGE_PATH"
      errors=1
    fi
  fi
  if [ -n "$NDDEV_REPLACED_BACKUP_HOLD" ] && [ -d "$NDDEV_REPLACED_BACKUP_HOLD" ] \
    && [ ! -L "$NDDEV_REPLACED_BACKUP_HOLD" ]; then
    # On success this discards the replaced oldest slot. On a clean rollback the
    # original moved back above, leaving an empty hold directory. If rollback
    # itself could not complete, preserve the hold for explicit recovery.
    if [ "$success" -eq 1 ] || [ ! -e "$NDDEV_REPLACED_BACKUP_HOLD/original" ]; then
      if ! nddev::remove_direct_child_tree \
        "$BACKUPS_DIR" "$NDDEV_REPLACED_BACKUP_HOLD" "$NDDEV_REPLACED_BACKUP_HOLD_IDENTITY"; then
        nddev::log "error" "target commit succeeded, but obsolete backup hold cleanup failed: $NDDEV_REPLACED_BACKUP_HOLD"
        errors=1
      fi
    else
      nddev::log "error" "preserved recovery hold after incomplete rollback: $NDDEV_REPLACED_BACKUP_HOLD"
      errors=1
    fi
  elif [ -n "$NDDEV_REPLACED_BACKUP_HOLD" ] \
    && { [ -e "$NDDEV_REPLACED_BACKUP_HOLD" ] || [ -L "$NDDEV_REPLACED_BACKUP_HOLD" ]; }; then
    nddev::log "error" "backup hold endpoint changed type; inspect manually: $NDDEV_REPLACED_BACKUP_HOLD"
    errors=1
  fi
  if [ "$success" -ne 1 ] && [ "$recovery_incomplete" -eq 1 ] \
    && [ "${#NDDEV_LOCK_PATHS[@]}" -gt 0 ]; then
    nddev::log "error" "transaction locks are preserved because rollback recovery is incomplete"
    errors=1
  elif ! nddev::release_lock; then
    nddev::log "error" "remove preserved lock directories only after verifying no installer process is active"
    errors=1
  fi
  if [ "$success" -eq 1 ]; then
    # These paths now describe committed history, not rollback work.
    NDDEV_STAGE_PATH=""
    NDDEV_STAGE_IDENTITY=""
    NDDEV_ROLLBACK_BACKUP=""
    NDDEV_ROLLBACK_IDENTITY=""
    NDDEV_ROLLBACK_ENVELOPE=""
    NDDEV_ROLLBACK_ENVELOPE_IDENTITY=""
  else
    { [ -e "$NDDEV_STAGE_PATH" ] || [ -L "$NDDEV_STAGE_PATH" ]; } || {
      NDDEV_STAGE_PATH=""
      NDDEV_STAGE_IDENTITY=""
    }
    { [ -e "$NDDEV_ROLLBACK_BACKUP" ] || [ -L "$NDDEV_ROLLBACK_BACKUP" ]; } || {
      NDDEV_ROLLBACK_BACKUP=""
      NDDEV_ROLLBACK_IDENTITY=""
    }
    { [ -e "$NDDEV_ROLLBACK_ENVELOPE" ] || [ -L "$NDDEV_ROLLBACK_ENVELOPE" ]; } || {
      NDDEV_ROLLBACK_ENVELOPE=""
      NDDEV_ROLLBACK_ENVELOPE_IDENTITY=""
    }
  fi
  { [ -e "$NDDEV_REPLACED_BACKUP_HOLD" ] || [ -L "$NDDEV_REPLACED_BACKUP_HOLD" ]; } || {
    NDDEV_REPLACED_BACKUP_HOLD=""
    NDDEV_REPLACED_BACKUP_HOLD_IDENTITY=""
    NDDEV_REPLACED_BACKUP_ORIGINAL=""
    NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY=""
  }
  NDDEV_ORIGINAL_TARGET_IDENTITY=""
  NDDEV_LIVE_SWAPPED=0
  NDDEV_LIVE_RENAME_PENDING=0
  NDDEV_LIVE_SOURCE_ID=""
  NDDEV_LIVE_IDENTITY=""
  if [ "$errors" -ne 0 ]; then
    if [ "$success" -eq 1 ]; then
      nddev::log "error" "transaction committed safely, but housekeeping is incomplete; command reports failure"
    else
      nddev::log "error" "transaction cleanup is incomplete; inspect the recovery paths reported above"
    fi
  fi
  return "$errors"
}

nddev::transaction_abort() {
  local status=$? cleanup_mode=0
  trap - EXIT INT TERM HUP
  [ "$status" -ne 0 ] || status=1
  [ "$NDDEV_FINISHING" -eq 1 ] && cleanup_mode=1
  nddev::transaction_cleanup "$cleanup_mode" || true
  exit "$status"
}

nddev::begin_transaction() {
  nddev::acquire_lock || return 1
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    trap 'nddev::transaction_abort' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
  fi
}

nddev::finish_transaction() {
  local status
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    # Keep signal/EXIT traps active until idempotent committed-state cleanup is
    # complete. A signal in this window re-enters cleanup in success mode and
    # must never roll back the verified live tree.
    NDDEV_FINISHING=1
  fi
  nddev::transaction_cleanup 1
  status=$?
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    NDDEV_FINISHING=0
    trap - EXIT INT TERM HUP
  fi
  return "$status"
}

nddev::create_stage() {
  local parent name
  parent="$(dirname "$ZCODE_HOME")"
  name="$(basename "$ZCODE_HOME")"
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    NDDEV_STAGE_PATH="$parent/.${name}.stage.PLAN"
    NDDEV_STAGE_IDENTITY="plan"
    printf '[DRY-RUN] create same-filesystem staging directory %q (0700)\n' "$NDDEV_STAGE_PATH"
    return 0
  fi
  NDDEV_STAGE_PATH="$(mktemp -d "$parent/.${name}.stage.XXXXXX")" || return 1
  nddev::assert_direct_child "$parent" "$NDDEV_STAGE_PATH" || return 1
  chmod 700 "$NDDEV_STAGE_PATH" || return 1
  NDDEV_STAGE_IDENTITY="$(nddev::path_identity "$NDDEV_STAGE_PATH" directory)" || return 1
}

nddev::find_slot_entry() {
  local slot=$1
  python3 -I - "$BACKUPS_DIR" "$slot" "$NDDEV_SEMVER_PATTERN" <<'PY'
import os
import re
import sys

root, slot, semver = sys.argv[1:]
pattern = re.compile(rf"^([0-9])-(?:unmanaged|{semver})-old\.zcode$")
matches = []
if os.path.isdir(root):
    for entry in os.scandir(root):
        match = pattern.fullmatch(entry.name)
        if not match:
            if re.fullmatch(r"[0-9]-.*-old\.zcode", entry.name):
                raise SystemExit("invalid backup slot name")
            if entry.name.startswith(".slot-") and ".hold." in entry.name:
                raise SystemExit("stale backup recovery hold requires attention")
            continue
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            raise SystemExit("unsafe backup slot entry")
        if match.group(1) == slot:
            matches.append(entry.path)
if len(matches) > 1:
    raise SystemExit(f"duplicate backup slot: {slot}")
if matches:
    print(matches[0])
PY
}

# Reserve a backup destination without destroying the current slot occupant.
# The old occupant is held until commit succeeds and restored on failure.
nddev::prepare_backup_destination() {
  local version=$1 slot name destination existing hold existing_identity
  slot="$(nddev::backup_slot)" || return 1
  name="$(nddev::backup_name "$version" "$slot")" || return 1
  destination="$BACKUPS_DIR/$name"
  nddev::assert_direct_child "$BACKUPS_DIR" "$destination" || return 1
  existing="$(nddev::find_slot_entry "$slot")" || return 1

  NDDEV_BACKUP_PATH="$destination"
  if [ -z "$existing" ]; then
    return 0
  fi
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] hold occupied backup slot %q until commit\n' "$existing"
    return 0
  fi
  existing_identity="$(nddev::path_identity "$existing" directory)" || return 1
  hold="$(mktemp -d "$BACKUPS_DIR/.slot-${slot}.hold.XXXXXX")" || return 1
  NDDEV_REPLACED_BACKUP_HOLD="$hold"
  NDDEV_REPLACED_BACKUP_HOLD_IDENTITY="$(nddev::path_identity "$hold" directory)" || return 1
  NDDEV_REPLACED_BACKUP_ORIGINAL="$existing"
  NDDEV_REPLACED_BACKUP_ORIGINAL_IDENTITY="$existing_identity"
  nddev::assert_direct_child "$BACKUPS_DIR" "$hold" || return 1
  chmod 700 "$hold" || return 1
  nddev::rename_noreplace "$existing" "$hold/original" directory "$existing_identity" || return 1
}

nddev::write_adoption_envelope() {
  local envelope=$1 original_target=$2 build_version created_at
  build_version="$(nddev::build_version)" || return 1
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 -I - "$envelope/NDDEV-BACKUP.json" "$original_target" "$build_version" "$created_at" <<'PY'
import json
import os
import sys
import tempfile

path, original_target, build_version, created_at = sys.argv[1:]
payload = {
    "schema": 1,
    "type": "adopted-unmanaged",
    "original_target": original_target,
    "created_at": created_at,
    "installer_build": build_version,
    "payload": "payload",
}
fd, temporary = tempfile.mkstemp(prefix=".nddev-envelope.", dir=os.path.dirname(path), text=True)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}

# Validate a typed adopted-state envelope and print its contained payload path.
nddev::adoption_payload() {
  local envelope=$1 requested_target=$2 allow_relocation=${3:-0}
  python3 -I - "$envelope" "$requested_target" "$allow_relocation" "$NDDEV_SEMVER_PATTERN" <<'PY'
import datetime as dt
import json
import os
import re
import sys

envelope, requested_target, allow_relocation, semver_pattern = sys.argv[1:]
envelope = os.path.realpath(envelope)
requested_target = os.path.realpath(requested_target)
if not re.fullmatch(r"[0-9]-unmanaged-old\.zcode", os.path.basename(envelope)):
    raise SystemExit("adopted backup envelope has an invalid slot name")
marker = os.path.join(envelope, "NDDEV-BACKUP.json")
if os.path.islink(marker):
    raise SystemExit("adopted backup marker must not be a symlink")
try:
    with open(marker, encoding="utf-8") as stream:
        data = json.load(stream)
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid adopted backup marker: {exc}")
if not isinstance(data, dict) or data.get("schema") != 1 or data.get("type") != "adopted-unmanaged":
    raise SystemExit("unsupported adopted backup marker")
if data.get("payload") != "payload":
    raise SystemExit("adopted backup payload name must be exactly 'payload'")
original = data.get("original_target")
if (
    not isinstance(original, str)
    or any(ord(char) < 32 or ord(char) == 127 for char in original)
    or not os.path.isabs(original)
    or os.path.realpath(original) != original
    or original == "/"
):
    raise SystemExit("adopted backup original_target is not canonical")
if allow_relocation != "1" and original != requested_target:
    raise SystemExit("adopted backup belongs to a different target; explicit relocation is required")
build = data.get("installer_build")
semver = re.compile(semver_pattern)
if not isinstance(build, str) or not semver.fullmatch(build):
    raise SystemExit("adopted backup installer_build is invalid")
created_at = data.get("created_at")
try:
    parsed = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
except (AttributeError, ValueError) as exc:
    raise SystemExit("adopted backup created_at is invalid") from exc
if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
    raise SystemExit("adopted backup created_at must be UTC")
payload = os.path.realpath(os.path.join(envelope, "payload"))
if os.path.dirname(payload) != envelope or not os.path.isdir(payload) or os.path.islink(payload):
    raise SystemExit("adopted backup payload escapes its envelope or is unsafe")
print(payload)
PY
}

nddev::commit_stage() {
  local current_version=$1 had_target=$2
  nddev::section "Commit transaction"
  if [ "$had_target" -eq 1 ]; then
    if ! nddev::identity_matches "$ZCODE_HOME" directory "$NDDEV_ORIGINAL_TARGET_IDENTITY"; then
      nddev::log "error" "install target identity changed before commit"
      return 1
    fi
    nddev::prepare_backup_destination "$current_version" || return 1
    nddev::log "info" "backup target: $NDDEV_BACKUP_PATH"
    if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
      if [ "$current_version" = "unmanaged" ]; then
        printf '[DRY-RUN] create typed adopted-unmanaged envelope %q and move target into payload/\n' "$NDDEV_BACKUP_PATH"
      else
        printf '[DRY-RUN] exclusive atomic rename %q %q\n' "$ZCODE_HOME" "$NDDEV_BACKUP_PATH"
      fi
    else
      if [ "$current_version" = "unmanaged" ]; then
        NDDEV_ROLLBACK_ENVELOPE="$NDDEV_BACKUP_PATH"
        mkdir -m 700 "$NDDEV_BACKUP_PATH" || return
        NDDEV_ROLLBACK_ENVELOPE_IDENTITY="$(nddev::path_identity "$NDDEV_BACKUP_PATH" directory)" || return 1
        NDDEV_ROLLBACK_BACKUP="$NDDEV_BACKUP_PATH/payload"
        NDDEV_ROLLBACK_IDENTITY="$NDDEV_ORIGINAL_TARGET_IDENTITY"
        nddev::rename_noreplace \
          "$ZCODE_HOME" "$NDDEV_BACKUP_PATH/payload" directory "$NDDEV_ROLLBACK_IDENTITY" || return
        nddev::write_adoption_envelope "$NDDEV_BACKUP_PATH" "$ZCODE_HOME" || return
      else
        NDDEV_ROLLBACK_BACKUP="$NDDEV_BACKUP_PATH"
        NDDEV_ROLLBACK_IDENTITY="$NDDEV_ORIGINAL_TARGET_IDENTITY"
        nddev::rename_noreplace \
          "$ZCODE_HOME" "$NDDEV_BACKUP_PATH" directory "$NDDEV_ROLLBACK_IDENTITY" || return
      fi
      if ! nddev::identity_matches "$NDDEV_ROLLBACK_BACKUP" directory "$NDDEV_ROLLBACK_IDENTITY"; then
        nddev::log "error" "rollback source identity changed after backup move"
        return 1
      fi
      nddev::normalize_tree_permissions "$NDDEV_BACKUP_PATH" || return
      touch "$NDDEV_BACKUP_PATH" || return
      nddev::sync_directory "$NDDEV_BACKUP_PATH" || return
      nddev::sync_directory "$BACKUPS_DIR" || return
    fi
  else
    NDDEV_BACKUP_PATH=""
  fi

  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] atomic rename %q %q\n' "$NDDEV_STAGE_PATH" "$ZCODE_HOME"
  else
    if ! nddev::identity_matches "$NDDEV_STAGE_PATH" directory "$NDDEV_STAGE_IDENTITY"; then
      nddev::log "error" "staging directory identity changed before commit"
      return 1
    fi
    NDDEV_LIVE_SOURCE_ID="$NDDEV_STAGE_IDENTITY"
    NDDEV_LIVE_RENAME_PENDING=1
    if ! nddev::rename_noreplace \
      "$NDDEV_STAGE_PATH" "$ZCODE_HOME" directory "$NDDEV_LIVE_SOURCE_ID"; then
      nddev::reconcile_live_rename || return 1
      return 1
    fi
    NDDEV_LIVE_SWAPPED=1
    NDDEV_LIVE_RENAME_PENDING=0
    NDDEV_LIVE_IDENTITY="$NDDEV_STAGE_IDENTITY"
    NDDEV_STAGE_PATH=""
    nddev::sync_directory "$(dirname "$ZCODE_HOME")" || return
  fi
}

# --- Build -----------------------------------------------------------------

nddev::create_runtime_dirs() {
  local target=$1 directory
  local dirs=(
    "$target/cli/agents"
    "$target/cli/artifacts"
    "$target/cli/db"
    "$target/cli/log"
    "$target/cli/plugins/cache"
    "$target/cli/plugins/data"
    "$target/v2/logs"
    "$target/v2/crash"
  )
  for directory in "${dirs[@]}"; do
    nddev::ensure_dir "$directory" || return 1
  done
}

nddev::merge_hooks() {
  local config_path=$1 hooks_path=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] merge hooks %q -> %q\n' "$hooks_path" "$config_path"
    return 0
  fi
  python3 -I - "$config_path" "$hooks_path" <<'PY'
import json
import os
import sys
import tempfile

config_path, hooks_path = sys.argv[1:]
with open(config_path, encoding="utf-8") as stream:
    config = json.load(stream)
with open(hooks_path, encoding="utf-8") as stream:
    hooks = json.load(stream)
if not isinstance(config, dict) or not isinstance(hooks, dict):
    raise SystemExit("hook merge inputs must be JSON objects")
hooks.pop("_comment", None)
events = config.setdefault("hooks", {}).setdefault("events", {})
config["hooks"].setdefault("enabled", True)
for event, entries in hooks.items():
    if not isinstance(entries, list):
        raise SystemExit(f"hook event must contain a list: {event}")
    existing = events.setdefault(event, [])
    if not isinstance(existing, list):
        raise SystemExit(f"configured hook event is not a list: {event}")
    existing.extend(entries)
fd, temporary = tempfile.mkstemp(prefix=".nddev-hooks.", dir=os.path.dirname(config_path), text=True)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, config_path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}

nddev::merge_mcp() {
  local config_path=$1 mcp_path=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] merge rendered MCP %q -> %q\n' "$mcp_path" "$config_path"
    return 0
  fi
  python3 -I - "$config_path" "$mcp_path" <<'PY'
import json
import os
import sys
import tempfile

config_path, mcp_path = sys.argv[1:]
with open(config_path, encoding="utf-8") as stream:
    config = json.load(stream)
with open(mcp_path, encoding="utf-8") as stream:
    mcp = json.load(stream)
if not isinstance(config, dict) or not isinstance(mcp, dict):
    raise SystemExit("MCP merge inputs must be JSON objects")
servers = mcp.get("mcpServers", {})
if not isinstance(servers, dict):
    raise SystemExit("mcpServers must be a JSON object")
configured = config.setdefault("mcp", {}).setdefault("servers", {})
if not isinstance(configured, dict):
    raise SystemExit("mcp.servers must be a JSON object")
configured.update(servers)
fd, temporary = tempfile.mkstemp(prefix=".nddev-mcp.", dir=os.path.dirname(config_path), text=True)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, config_path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}

nddev::validate_plan_configs() {
  python3 -I - "$SOURCE_DIR" <<'PY' || return 1
import json
import os
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
placeholder = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def load(name, *, optional=False):
    path = root / name
    if optional and not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"missing safe JSON plan input: {name}")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise SystemExit(f"JSON plan input must contain an object: {name}")
    value.pop("_comment", None)
    return value

def substitute(value):
    if isinstance(value, str):
        def replace(match):
            replacement = os.environ.get(match.group(1))
            return replacement if replacement not in (None, "") else match.group(0)
        return placeholder.sub(replace, value)
    if isinstance(value, list):
        return [substitute(item) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item) for key, item in value.items()}
    return value

def child_path(path, key):
    return f"{path}[{key!r}]"

def unresolved_keys(value, path):
    failures = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(unresolved_keys(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            location = child_path(path, key)
            if isinstance(key, str) and placeholder.search(key):
                failures.append(f"{location}.<placeholder-key>")
            failures.extend(unresolved_keys(item, location))
    return failures

def unresolved_values(value, path):
    failures = []
    if isinstance(value, str) and placeholder.search(value):
        failures.append(path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(unresolved_values(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            failures.extend(unresolved_values(item, child_path(path, key)))
    return failures

cli = substitute(load("cli-config.template.json"))
providers = substitute(load("v2-config.template.json"))
settings = substitute(load("v2-setting.template.json"))

hooks = load("hooks.json", optional=True)
if hooks is not None:
    hooks = substitute(hooks)
    events = cli.setdefault("hooks", {}).setdefault("events", {})
    if not isinstance(events, dict):
        raise SystemExit("hooks.events must be a JSON object")
    cli["hooks"].setdefault("enabled", True)
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise SystemExit(f"hook event must contain a list: {event}")
        existing = events.setdefault(event, [])
        if not isinstance(existing, list):
            raise SystemExit(f"configured hook event is not a list: {event}")
        existing.extend(entries)

mcp = load("mcp.json", optional=True)
if mcp is not None:
    mcp = substitute(mcp)
    servers = mcp.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise SystemExit("mcpServers must be a JSON object")
    configured = cli.setdefault("mcp", {}).setdefault("servers", {})
    if not isinstance(configured, dict):
        raise SystemExit("mcp.servers must be a JSON object")
    configured.update(servers)

failures = []
for root_name, value in (
    ("provider-config", providers),
    ("setting", settings),
    ("cli", cli),
):
    failures.extend(unresolved_keys(value, root_name))

for key, value in providers.items():
    if key != "provider":
        failures.extend(unresolved_values(value, child_path("provider-config", key)))
    elif isinstance(value, dict):
        for name, provider in value.items():
            if isinstance(provider, dict) and provider.get("enabled") is False:
                continue
            failures.extend(unresolved_values(provider, child_path("provider", name)))
    else:
        failures.extend(unresolved_values(value, child_path("provider-config", key)))

failures.extend(unresolved_values(settings, "setting"))

for key, value in cli.items():
    if key != "mcp":
        failures.extend(unresolved_values(value, child_path("cli", key)))
    elif isinstance(value, dict):
        for mcp_key, mcp_value in value.items():
            if mcp_key != "servers":
                failures.extend(unresolved_values(mcp_value, child_path("mcp", mcp_key)))
            elif isinstance(mcp_value, dict):
                for name, server in mcp_value.items():
                    if isinstance(server, dict) and server.get("enabled") is False:
                        continue
                    failures.extend(unresolved_values(server, child_path("mcp.servers", name)))
            else:
                failures.extend(unresolved_values(mcp_value, child_path("mcp", mcp_key)))
    else:
        failures.extend(unresolved_values(value, child_path("cli", key)))

if failures:
    raise SystemExit("unresolved required placeholder(s): " + ", ".join(failures))
PY
  nddev::log "ok" "plan config render, merge, and active-placeholder contracts passed"
}

nddev::render_configs() {
  local target=$1 rendered_mcp rendered_hooks
  nddev::section "Render config templates"
  nddev::render_template "$SOURCE_DIR/cli-config.template.json" "$target/cli/config.json" || return 1

  if [ -f "$SOURCE_DIR/hooks.json" ]; then
    rendered_hooks="$target/cli/.hooks.rendered.json"
    nddev::render_template "$SOURCE_DIR/hooks.json" "$rendered_hooks" || return 1
    nddev::merge_hooks "$target/cli/config.json" "$rendered_hooks" || return 1
    [ "${NDDEV_DRY_RUN:-1}" -eq 1 ] || rm -f "$rendered_hooks" || return 1
  fi
  if [ -f "$SOURCE_DIR/mcp.json" ]; then
    rendered_mcp="$target/cli/.mcp.rendered.json"
    nddev::render_template "$SOURCE_DIR/mcp.json" "$rendered_mcp" || return 1
    nddev::merge_mcp "$target/cli/config.json" "$rendered_mcp" || return 1
    [ "${NDDEV_DRY_RUN:-1}" -eq 1 ] || rm -f "$rendered_mcp" || return 1
  fi

  nddev::render_template "$SOURCE_DIR/v2-config.template.json" "$target/v2/config.json" || return 1
  nddev::render_template "$SOURCE_DIR/v2-setting.template.json" "$target/v2/setting.json" || return 1
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    nddev::validate_required_placeholders \
      "$target/cli/config.json" "$target/v2/config.json" "$target/v2/setting.json" || return 1
  else
    nddev::validate_plan_configs || return 1
  fi
}

nddev::render_env() {
  local target=$1 src_env
  src_env="$(nddev::repo_root)/build/.env"
  if [ ! -e "$src_env" ] && [ ! -L "$src_env" ]; then
    if [ "${NDDEV_ENV_DIGEST:-}" != "absent" ]; then
      nddev::log "error" "build/.env disappeared after environment loading"
      return 1
    fi
    nddev::log "info" "no build/.env — runtime tools must receive secrets from the environment"
    return 0
  fi
  if [ -z "${NDDEV_ENV_DIGEST:-}" ] || [ "$NDDEV_ENV_DIGEST" = "absent" ]; then
    nddev::log "error" "build/.env appeared after environment loading"
    return 1
  fi
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    nddev::parse_env_file "$src_env" "$NDDEV_ENV_DIGEST" >/dev/null || return 1
    printf '[DRY-RUN] install private env %q -> %q (0600)\n' "$src_env" "$target/.env"
    return 0
  fi
  nddev::parse_env_file "$src_env" "$NDDEV_ENV_DIGEST" "$target/.env" >/dev/null || return 1
}

nddev::copy_source_tree() {
  local target=$1 mp_name directory
  mp_name="$(basename "$SOURCE_DIR")"
  nddev::section "Copy source tree (marketplace: $mp_name)"
  nddev::copy "$SOURCE_DIR/AGENTS.md" "$target/AGENTS.md" || return 1
  nddev::ensure_dir "$target/marketplaces" || return 1
  nddev::copy "$SOURCE_DIR" "$target/marketplaces/$mp_name" || return 1
  for directory in skills commands agents; do
    if [ -d "$SOURCE_DIR/$directory" ]; then
      nddev::ensure_dir "$target/$directory" || return 1
      nddev::copy "$SOURCE_DIR/$directory/." "$target/$directory/" || return 1
    fi
  done
}

nddev::build_clean() {
  local target=$1
  nddev::section "Build isolated staging tree"
  nddev::ensure_dir "$target" || return 1
  nddev::ensure_dir "$target/cli" || return 1
  nddev::ensure_dir "$target/v2" || return 1
  nddev::create_runtime_dirs "$target" || return 1
  nddev::copy_source_tree "$target" || return 1
  nddev::render_configs "$target" || return 1
  nddev::render_env "$target" || return 1
}

nddev::restore_runtime() {
  local source=$1 target=$2 managed=${3:-managed}
  if [ ! -d "$source" ]; then
    nddev::log "info" "no existing state to adopt (fresh install)"
    return 0
  fi
  nddev::section "Restore selected runtime state into staging"
  if [ "$managed" = "unmanaged" ]; then
    NDDEV_ALLOW_UNMANAGED_BACKUP=1 NDDEV_BACKUP="$source" NDDEV_TARGET="$target" "$RESTORE_SCRIPT"
  else
    NDDEV_ALLOW_UNMANAGED_BACKUP=0 NDDEV_BACKUP="$source" NDDEV_TARGET="$target" "$RESTORE_SCRIPT"
  fi
}

# --- Verification ----------------------------------------------------------

nddev::verify_managed_tree() {
  local target=$1 errors=0
  if [ ! -d "$target" ] || [ -L "$target" ]; then
    nddev::log "missing" "managed tree is not a real directory: $target"
    return 1
  fi
  nddev::assert_safe_tree "$target" || errors=$((errors + 1))
  nddev::stamp_version "$target" >/dev/null || {
    nddev::log "missing" "BUILD-VERSION does not satisfy the managed schema"
    errors=$((errors + 1))
  }
  local path
  for path in cli/config.json v2/config.json v2/setting.json; do
    if [ ! -f "$target/$path" ] || ! nddev::validate_json "$target/$path" >/dev/null 2>&1; then
      nddev::log "missing" "$path is missing or invalid"
      errors=$((errors + 1))
    fi
  done
  if [ "$errors" -eq 0 ]; then
    nddev::validate_required_placeholders \
      "$target/cli/config.json" "$target/v2/config.json" "$target/v2/setting.json" \
      || errors=$((errors + 1))
  fi
  [ "$errors" -eq 0 ]
}

nddev::verify_build() {
  local target=$1 mp_name errors=0
  mp_name="$(basename "$SOURCE_DIR")"
  nddev::section "Verify staged build"
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    nddev::log "ok" "all checks passed (planned staged verification)"
    return 0
  fi
  nddev::verify_managed_tree "$target" || errors=$((errors + 1))
  if [ ! -f "$target/AGENTS.md" ]; then
    nddev::log "missing" "AGENTS.md not found"
    errors=$((errors + 1))
  fi
  local manifest="$target/marketplaces/$mp_name/marketplace.json"
  if [ ! -f "$manifest" ] || ! nddev::validate_json "$manifest" >/dev/null 2>&1; then
    nddev::log "missing" "$mp_name/marketplace.json is missing or invalid"
    errors=$((errors + 1))
  fi
  nddev::normalize_tree_permissions "$target" || errors=$((errors + 1))
  python3 -I - "$target" <<'PY' || errors=$((errors + 1))
import os
import stat
import sys

root = sys.argv[1]
if stat.S_IMODE(os.stat(root).st_mode) != 0o700:
    raise SystemExit("target root must be 0700")
for relative in ("BUILD-VERSION", "cli/config.json", "v2/config.json"):
    path = os.path.join(root, relative)
    if stat.S_IMODE(os.stat(path).st_mode) != 0o600:
        raise SystemExit(f"sensitive config must be 0600: {relative}")
PY
  nddev::sync_tree "$target" || errors=$((errors + 1))
  if [ "$errors" -gt 0 ]; then
    nddev::log "error" "$errors staged verification error(s)"
    return 1
  fi
  nddev::log "ok" "staged build is complete, private, and internally consistent"
}

# --- Public orchestration --------------------------------------------------

nddev::install_sequence() {
  local platform=$1 current_version had_target=0 adoption_mode=managed
  nddev::prepare_paths || return
  nddev::log "info" "target: $ZCODE_HOME"
  nddev::begin_transaction || return
  if [ -e "$ZCODE_HOME" ]; then
    had_target=1
    current_version="$(nddev::current_version)" || return 1
    NDDEV_ORIGINAL_TARGET_IDENTITY="$(nddev::path_identity "$ZCODE_HOME" directory)" || return 1
    if [ "$current_version" = "unmanaged" ]; then
      if [ "${NDDEV_ADOPT_UNMANAGED:-0}" != "1" ]; then
        nddev::log "error" "refusing to replace an unstamped target; use --adopt-unmanaged with an explicit --target"
        return 1
      fi
      adoption_mode=unmanaged
    elif [ "${NDDEV_ADOPT_UNMANAGED:-0}" = "1" ]; then
      nddev::log "error" "--adopt-unmanaged is only valid for an existing unstamped target"
      return 2
    fi
  else
    current_version="unmanaged"
    if [ "${NDDEV_ADOPT_UNMANAGED:-0}" = "1" ]; then
      nddev::log "error" "--adopt-unmanaged requires an existing unstamped target"
      return 2
    fi
  fi

  nddev::create_stage || return
  nddev::check_runtime_version || return
  nddev::build_clean "$NDDEV_STAGE_PATH" || return
  nddev::write_version_stamp "$NDDEV_STAGE_PATH" "$platform" || return
  if [ "$had_target" -eq 1 ]; then
    nddev::restore_runtime "$ZCODE_HOME" "$NDDEV_STAGE_PATH" "$adoption_mode" || return
  fi
  nddev::verify_build "$NDDEV_STAGE_PATH" || return
  nddev::commit_stage "$current_version" "$had_target" || return
  nddev::finish_transaction || return
}

# Move a strictly managed target into a contained backup slot. This is the
# complete remove operation; no follow-up rm -rf is required.
nddev::remove_managed_target() {
  local current_version
  nddev::prepare_paths || return
  nddev::log "info" "target: $ZCODE_HOME"
  nddev::begin_transaction || return
  if [ ! -e "$ZCODE_HOME" ]; then
    nddev::log "info" "nothing to remove: $ZCODE_HOME does not exist"
    nddev::finish_transaction || return
    return 0
  fi
  current_version="$(nddev::stamp_version "$ZCODE_HOME")" || {
    nddev::log "error" "refusing to remove: target has no valid managed BUILD-VERSION"
    return 1
  }
  nddev::assert_safe_tree "$ZCODE_HOME" || {
    nddev::log "error" "refusing to remove a managed tree containing unsafe filesystem entries"
    return 1
  }
  NDDEV_ORIGINAL_TARGET_IDENTITY="$(nddev::path_identity "$ZCODE_HOME" directory)" || return 1
  nddev::prepare_backup_destination "$current_version" || return
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] atomic move %q %q\n' "$ZCODE_HOME" "$NDDEV_BACKUP_PATH"
  else
    NDDEV_ROLLBACK_BACKUP="$NDDEV_BACKUP_PATH"
    NDDEV_ROLLBACK_IDENTITY="$NDDEV_ORIGINAL_TARGET_IDENTITY"
    nddev::rename_noreplace \
      "$ZCODE_HOME" "$NDDEV_BACKUP_PATH" directory "$NDDEV_ROLLBACK_IDENTITY" || return
    if ! nddev::identity_matches "$NDDEV_ROLLBACK_BACKUP" directory "$NDDEV_ROLLBACK_IDENTITY"; then
      nddev::log "error" "backup identity changed after remove move"
      return 1
    fi
    nddev::normalize_tree_permissions "$NDDEV_BACKUP_PATH" || return
    touch "$NDDEV_BACKUP_PATH" || return
    nddev::sync_directory "$NDDEV_BACKUP_PATH" || return
    nddev::sync_directory "$BACKUPS_DIR" || return
  fi
  nddev::finish_transaction || return
}

# Resolve and restore a slot while holding both target and backup-pool locks.
nddev::restore_backup_slot() {
  local slot=$1 source current_version="" had_target=0 restore_kind="managed" payload
  nddev::prepare_paths || return
  nddev::begin_transaction || return
  source="$(nddev::find_slot_entry "$slot")" || return 1
  if [ -z "$source" ] || [ ! -d "$source" ] || [ -L "$source" ]; then
    nddev::log "error" "no safe backup found in slot $slot"
    return 1
  fi
  source="$(nddev::canonical_path "$source")" || return 2
  nddev::assert_direct_child "$BACKUPS_DIR" "$source" || return 1
  if [ ! -d "$source" ] || [ -L "$source" ]; then
    nddev::log "error" "restore source must be a real backup directory: $source"
    return 1
  fi
  nddev::assert_safe_tree "$source" || return 1
  if nddev::stamp_version "$source" >/dev/null 2>&1; then
    if [ "${NDDEV_ALLOW_TARGET_RELOCATION:-0}" = "1" ]; then
      nddev::log "error" "--allow-target-relocation applies only to adopted-unmanaged envelopes"
      return 2
    fi
    payload="$source"
  else
    restore_kind="adopted-unmanaged"
    payload="$(nddev::adoption_payload "$source" "$ZCODE_HOME" "${NDDEV_ALLOW_TARGET_RELOCATION:-0}")" || {
      nddev::log "error" "restore source is neither a managed backup nor a valid adopted-state envelope"
      return 1
    }
    nddev::assert_safe_tree "$payload" || return 1
    if [ -e "$payload/BUILD-VERSION" ] || [ -L "$payload/BUILD-VERSION" ]; then
      nddev::log "error" "adopted-state payload must remain unstamped"
      return 1
    fi
  fi
  if [ "$restore_kind" = "managed" ]; then
    nddev::verify_managed_tree "$payload" || {
      nddev::log "error" "managed backup does not satisfy the full restore contract"
      return 1
    }
  fi
  if [ -e "$ZCODE_HOME" ]; then
    had_target=1
    current_version="$(nddev::stamp_version "$ZCODE_HOME")" || {
      nddev::log "error" "refusing to restore: target has no valid managed BUILD-VERSION"
      return 1
    }
    nddev::assert_safe_tree "$ZCODE_HOME" || {
      nddev::log "error" "refusing to replace a managed target containing unsafe filesystem entries"
      return 1
    }
    NDDEV_ORIGINAL_TARGET_IDENTITY="$(nddev::path_identity "$ZCODE_HOME" directory)" || return 1
  fi

  # Read by install.sh after this sourced function returns.
  # shellcheck disable=SC2034
  NDDEV_RESTORE_SOURCE="$source"
  nddev::section "Restore from backup slot $slot"
  nddev::log "info" "backup: $source"
  nddev::log "info" "target: $ZCODE_HOME"
  nddev::log "info" "mode: $([ "${NDDEV_DRY_RUN:-1}" -eq 0 ] && echo APPLY || echo 'PLAN (dry-run)')"

  nddev::create_stage || return
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] copy %s payload %q -> %q\n' "$restore_kind" "$payload" "$NDDEV_STAGE_PATH"
    if [ "$restore_kind" = "managed" ]; then
      printf '[DRY-RUN] validate managed restore staging tree and BUILD-VERSION\n'
    else
      printf '[DRY-RUN] validate adopted-unmanaged payload remains unstamped\n'
    fi
  else
    cp -R "$payload/." "$NDDEV_STAGE_PATH/" || return
    nddev::normalize_tree_permissions "$NDDEV_STAGE_PATH" || return
    nddev::sync_tree "$NDDEV_STAGE_PATH" || return
    if [ "$restore_kind" = "managed" ]; then
      nddev::verify_managed_tree "$NDDEV_STAGE_PATH" || return
    elif [ -e "$NDDEV_STAGE_PATH/BUILD-VERSION" ]; then
      nddev::log "error" "adopted-state payload unexpectedly contains BUILD-VERSION"
      return 1
    fi
  fi
  nddev::commit_stage "${current_version:-unmanaged}" "$had_target" || return
  nddev::finish_transaction || return
}
