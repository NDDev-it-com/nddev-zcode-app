#!/usr/bin/env bash
#
# nddev-zcode-app installer — manages a complete, version-stamped ~/.zcode
# built from ONE selected setup. Supports bootstrap, install, update, switch,
# status, backup inspection, restore, and removal on macOS or Ubuntu.
#
# Usage:
#   cli-tools/scripts/install.sh <command> [options]
#
# Commands:
#   bootstrap           Download and install the pinned ZCode app and CLI.
#   install (default)   Build ~/.zcode from a setup (backup → build → restore).
#   remove              Back up and delete the installed ~/.zcode.
#   restore             Restore ~/.zcode from a numbered backup slot.
#   list                List available setups or backups.
#   status              Report the installed setup and version stamp.
#
# Each native marketplace directory is a self-contained setup (its own AGENTS.md, config
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

# ─── Defaults ────────────────────────────────────────────────────────────
COMMAND="install"
APPLY=0
PLATFORM="auto"
MARKETPLACE=""
TARGET_OVERRIDE=""
SLOT=""
ADOPT_UNMANAGED=0
ALLOW_TARGET_RELOCATION=0
COMMAND_EXPLICIT=0
SEEN_MARKETPLACE=0
SEEN_TARGET=0
SEEN_PLATFORM=0
SEEN_APPLY=0
SEEN_PLAN=0
SEEN_KEEP_BACKUP=0
SEEN_SLOT=0
SEEN_ADOPT=0
SEEN_RELOCATION=0
SEEN_BACKUPS=0
SEEN_LIST=0
SEEN_JSON=0
OUTPUT_JSON=0

usage() {
  cat <<'EOF'
Usage: cli-tools/scripts/install.sh [bootstrap|install|remove|restore|list|status] [options]

Commands:
  bootstrap             Download and install the ZCode desktop app + CLI (from zero).
  install (default)     Build ~/.zcode from a setup.
  remove                Back up and delete the installed ~/.zcode.
  restore               Restore ~/.zcode from a backup slot (0-9).
  list                  List available setups (and backups with --backups).
  status                Show the installed setup and validated version stamp.

Options (bootstrap):
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute the download + install (default is --plan).

Options (install):
  --setup <id>              Which setup to build from (required for install).
  --marketplace <id>        Backward-compatible alias for --setup.
  --target <dir>            Install directory (default: ~/.zcode, or ZCODE_TARGET in .env).
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute (default is --plan / dry-run).
  --plan | --dry-run        Print actions without writing (default).
  --adopt-unmanaged         Allow install to replace an explicitly selected,
                            existing unstamped --target after backing it up.

Options (remove):
  --target <dir>            Directory to remove (default: ~/.zcode, or ZCODE_TARGET in .env).
  --apply                   Actually delete (default is --plan).
  --keep-backup <dir>       Use this backup root for the generated numbered slot.

Options (restore):
  --slot <N>                Backup slot to restore (0-9). Required.
  --target <dir>            Restore destination (default: ~/.zcode, or ZCODE_TARGET in .env).
  --allow-target-relocation Restore an adopted-unmanaged envelope to a different,
                            explicitly selected --target.
  --apply                   Execute the restore (default is --plan).

Options (list/status):
  --json                    Emit stable machine-readable JSON.
  --target <dir>            Status target (default: ~/.zcode, or ZCODE_TARGET in .env).

Target resolution (install/remove/restore/status):
  --target flag > ZCODE_TARGET (build/.env) > ~/.zcode

Backup convention:
  ~/.zcode → <backups>/<N>-<VERSION>-old.zcode  (10 slots 0-9; oldest overwritten when full)
EOF
}

