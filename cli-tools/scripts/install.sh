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

usage() {
  cat <<'EOF'
Usage: cli-tools/scripts/install.sh [install|remove|list] [options]

Commands:
  install (default)   Build ~/.zcode from a marketplace.
  remove              Back up and delete the installed ~/.zcode.
  list                List available marketplaces.

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

Target resolution:
  --target flag > ZCODE_TARGET (build/.env) > ~/.zcode

Backup convention:
  ~/.zcode → <backups>/<N>-<DD.MM.YYYY>-<VERSION>-old.zcode  (N = 1-9 rotation slot)
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
    install|remove|list)
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
