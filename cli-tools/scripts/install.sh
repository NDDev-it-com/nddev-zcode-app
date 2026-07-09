#!/usr/bin/env bash
#
# nddev-zcode-app installer — manages a complete, version-stamped ~/.zcode
# built from ONE selected marketplace. Supports install, update, switch, and
# remove on macOS (desktop) or Ubuntu (desktop/server).
#
# Usage:
#   cli-tools/scripts/install.sh <command> [options]
#
# Commands:
#   install (default)   Build ~/.zcode from a marketplace (backup → build → restore).
#   remove              Back up and delete the installed ~/.zcode.
#   list                List available marketplaces.
#
# Each marketplace is a self-contained setup (its own AGENTS.md, config
# templates, skills/commands/agents, and plugins). The installer selects one
# and builds a clean ~/.zcode entirely from it.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

# shellcheck source=lib/common.sh
. "$LIB_DIR/common.sh"
# shellcheck source=lib/version.sh
. "$LIB_DIR/version.sh"

# Load build/.env early (target dir + secrets). Env vars already set win.
nddev::load_env

# ─── Defaults ────────────────────────────────────────────────────────────
COMMAND="install"
APPLY=0
PLATFORM="auto"
MARKETPLACE=""
TARGET_OVERRIDE=""
SLOT=""

usage() {
  cat <<'EOF'
Usage: cli-tools/scripts/install.sh [bootstrap|install|remove|restore|list] [options]

Commands:
  bootstrap             Download and install the ZCode desktop app + CLI (from zero).
  install (default)     Build ~/.zcode from a marketplace.
  remove                Back up and delete the installed ~/.zcode.
  restore               Restore ~/.zcode from a backup slot (0-9).
  list                  List available marketplaces (and backups with --backups).

Options (bootstrap):
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute the download + install (default is --plan).

Options (install):
  --marketplace <name>      Which marketplace/setup to build from (required for install).
  --target <dir>            Install directory (default: ~/.zcode, or ZCODE_TARGET in .env).
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute (default is --plan / dry-run).
  --plan | --dry-run        Print actions without writing (default).

Options (remove):
  --target <dir>            Directory to remove (default: ~/.zcode, or ZCODE_TARGET in .env).
  --apply                   Actually delete (default is --plan).
  --keep-backup <dir>       Move the target here instead of the default backups dir.

Options (restore):
  --slot <N>                Backup slot to restore (0-9). Required.
  --target <dir>            Restore destination (default: ~/.zcode, or ZCODE_TARGET in .env).
  --apply                   Execute the restore (default is --plan).

Target resolution (install/remove/restore):
  --target flag > ZCODE_TARGET (build/.env) > ~/.zcode

Backup convention:
  ~/.zcode → <backups>/<N>-<VERSION>-old.zcode  (10 slots 0-9; oldest overwritten when full)
EOF
}

list_marketplaces() {
  local root
  root="$(nddev::repo_root)/zcode_tools/marketplaces"
  nddev::section "Available marketplaces"
  if [ ! -d "$root" ]; then
    nddev::log "info" "no marketplaces directory: $root"
    return
  fi
  local d
  for d in "$root"/*/; do
    [ -d "$d" ] || continue
    local name desc
    name="$(basename "$d")"
    desc="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('description',''))" "${d}marketplace.json" 2>/dev/null || echo '')"
    printf '  %-24s %s\n' "$name" "$desc"
  done
}

# ─── Parse command (first positional, if present) ────────────────────────
if [ "$#" -gt 0 ]; then
  case "$1" in
    bootstrap|install|remove|restore|list)
      COMMAND="$1"
      shift
      ;;
    --*) ;;  # first arg is a flag → default command (install)
    *)
      echo "Unknown command or argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
fi

# ─── Parse flags ─────────────────────────────────────────────────────────
while [ "$#" -gt 0 ]; do
  case "$1" in
    --marketplace)
      MARKETPLACE="${2:?--marketplace requires a name (use 'list')}"
      shift 2
      ;;
    --target)
      TARGET_OVERRIDE="${2:?--target requires a directory path}"
      shift 2
      ;;
    --platform)
      PLATFORM="${2:?--platform requires one of macos|ubuntu}"
      shift 2
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --plan | --dry-run)
      APPLY=0
      shift
      ;;
    --keep-backup)
      export NDDEV_BACKUPS_DIR="${2:?--keep-backup requires a directory path}"
      shift 2
      ;;
    --slot)
      SLOT="${2:?--slot requires a number 0-9}"
      shift 2
      ;;
    --backups)
      COMMAND="list-backups"
      shift
      ;;
    -l | --list)
      list_marketplaces
      exit 0
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

export NDDEV_DRY_RUN=$((1 - APPLY))

# ─── Resolve target directory ────────────────────────────────────────────
# Precedence: --target flag > ZCODE_TARGET (.env, already loaded) > ~/.zcode.
if [ -n "$TARGET_OVERRIDE" ]; then
  export NDDEV_TARGET="$TARGET_OVERRIDE"
elif [ -n "${ZCODE_TARGET:-}" ]; then
  export NDDEV_TARGET="$ZCODE_TARGET"
fi

# ─── Handle 'list' command ───────────────────────────────────────────────
if [ "$COMMAND" = "list" ]; then
  list_marketplaces
  exit 0
fi

# ─── Handle 'list-backups' command ───────────────────────────────────────
if [ "$COMMAND" = "list-backups" ]; then
  backups_dir="${NDDEV_BACKUPS_DIR:-${ZCODE_BACKUPS_DIR:-$HOME/.zcode-backups}}"
  nddev::section "Backups ($backups_dir)"
  if [ ! -d "$backups_dir" ]; then
    nddev::log "info" "no backups directory"
    exit 0
  fi
  local_found=0
  for d in "$backups_dir"/*/; do
    [ -d "$d" ] || continue
    local_found=1
    name="$(basename "$d")"
    bv="$d/BUILD-VERSION"
    if [ -f "$bv" ]; then
      ver="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('build_version','?'))" "$bv" 2>/dev/null || echo '?')"
      stamp="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('installed_at','?'))" "$bv" 2>/dev/null || echo '?')"
    else
      ver="?"; stamp="?"
    fi
    printf '  %s  build=%s  installed=%s\n' "$name" "$ver" "$stamp"
  done
  [ "$local_found" -eq 0 ] && nddev::log "info" "no backups found"
  exit 0