list_setups() {
  local output=$1 root
  root="$(nddev::repo_root)/zcode_tools/marketplaces"
  if [ "$output" = "human" ]; then
    nddev::section "Available setups"
  fi
  python3 -I - "$root" "$output" <<'PY'
import json
import os
import re
import stat
import sys

root, output = sys.argv[1:]
if output not in {"human", "json"}:
    raise SystemExit("unsupported setup-list output mode")
if not os.path.lexists(root):
    setups = []
else:
    root_metadata = os.lstat(root)
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise SystemExit("setup catalog root must be a real directory")
    setups = []
    for entry in sorted(os.scandir(root), key=lambda candidate: candidate.name):
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.name) is None:
            continue
        if not entry.is_dir(follow_symlinks=False):
            raise SystemExit(f"unsafe setup catalog entry: {entry.name}")
        manifest_path = os.path.join(entry.path, "marketplace.json")
        try:
            manifest_metadata = os.lstat(manifest_path)
            if stat.S_ISLNK(manifest_metadata.st_mode) or not stat.S_ISREG(manifest_metadata.st_mode):
                raise SystemExit(f"unsafe setup manifest: {entry.name}")
            with open(manifest_path, encoding="utf-8") as stream:
                manifest = json.load(stream)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot read setup manifest: {entry.name}") from exc
        if not isinstance(manifest, dict) or manifest.get("name") != entry.name:
            raise SystemExit(f"setup manifest identity mismatch: {entry.name}")
        description = manifest.get("description", "")
        plugins = manifest.get("plugins")
        if (
            not isinstance(description, str)
            or any(ord(char) < 32 or ord(char) == 127 for char in description)
            or not isinstance(plugins, list)
        ):
            raise SystemExit(f"invalid setup manifest summary: {entry.name}")
        setups.append(
            {"id": entry.name, "description": description, "plugin_count": len(plugins)}
        )
if output == "json":
    print(json.dumps({"schema_version": 1, "setups": setups}, separators=(",", ":")))
elif not setups:
    print("  no setups found")
else:
    for setup in setups:
        print(f"  {setup['id']:<24} {setup['description']}")
PY
}

show_status() {
  local target=$1 output=$2 metadata setup_label
  if [ ! -e "$target" ] && [ ! -L "$target" ]; then
    if [ "$output" = "json" ]; then
      printf '{"schema_version":1,"state":"missing"}\n'
    else
      nddev::section "Installation status"
      printf '  state: missing\n'
    fi
    return 0
  fi
  if [ ! -e "$target/BUILD-VERSION" ] && [ ! -L "$target/BUILD-VERSION" ]; then
    if [ "$output" = "json" ]; then
      printf '{"schema_version":1,"state":"unmanaged"}\n'
    else
      nddev::section "Installation status"
      printf '  state: unmanaged\n'
    fi
    return 0
  fi
  if [ -L "$target/BUILD-VERSION" ] || [ ! -f "$target/BUILD-VERSION" ]; then
    nddev::log "error" "BUILD-VERSION must be a regular non-symlink file"
    return 1
  fi
  metadata="$(nddev::stamp_metadata "$target" status-json)" || return 1
  if [ "$output" = "json" ]; then
    python3 -I - "$metadata" <<'PY'
import json
import sys

stamp = json.loads(sys.argv[1])
print(json.dumps({"schema_version": 1, "state": "managed", **stamp}, separators=(",", ":")))
PY
    return 0
  fi
  setup_label="$(nddev::stamp_setup_id "$target")" || return 1
  [ -n "$setup_label" ] || setup_label="unknown (legacy stamp)"
  nddev::section "Installation status"
  python3 -I - "$metadata" "$setup_label" <<'PY'
import json
import sys

stamp = json.loads(sys.argv[1])
print("  state: managed")
print(f"  setup: {sys.argv[2]}")
print(f"  build: {stamp['build_version']}")
print(f"  platform: {stamp['platform']}")
print(f"  installed: {stamp['installed_at']}")
PY
}

# ─── Parse command (first positional, if present) ────────────────────────
if [ "$#" -gt 0 ]; then
  case "$1" in
    bootstrap|install|remove|restore|list|status)
      COMMAND="$1"
      COMMAND_EXPLICIT=1
      shift
      ;;
    --*) ;;  # first arg is a flag → default command (install)
    *)
      echo "Unknown command or argument" >&2
      usage >&2
      exit 2
      ;;
  esac
fi

