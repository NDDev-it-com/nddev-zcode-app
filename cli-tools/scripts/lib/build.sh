#!/usr/bin/env bash
# Shared build/backup/restore logic. Sourced by the macos and ubuntu runners
# after common.sh and version.sh.
#
# Each marketplace is a SELF-CONTAINED setup: it owns its AGENTS.md, config
# templates, mcp/hooks, user-scope skills/commands/agents, and plugins. The
# installer selects ONE marketplace (--marketplace <name>) and builds a clean
# ~/.zcode entirely from that marketplace's directory.

# Path constants. SOURCE_DIR is resolved by nddev::select_marketplace() below.
# Resolution order for the install target: CLI flag --target > ZCODE_TARGET
# (from build/.env) > NDDEV_TARGET (legacy test override) > ~/.zcode (standard).
ZCODE_HOME="${NDDEV_TARGET:-${ZCODE_TARGET:-$HOME/.zcode}}"
BACKUPS_DIR="${NDDEV_BACKUPS_DIR:-${ZCODE_BACKUPS_DIR:-$HOME/.zcode-backups}}"
MARKETPLACES_ROOT="$(nddev::repo_root)/zcode_tools/marketplaces"
SOURCE_DIR=""
RESTORE_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/restore.sh"

# --- Marketplace selection ------------------------------------------------

# Validate that a marketplace directory exists and is self-contained. Exits on failure.
nddev::validate_marketplace() {
  local mp_dir=$1
  local required=(
    "AGENTS.md"
    "marketplace.json"
    "cli-config.template.json"
    "v2-config.template.json"
    "v2-setting.template.json"
  )
  local f
  for f in "${required[@]}"; do
    if [ ! -f "$mp_dir/$f" ]; then
      nddev::log "error" "marketplace '$(basename "$mp_dir")' is not self-contained: missing $f"
      return 1
    fi
  done
  return 0
}