fi

# ─── Handle 'restore' command ────────────────────────────────────────────
if [ "$COMMAND" = "restore" ]; then
  # shellcheck source=lib/build.sh
  . "$LIB_DIR/build.sh"

  if [ -z "$SLOT" ]; then
    nddev::log "error" "restore requires --slot <N> (0-9). Use 'list --backups' to see options."
    exit 2
  fi
  if ! printf '%s' "$SLOT" | grep -qE '^[0-9]$'; then
    nddev::log "error" "--slot must be a single digit 0-9 (got: $SLOT)"
    exit 2
  fi

  backups_dir="${NDDEV_BACKUPS_DIR:-${ZCODE_BACKUPS_DIR:-$HOME/.zcode-backups}}"
  # Find the backup directory matching this slot (N-*-old.zcode).
  backup_dir="$(find "$backups_dir" -maxdepth 1 -name "${SLOT}-*-old.zcode" -print -quit 2>/dev/null || true)"
  if [ -z "$backup_dir" ] || [ ! -d "$backup_dir" ]; then
    nddev::log "error" "no backup found in slot $SLOT (looked for ${SLOT}-*-old.zcode in $backups_dir)"
    nddev::log "info" "available backups:"
    for d in "$backups_dir"/*/; do
      [ -d "$d" ] && nddev::log "info" "  $(basename "$d")"
    done
    exit 1
  fi

  nddev::section "Restore from backup slot $SLOT"
  nddev::log "info" "backup: $backup_dir"
  nddev::log "info" "target: $ZCODE_HOME"
  nddev::log "info" "mode: $([ "$APPLY" -eq 1 ] && echo 'APPLY' || echo 'PLAN (dry-run)')"

  # C2: Safety guard — refuse to overwrite a target that is not one of ours
  # (no BUILD-VERSION), same as the 'remove' command. Prevents accidental
  # destruction of a non-nddev directory via --target.
  if [ -d "$ZCODE_HOME" ] && [ ! -f "$ZCODE_HOME/BUILD-VERSION" ]; then
    nddev::log "error" "refusing to restore: $ZCODE_HOME has no BUILD-VERSION (not an nddev-zcode-app install). Pass --target explicitly if you are sure."
    exit 1
  fi

  # C1: Copy the restore source to a temp dir BEFORE any backup/destructive
  # operation. The pre-restore backup_current call below may reuse the source's
  # slot (when all 10 are full) and delete it — operating from a temp copy makes
  # that harmless. The temp dir is cleaned up on exit.
  restore_source=""
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    restore_source="$(mktemp -d -t nddev-restore.XXXXXX)"
    cp -R "$backup_dir" "$restore_source/zcode-backup"
    restore_source="$restore_source/zcode-backup"
    # Re-validate the copy exists before proceeding.
    if [ ! -d "$restore_source" ]; then
      nddev::log "error" "failed to stage restore source — aborting before any destructive operation"
      exit 1
    fi
  else
    restore_source="$backup_dir"
  fi
  # Cleanup the temp dir on exit (only in APPLY mode, only if we created it).
  # shellcheck disable=SC2329 # invoked indirectly by the EXIT trap below.
  _restore_cleanup() {
    local tmp_parent
    tmp_parent="$(dirname "$restore_source")"
    case "$tmp_parent" in
      /tmp/nddev-restore.*|*/T/nddev-restore.*) rm -rf "$tmp_parent" ;;
    esac
  }
  trap '_restore_cleanup' EXIT

  # Safety: back up the existing target before overwriting it (if it exists).
  # C3: Do NOT silence failures — a failed backup must abort the restore.
  if [ -d "$ZCODE_HOME" ]; then
    nddev::log "warn" "target exists — it will be backed up before restore"
    if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
      ZCODE_HOME="$ZCODE_HOME" BACKUPS_DIR="$backups_dir" \
        NDDEV_DRY_RUN=0 nddev::backup_current
    fi
  fi

  # C1: Re-validate the staged source still exists (belt-and-suspenders after
  # the backup_current call that may have reused a slot).
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ] && [ ! -d "$restore_source" ]; then
    nddev::log "error" "restore source was lost during pre-restore backup — aborting (target untouched)"
    exit 1
  fi

  # Clear the target, then copy the (staged) backup wholesale.
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] rm -rf %q\n' "$ZCODE_HOME"
    printf '[DRY-RUN] cp -R %q %q\n' "${restore_source}" "${ZCODE_HOME}"
  else
    rm -rf "$ZCODE_HOME"
    cp -R "$restore_source" "$ZCODE_HOME"
    nddev::log "ok" "restored $ZCODE_HOME from $(basename "$backup_dir")"
  fi

  nddev::section "Restore complete"
  bv="$ZCODE_HOME/BUILD-VERSION"
  if [ -f "$bv" ]; then
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f'[ok] build {d.get(\"build_version\",\"?\")} from {d.get(\"installed_at\",\"?\")}')" "$bv" 2>/dev/null || true
  fi
  exit 0