# ─── Parse flags ─────────────────────────────────────────────────────────
while [ "$#" -gt 0 ]; do
  case "$1" in
    --setup | --marketplace)
      nddev::require_option_once "$SEEN_MARKETPLACE" "$1" || exit 2
      nddev::require_option_value "$1" "${2-}" || exit 2
      MARKETPLACE="$2"
      SEEN_MARKETPLACE=1
      shift 2
      ;;
    --target)
      nddev::require_option_once "$SEEN_TARGET" "$1" || exit 2
      nddev::require_option_value "$1" "${2-}" || exit 2
      TARGET_OVERRIDE="$2"
      SEEN_TARGET=1
      shift 2
      ;;
    --platform)
      nddev::require_option_once "$SEEN_PLATFORM" "$1" || exit 2
      nddev::require_option_value "$1" "${2-}" || exit 2
      PLATFORM="$2"
      SEEN_PLATFORM=1
      shift 2
      ;;
    --apply)
      nddev::require_option_once "$SEEN_APPLY" "$1" || exit 2
      APPLY=1
      SEEN_APPLY=1
      shift
      ;;
    --plan | --dry-run)
      nddev::require_option_once "$SEEN_PLAN" "$1" || exit 2
      APPLY=0
      SEEN_PLAN=1
      shift
      ;;
    --keep-backup)
      nddev::require_option_once "$SEEN_KEEP_BACKUP" "$1" || exit 2
      nddev::require_option_value "$1" "${2-}" || exit 2
      export NDDEV_BACKUPS_DIR="$2"
      SEEN_KEEP_BACKUP=1
      shift 2
      ;;
    --slot)
      nddev::require_option_once "$SEEN_SLOT" "$1" || exit 2
      nddev::require_option_value "$1" "${2-}" || exit 2
      SLOT="$2"
      SEEN_SLOT=1
      shift 2
      ;;
    --adopt-unmanaged)
      nddev::require_option_once "$SEEN_ADOPT" "$1" || exit 2
      ADOPT_UNMANAGED=1
      SEEN_ADOPT=1
      shift
      ;;
    --allow-target-relocation)
      nddev::require_option_once "$SEEN_RELOCATION" "$1" || exit 2
      ALLOW_TARGET_RELOCATION=1
      SEEN_RELOCATION=1
      shift
      ;;
    --backups)
      nddev::require_option_once "$SEEN_BACKUPS" "$1" || exit 2
      SEEN_BACKUPS=1
      shift
      ;;
    --json)
      nddev::require_option_once "$SEEN_JSON" "$1" || exit 2
      OUTPUT_JSON=1
      SEEN_JSON=1
      shift
      ;;
    -l | --list)
      nddev::require_option_once "$SEEN_LIST" "$1" || exit 2
      if [ "$COMMAND_EXPLICIT" -eq 1 ] && [ "$COMMAND" != "list" ]; then
        nddev::log "error" "$1 cannot replace the explicit '$COMMAND' command"
        exit 2
      fi
      COMMAND="list"
      COMMAND_EXPLICIT=1
      SEEN_LIST=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Reject every syntactically accepted but command-inapplicable option. Silent
# ignores are unsafe for an installer because they create false expectations.
INVALID_OPTIONS=""
nddev::reject_seen_option() {
  local seen=$1 option=$2
  if [ "$seen" -eq 1 ]; then
    INVALID_OPTIONS="${INVALID_OPTIONS}${INVALID_OPTIONS:+, }$option"
  fi
}

if [ "$SEEN_APPLY" -eq 1 ] && [ "$SEEN_PLAN" -eq 1 ]; then
  nddev::log "error" "--apply and --plan/--dry-run are mutually exclusive"
  exit 2
fi