# Resolve SOURCE_DIR to the selected marketplace directory. $1 = marketplace name.
nddev::select_marketplace() {
  local mp_name=$1
  local mp_dir="$MARKETPLACES_ROOT/$mp_name"
  if [ ! -d "$mp_dir" ]; then
    nddev::log "error" "marketplace not found: $mp_name (looked in $mp_dir)"
    nddev::log "info" "available marketplaces:"
    local d
    for d in "$MARKETPLACES_ROOT"/*/; do
      [ -d "$d" ] && nddev::log "info" "  - $(basename "$d")"
    done
    return 1
  fi
  nddev::validate_marketplace "$mp_dir" || return 1
  SOURCE_DIR="$mp_dir"
  nddev::log "info" "selected marketplace: $mp_name ($mp_dir)"
}

# --- Backup --------------------------------------------------------------

# Back up the current ~/.zcode into ~/.zcode-backups/<N>-<VERSION>-old.zcode.
# Ten slots (0-9); reusing a slot overwrites the old backup regardless of its
# version, so the pool never exceeds 10 directories. Safe to call when ~/.zcode
# does not exist (no-op log).
nddev::backup_current() {
  if [ ! -d "$ZCODE_HOME" ]; then
    nddev::log "info" "no existing ~/.zcode to back up (fresh install)"
    return 0
  fi

  local current_version backup_name target slot
  current_version="$(nddev::current_version)"
  slot="$(nddev::backup_slot)"
  backup_name="${slot}-${current_version}-old.zcode"
  target="$BACKUPS_DIR/$backup_name"

  nddev::section "Backup current ~/.zcode"
  nddev::log "info" "current build version: $current_version"
  nddev::log "info" "backup target: $target"

  nddev::ensure_dir "$BACKUPS_DIR"

  # Remove any existing backup in this slot (version may differ, so the name
  # may differ — match by slot prefix, not exact name).
  local existing
  existing="$(find "$BACKUPS_DIR" -maxdepth 1 -name "${slot}-*-old.zcode" -print -quit 2>/dev/null)"
  if [ -n "$existing" ] && [ "$existing" != "$target" ]; then
    nddev::log "warn" "slot ${slot} occupied by different backup; removing: $(basename "$existing")"
    if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
      rm -rf "$existing"
    fi
  elif [ -e "$target" ]; then
    nddev::log "warn" "overwriting same-version backup: $target"
    if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
      rm -rf "$target"
    fi
  fi

  nddev::move "$ZCODE_HOME" "$target"
  nddev::log "ok" "backup complete"
}

# --- Build (lay down clean ~/.zcode from the selected marketplace) --------

# Create the empty runtime directories ZCode expects to find under ~/.zcode.
nddev::create_runtime_dirs() {
  local target=$1
  local dirs=(
    "$target/cli/agents"
    "$target/cli/db"
    "$target/cli/log"
    "$target/cli/plugins/cache"
    "$target/cli/plugins/data"
    "$target/v2/logs"
    "$target/v2/crash"
  )
  local d
  for d in "${dirs[@]}"; do
    nddev::ensure_dir "$d"
  done
}

# Merge the seven hook events from hooks.json into the rendered cli/config.json.
# Config-file hooks shape: events live under hooks.events.<Event> (NOT hooks.<Event>).
# hooks.json shape (after _comment stripped): { "SessionStart": [...], ... }.
# Uses python3 for safe JSON manipulation. $1=cli/config.json path, $2=hooks.json path.
nddev::merge_hooks() {
  local config_path=$1 hooks_path=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] merge hooks %q -> %q\n' "$hooks_path" "$config_path"
    return 0
  fi
  python3 - "$config_path" "$hooks_path" <<'PY'
import json, sys

config_path, hooks_path = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    config = json.load(f)
with open(hooks_path) as f:
    hooks_src = json.load(f)
hooks_src.pop("_comment", None)

# Config-file hooks go under hooks.events.<Event> (per the official
# diagnosing-hooks skill: the configuration file uses hooks.events.<Event>).
config.setdefault("hooks", {})
config["hooks"].setdefault("enabled", True)
config["hooks"].setdefault("events", {})
for event, entries in hooks_src.items():
    if not isinstance(entries, list):
        continue
    config["hooks"]["events"].setdefault(event, [])
    config["hooks"]["events"][event].extend(entries)

with open(config_path, "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}

# Merge MCP servers from mcp.json into the rendered cli/config.json under mcp.servers.
# mcp.json shape (after _comment stripped): { "mcpServers": { "<name>": {...} } }.
# $1=cli/config.json path, $2=mcp.json path.
nddev::merge_mcp() {
  local config_path=$1 mcp_path=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] merge mcp %q -> %q\n' "$mcp_path" "$config_path"
    return 0
  fi
  python3 - "$config_path" "$mcp_path" <<'PY'
import json, sys

config_path, mcp_path = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    config = json.load(f)
with open(mcp_path) as f:
    mcp_src = json.load(f)
mcp_src.pop("_comment", None)

servers = mcp_src.get("mcpServers", {})
config.setdefault("mcp", {})
config["mcp"].setdefault("servers", {})
config["mcp"]["servers"].update(servers)

with open(config_path, "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}

# Render the templated config files (secrets from build/.env, ${HOME} expanded),
# then merge hooks.json and mcp.json into cli/config.json.
nddev::render_configs() {
  local target=$1
  nddev::section "Render config templates"

  # cli/config.json — plugins, hooks, mcp servers.
  nddev::render_template "$SOURCE_DIR/cli-config.template.json" "$target/cli/config.json"

  # Merge hooks.json (per-event arrays) into cli/config.json.hooks.
  if [ -f "$SOURCE_DIR/hooks.json" ]; then
    nddev::merge_hooks "$target/cli/config.json" "$SOURCE_DIR/hooks.json"
  fi

  # Merge mcp.json (mcpServers) into cli/config.json.mcp.servers.
  if [ -f "$SOURCE_DIR/mcp.json" ]; then
    nddev::merge_mcp "$target/cli/config.json" "$SOURCE_DIR/mcp.json"
  fi

  # v2/config.json — provider definitions with ${API_KEY} placeholders.
  nddev::render_template "$SOURCE_DIR/v2-config.template.json" "$target/v2/config.json"

  # v2/setting.json — preferences with ${HOME} expanded.
  nddev::render_template "$SOURCE_DIR/v2-setting.template.json" "$target/v2/setting.json"
}

# Render ~/.zcode/.env from build/.env (for CLI tools that read secrets at runtime).
# This file is gitignored and contains real secret values — it lets CLI tool
# scripts source secrets without needing system-level env setup.
nddev::render_env() {
  local target=$1
  local src_env
  src_env="$(nddev::repo_root)/build/.env"
  if [ ! -f "$src_env" ]; then
    nddev::log "info" "no build/.env — skipping ~/.zcode/.env (CLI tools will need env vars set externally)"
    return 0
  fi
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] cp %q -> %q\n' "$src_env" "$target/.env"
    return 0
  fi
  cp "$src_env" "$target/.env"
  chmod 600 "$target/.env"
  nddev::log "ok" "wrote $target/.env (600) for CLI tool secrets"
}

# Copy the static source tree from the selected marketplace into ~/.zcode.
# The marketplace IS the setup: AGENTS.md, config files, skills/commands/agents,
# and its own plugins (installed as a marketplace ZCode can discover).
nddev::copy_source_tree() {
  local target=$1
  local mp_name
  mp_name="$(basename "$SOURCE_DIR")"
  nddev::section "Copy source tree (marketplace: $mp_name)"

  # AGENTS.md -> ~/.zcode/AGENTS.md  (the system instruction file)
  nddev::copy "$SOURCE_DIR/AGENTS.md" "$target/AGENTS.md"

  # The marketplace directory itself -> ~/.zcode/marketplaces/<name>/
  # (so ZCode's Plugin Management can discover it by local directory).
  nddev::ensure_dir "$target/marketplaces"
  nddev::copy "$SOURCE_DIR" "$target/marketplaces/$mp_name"

  # User-scope skills/, commands/, agents/ -> ~/.zcode/{skills,commands,agents}/
  # (copied OUT of the marketplace into the top-level user-scope dirs ZCode scans).
  local d
  for d in skills commands agents; do
    if [ -d "$SOURCE_DIR/$d" ]; then
      nddev::copy "$SOURCE_DIR/$d/." "$target/$d/"
    fi
  done
}

# Build a clean ~/.zcode from the selected marketplace source.
nddev::build_clean() {
  local target=$1
  nddev::section "Build clean ~/.zcode"
  nddev::ensure_dir "$target"
  nddev::ensure_dir "$target/cli"
  nddev::ensure_dir "$target/v2"
  nddev::create_runtime_dirs "$target"
  nddev::copy_source_tree "$target"
  nddev::render_configs "$target"
  nddev::render_env "$target"
}

# --- Restore (selective, from backup) ------------------------------------

# Restore runtime state from the most recent backup. Delegates to restore.sh.
nddev::restore_runtime() {
  local backup=$1
  local target=$2
  if [ ! -d "$backup" ]; then
    nddev::log "info" "no backup to restore from (fresh install)"
    return 0
  fi
  nddev::section "Restore runtime state from backup"
  # restore.sh is self-contained and reads NDDEV_DRY_RUN itself.
  NDDEV_BACKUP="$backup" NDDEV_TARGET="$target" "$RESTORE_SCRIPT"
}

# --- Verify --------------------------------------------------------------

# Validate the freshly built ~/.zcode.
nddev::verify_build() {
  local target=$1
  local mp_name
  mp_name="$(basename "$SOURCE_DIR")"
  nddev::section "Verify build"
  local errors=0

  if [ ! -f "$target/AGENTS.md" ]; then
    nddev::log "missing" "AGENTS.md not found"
    errors=$((errors + 1))
  fi

  if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
    if ! nddev::validate_json "$target/cli/config.json" 2>/dev/null; then
      nddev::log "missing" "cli/config.json is not valid JSON"
      errors=$((errors + 1))
    fi
    if ! nddev::validate_json "$target/v2/config.json" 2>/dev/null; then
      nddev::log "missing" "v2/config.json is not valid JSON"
      errors=$((errors + 1))
    fi
    if ! nddev::validate_json "$target/v2/setting.json" 2>/dev/null; then
      nddev::log "missing" "v2/setting.json is not valid JSON"
      errors=$((errors + 1))
    fi
    # Validate the selected marketplace manifest.
    local mp_json="$target/marketplaces/$mp_name/marketplace.json"
    if [ ! -f "$mp_json" ]; then
      nddev::log "missing" "$mp_name/marketplace.json not installed"
      errors=$((errors + 1))
    elif ! nddev::validate_json "$mp_json" 2>/dev/null; then
      nddev::log "missing" "$mp_name/marketplace.json is not valid JSON"
      errors=$((errors + 1))
    fi
  fi

  if [ "$errors" -gt 0 ]; then
    nddev::log "error" "$errors verification error(s)"
    return 1
  fi
  nddev::log "ok" "all checks passed"
}

# --- Orchestration -------------------------------------------------------

# Full install sequence. Called by the platform runners after they select a
# marketplace. Sets NDDEV_BACKUP_PATH to the backup directory (empty on a fresh
# install with no prior ~/.zcode).
NDDEV_BACKUP_PATH=""
nddev::install_sequence() {
  local platform=$1
  local current_version backup_name backup_path

  current_version="$(nddev::current_version)"

  # Compute the backup path BEFORE backing up (so we can restore from it).
  if [ -d "$ZCODE_HOME" ]; then
    backup_name="$(nddev::backup_name "$current_version")"
    backup_path="$BACKUPS_DIR/$backup_name"
  else
    backup_path=""
  fi

  nddev::backup_current
  nddev::check_runtime_version
  nddev::build_clean "$ZCODE_HOME"
  nddev::write_version_stamp "$ZCODE_HOME"

  if [ -n "$backup_path" ]; then
    nddev::restore_runtime "$backup_path" "$ZCODE_HOME"
  fi

  nddev::verify_build "$ZCODE_HOME"

  NDDEV_BACKUP_PATH="$backup_path"
}