fi

# ─── Handle 'bootstrap' command ──────────────────────────────────────────
if [ "$COMMAND" = "bootstrap" ]; then
  BOOTSTRAP="$SCRIPT_DIR/bootstrap.sh"
  if [ ! -x "$BOOTSTRAP" ]; then
    nddev::log "error" "Missing bootstrap script: $BOOTSTRAP"
    exit 2
  fi
  # Build the arg array safely (no unquoted word-splitting).
  bootstrap_args=()
  [ -n "$PLATFORM" ] && bootstrap_args+=(--platform "$PLATFORM")
  [ "$APPLY" -eq 1 ] && bootstrap_args+=(--apply) || bootstrap_args+=(--plan)
  exec "$BOOTSTRAP" "${bootstrap_args[@]}"
fi

# ─── Handle 'remove' command ─────────────────────────────────────────────
if [ "$COMMAND" = "remove" ]; then
  # shellcheck source=lib/build.sh
  . "$LIB_DIR/build.sh"
  nddev::section "nddev-zcode-app — remove"
  nddev::log "info" "mode: $([ "$APPLY" -eq 1 ] && echo 'APPLY' || echo 'PLAN (dry-run)')"
  nddev::log "info" "target: $ZCODE_HOME"

  if [ ! -d "$ZCODE_HOME" ]; then
    nddev::log "info" "nothing to remove: $ZCODE_HOME does not exist"
    exit 0
  fi

  # Check it's one of ours (has BUILD-VERSION) before deleting.
  if [ ! -f "$ZCODE_HOME/BUILD-VERSION" ]; then
    nddev::log "error" "refusing to remove: $ZCODE_HOME has no BUILD-VERSION (not an nddev-zcode-app install). Pass --target explicitly if you are sure."
    exit 1
  fi

  # Back up first, then delete.
  nddev::backup_current
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] rm -rf %q\n' "$ZCODE_HOME"
  else
    rm -rf "$ZCODE_HOME"
    nddev::log "ok" "removed: $ZCODE_HOME"
  fi
  exit 0
fi

# ─── Handle 'install' command ────────────────────────────────────────────
if [ "$MARKETPLACE" = "" ]; then
  nddev::log "error" "install requires --marketplace <name> (use 'list' to see options)"
  exit 2
fi

# Resolve platform.
if [ "$PLATFORM" = "auto" ]; then
  PLATFORM="$(nddev::detect_platform)" || exit 1
fi
if [ "$PLATFORM" != "macos" ] && [ "$PLATFORM" != "ubuntu" ]; then
  nddev::log "error" "Unsupported platform: $PLATFORM (expected macos|ubuntu)"
  exit 2
fi

ROOT="$(nddev::repo_root)"
RUNNER="$SCRIPT_DIR/$PLATFORM/install.sh"

if [ ! -x "$RUNNER" ]; then
  nddev::log "error" "Missing runner script: $RUNNER"
  exit 2
fi

# Load the build library (defines nddev::select_marketplace etc.).
# shellcheck source=lib/build.sh
. "$LIB_DIR/build.sh"

nddev::section "nddev-zcode-app installer"
nddev::log "info" "mode: $([ "$APPLY" -eq 1 ] && echo 'APPLY' || echo 'PLAN (dry-run)')"
nddev::log "info" "platform: $PLATFORM"
nddev::log "info" "target: $ZCODE_HOME"
nddev::log "info" "repo root: $ROOT"

# Validate prerequisites.
nddev::require_cmd git required || exit 1
nddev::require_cmd python3 required || exit 1

# Select and validate the marketplace (sets SOURCE_DIR).
nddev::select_marketplace "$MARKETPLACE" || exit 1

# Export the selection so the runner (a fresh process via exec) can re-select.
export NDDEV_MARKETPLACE="$MARKETPLACE"

# Hand off to the platform runner.
exec "$RUNNER"