case "$COMMAND" in
  bootstrap)
    nddev::reject_seen_option "$SEEN_MARKETPLACE" --setup/--marketplace
    nddev::reject_seen_option "$SEEN_TARGET" --target
    nddev::reject_seen_option "$SEEN_KEEP_BACKUP" --keep-backup
    nddev::reject_seen_option "$SEEN_SLOT" --slot
    nddev::reject_seen_option "$SEEN_ADOPT" --adopt-unmanaged
    nddev::reject_seen_option "$SEEN_RELOCATION" --allow-target-relocation
    nddev::reject_seen_option "$SEEN_BACKUPS" --backups
    nddev::reject_seen_option "$SEEN_JSON" --json
    ;;
  install)
    nddev::reject_seen_option "$SEEN_KEEP_BACKUP" --keep-backup
    nddev::reject_seen_option "$SEEN_SLOT" --slot
    nddev::reject_seen_option "$SEEN_RELOCATION" --allow-target-relocation
    nddev::reject_seen_option "$SEEN_BACKUPS" --backups
    nddev::reject_seen_option "$SEEN_JSON" --json
    ;;
  remove)
    nddev::reject_seen_option "$SEEN_MARKETPLACE" --setup/--marketplace
    nddev::reject_seen_option "$SEEN_PLATFORM" --platform
    nddev::reject_seen_option "$SEEN_SLOT" --slot
    nddev::reject_seen_option "$SEEN_ADOPT" --adopt-unmanaged
    nddev::reject_seen_option "$SEEN_RELOCATION" --allow-target-relocation
    nddev::reject_seen_option "$SEEN_BACKUPS" --backups
    nddev::reject_seen_option "$SEEN_JSON" --json
    ;;
  restore)
    nddev::reject_seen_option "$SEEN_MARKETPLACE" --setup/--marketplace
    nddev::reject_seen_option "$SEEN_PLATFORM" --platform
    nddev::reject_seen_option "$SEEN_KEEP_BACKUP" --keep-backup
    nddev::reject_seen_option "$SEEN_ADOPT" --adopt-unmanaged
    nddev::reject_seen_option "$SEEN_BACKUPS" --backups
    nddev::reject_seen_option "$SEEN_JSON" --json
    ;;
  list)
    nddev::reject_seen_option "$SEEN_MARKETPLACE" --setup/--marketplace
    nddev::reject_seen_option "$SEEN_TARGET" --target
    nddev::reject_seen_option "$SEEN_PLATFORM" --platform
    nddev::reject_seen_option "$SEEN_APPLY" --apply
    nddev::reject_seen_option "$SEEN_PLAN" --plan/--dry-run
    nddev::reject_seen_option "$SEEN_KEEP_BACKUP" --keep-backup
    nddev::reject_seen_option "$SEEN_SLOT" --slot
    nddev::reject_seen_option "$SEEN_ADOPT" --adopt-unmanaged
    nddev::reject_seen_option "$SEEN_RELOCATION" --allow-target-relocation
    ;;
  status)
    nddev::reject_seen_option "$SEEN_MARKETPLACE" --setup/--marketplace
    nddev::reject_seen_option "$SEEN_PLATFORM" --platform
    nddev::reject_seen_option "$SEEN_APPLY" --apply
    nddev::reject_seen_option "$SEEN_PLAN" --plan/--dry-run
    nddev::reject_seen_option "$SEEN_KEEP_BACKUP" --keep-backup
    nddev::reject_seen_option "$SEEN_SLOT" --slot
    nddev::reject_seen_option "$SEEN_ADOPT" --adopt-unmanaged
    nddev::reject_seen_option "$SEEN_RELOCATION" --allow-target-relocation
    nddev::reject_seen_option "$SEEN_BACKUPS" --backups
    ;;
esac
if [ -n "$INVALID_OPTIONS" ]; then
  nddev::log "error" "option(s) not valid for '$COMMAND': $INVALID_OPTIONS"
  exit 2
fi
if [ "$COMMAND" = "list" ] && [ "$SEEN_BACKUPS" -eq 1 ]; then
  if [ "$OUTPUT_JSON" -eq 1 ]; then
    nddev::log "error" "--json is not valid with list --backups"
    exit 2
  fi
  COMMAND="list-backups"
fi

if [ "$ALLOW_TARGET_RELOCATION" -eq 1 ]; then
  if [ "$COMMAND" != "restore" ] || [ -z "$TARGET_OVERRIDE" ]; then
    nddev::log "error" "--allow-target-relocation requires restore with an explicit --target"
    exit 2
  fi
fi
if [ "$ADOPT_UNMANAGED" -eq 1 ]; then
  if [ -z "$TARGET_OVERRIDE" ]; then
    nddev::log "error" "--adopt-unmanaged requires an explicit --target <existing-directory>"
    exit 2
  fi
  if [ -L "$TARGET_OVERRIDE" ] || [ ! -d "$TARGET_OVERRIDE" ]; then
    nddev::log "error" "--adopt-unmanaged target must be an existing real directory"
    exit 2
  fi
fi

# Required operands and finite option domains are CLI grammar, so reject them
# before consulting Python or any machine-local build/.env state.
case "$COMMAND" in
  install)
    if [ -z "$MARKETPLACE" ]; then
      nddev::log "error" "install requires --setup <id> (use 'list' to see options)"
      exit 2
    fi
    if ! printf '%s\n' "$MARKETPLACE" | grep -qE '^[a-z0-9][a-z0-9-]*$'; then
      nddev::log "error" "invalid setup id"
      exit 2
    fi
    case "$PLATFORM" in auto | macos | ubuntu) ;; *) nddev::log "error" "unsupported platform (expected macos|ubuntu)"; exit 2 ;; esac
    ;;
  restore)
    if [ -z "$SLOT" ]; then
      nddev::log "error" "restore requires --slot <N> (0-9). Use 'list --backups' to see options."
      exit 2
    fi
    case "$SLOT" in [0-9]) ;; *) nddev::log "error" "--slot must be a single digit 0-9"; exit 2 ;; esac
    ;;
esac

# Bootstrap is independent of build/.env. Dispatch it after the complete CLI
# grammar check, but before this wrapper requires Python or loads project
# configuration. The bootstrap entry point performs its own prerequisite
# checks after parsing its CLI.
if [ "$COMMAND" = "bootstrap" ]; then
  BOOTSTRAP="$SCRIPT_DIR/bootstrap.sh"
  if [ ! -x "$BOOTSTRAP" ]; then
    nddev::log "error" "Missing bootstrap script: $BOOTSTRAP"
    exit 2
  fi
  bootstrap_args=(--platform "$PLATFORM")
  [ "$APPLY" -eq 1 ] && bootstrap_args+=(--apply) || bootstrap_args+=(--plan)
  exec "$BOOTSTRAP" "${bootstrap_args[@]}"
fi

# Every remaining command uses isolated Python helpers. Plain setup
# listing needs no build/.env; target-mutating and backup-listing commands load
# only the two documented path keys at this layer.
if [ "$OUTPUT_JSON" -eq 1 ]; then
  nddev::require_cmd python3 required >/dev/null || exit 1
else
  nddev::require_cmd python3 required || exit 1
fi
if [ "$COMMAND" = "list" ]; then
  if [ "$OUTPUT_JSON" -eq 1 ]; then
    list_setups json
  else
    list_setups human
  fi
  exit 0
fi
nddev::load_env paths-only || exit 1

export NDDEV_DRY_RUN=$((1 - APPLY))
export NDDEV_ADOPT_UNMANAGED="$ADOPT_UNMANAGED"
export NDDEV_ALLOW_TARGET_RELOCATION="$ALLOW_TARGET_RELOCATION"

# ─── Resolve target directory ────────────────────────────────────────────
# Precedence: --target flag > ZCODE_TARGET (.env, already loaded) > ~/.zcode.
if [ -n "$TARGET_OVERRIDE" ]; then
  export NDDEV_TARGET="$TARGET_OVERRIDE"
elif [ -n "${ZCODE_TARGET:-}" ]; then
  export NDDEV_TARGET="$ZCODE_TARGET"
fi

# ─── Handle read-only status command ─────────────────────────────────────
if [ "$COMMAND" = "status" ]; then
  status_target="${NDDEV_TARGET:-$HOME/.zcode}"
  status_target="$(nddev::validate_directory_endpoint "install target" "$status_target")" || exit 2
  if [ "$OUTPUT_JSON" -eq 1 ]; then
    show_status "$status_target" json
  else
    show_status "$status_target" human
  fi
  exit $?
fi

# ─── Handle 'list-backups' command ───────────────────────────────────────
if [ "$COMMAND" = "list-backups" ]; then
  backups_dir="${NDDEV_BACKUPS_DIR:-${ZCODE_BACKUPS_DIR:-$HOME/.zcode-backups}}"
  backups_dir="$(nddev::validate_directory_endpoint "backup root" "$backups_dir")" || exit 2
  nddev::section "Backups ($backups_dir)"
  if [ ! -d "$backups_dir" ]; then
    nddev::log "info" "no backups directory"
    exit 0
  fi
  local_found=0
  for d in "$backups_dir"/*/; do
    [ -d "$d" ] && [ ! -L "$d" ] || continue
    local_found=1
    name="$(basename "$d")"
    slot_name="${name%%-*}"
    backup_version="${name#*-}"
    backup_version="${backup_version%-old.zcode}"
    if [ "$name" != "$slot_name-$backup_version-old.zcode" ] \
      || ! { case "$slot_name" in [0-9]) true ;; *) false ;; esac; } \
      || { [ "$backup_version" != "unmanaged" ] && ! nddev::is_semver "$backup_version"; }; then
      printf '  [redacted-invalid-name]  type=invalid-backup-name\n'
      continue
    fi
    bv="$d/BUILD-VERSION"
    if [ -f "$bv" ] && [ ! -L "$bv" ]; then
      if ver="$(nddev::stamp_version "$d" 2>/dev/null)"; then
        stamp="$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['installed_at'])" "$bv" 2>/dev/null)" || {
          printf '  %s  type=invalid-managed-stamp\n' "$name"
          continue
        }
        printf '  %s  type=managed  build=%s  installed=%s\n' "$name" "$ver" "$stamp"
      else
        printf '  %s  type=invalid-managed-stamp\n' "$name"
      fi
    elif [ -f "$d/NDDEV-BACKUP.json" ] && [ ! -L "$d/NDDEV-BACKUP.json" ]; then
      summary="$(python3 -I - "$d" "$NDDEV_SEMVER_PATTERN" <<'PY'
import json
import os
import re
import sys
import datetime as dt

root = os.path.realpath(sys.argv[1])
semver = re.compile(sys.argv[2])
try:
    with open(os.path.join(root, "NDDEV-BACKUP.json"), encoding="utf-8") as stream:
        data = json.load(stream)
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
payload_name = data.get("payload")
original = data.get("original_target")
installer_build = data.get("installer_build")
created_at = data.get("created_at")
if (
    data.get("schema") != 1
    or data.get("type") != "adopted-unmanaged"
    or payload_name != "payload"
    or not isinstance(original, str)
    or any(ord(char) < 32 or ord(char) == 127 for char in original)
    or not isinstance(installer_build, str)
    or not semver.fullmatch(installer_build)
    or not isinstance(created_at, str)
):
    raise SystemExit(1)
try:
    parsed = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
except ValueError:
    raise SystemExit(1)
if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
    raise SystemExit(1)
payload = os.path.realpath(os.path.join(root, payload_name))
if (
    os.path.dirname(payload) != root
    or not os.path.isdir(payload)
    or os.path.islink(payload)
    or not os.path.isabs(original)
    or os.path.realpath(original) != original
):
    raise SystemExit(1)
print(
    f"type=adopted-unmanaged build={installer_build} "
    f"created={created_at} target={original}"
)
PY
)" || summary="type=invalid-adoption-envelope"
      printf '  %s  %s\n' "$name" "$summary"
    else
      printf '  %s  type=invalid-or-unmanaged\n' "$name"
    fi
  done
  [ "$local_found" -eq 0 ] && nddev::log "info" "no backups found"
  exit 0
fi

# ─── Handle 'restore' command ────────────────────────────────────────────
if [ "$COMMAND" = "restore" ]; then
  # shellcheck source=lib/build.sh
  . "$LIB_DIR/build.sh"

  # Keep this as a simple command: putting a Bash function in an OR-list
  # disables errexit throughout its body and can bypass transaction rollback.
  nddev::restore_backup_slot "$SLOT"
  nddev::log "ok" "restored $ZCODE_HOME from $(basename "$NDDEV_RESTORE_SOURCE")"

  nddev::section "Restore complete"
  bv="$ZCODE_HOME/BUILD-VERSION"
  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ] && [ -f "$bv" ]; then
    python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(f'[ok] build {d[\"build_version\"]} from {d[\"installed_at\"]}')" "$bv"
  fi
  exit 0
fi

# ─── Handle 'remove' command ─────────────────────────────────────────────
if [ "$COMMAND" = "remove" ]; then
  # shellcheck source=lib/build.sh
  . "$LIB_DIR/build.sh"
  nddev::section "nddev-zcode-app — remove"
  nddev::log "info" "mode: $([ "$APPLY" -eq 1 ] && echo 'APPLY' || echo 'PLAN (dry-run)')"

  # Keep this as a simple command so critical failures trigger the EXIT trap.
  nddev::remove_managed_target
  [ -n "$NDDEV_BACKUP_PATH" ] && nddev::log "ok" "removed target into backup: $NDDEV_BACKUP_PATH"
  exit 0
fi

# ─── Handle 'install' command ────────────────────────────────────────────
# Resolve platform.
if [ "$PLATFORM" = "auto" ]; then
  PLATFORM="$(nddev::detect_platform)" || exit 1
fi
if [ "$PLATFORM" != "macos" ] && [ "$PLATFORM" != "ubuntu" ]; then
  nddev::log "error" "unsupported platform (expected macos|ubuntu)"
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
nddev::log "info" "repo root: $ROOT"

# Select and validate the marketplace (sets SOURCE_DIR).
nddev::select_marketplace "$MARKETPLACE" || exit 1

# Export the selection so the runner (a fresh process via exec) can re-select.
export NDDEV_MARKETPLACE="$MARKETPLACE"

# Hand off to the platform runner.
exec "$RUNNER"
