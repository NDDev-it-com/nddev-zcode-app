#!/usr/bin/env bash
# Shared build/backup/restore logic. Sourced by the macos and ubuntu runners
# after common.sh and version.sh. The platform differences (overlay templates)
# are passed via NDDEV_PLATFORM, set by the runner.

# Path constants.
ZCODE_HOME="$HOME/.zcode"
BACKUPS_DIR="$HOME/.zcode-backups"
SOURCE_DIR="$(nddev::repo_root)/zcode_tools"
RESTORE_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/restore.sh"

# --- Backup --------------------------------------------------------------

# Back up the current ~/.zcode into ~/.zcode-backups/<N>-<DD.MM.YYYY>-<VERSION>-old.zcode.
# Safe to call when ~/.zcode does not exist (no-op log).
nddev::backup_current() {
  if [ ! -d "$ZCODE_HOME" ]; then
    nddev::log "info" "no existing ~/.zcode to back up (fresh install)"
    return 0
  fi

  local current_version backup_name target
  current_version="$(nddev::current_version)"
  backup_name="$(nddev::backup_name "$current_version")"
  target="$BACKUPS_DIR/$backup_name"

  nddev::section "Backup current ~/.zcode"
  nddev::log "info" "current build version: $current_version"
  nddev::log "info" "backup target: $target"

  nddev::ensure_dir "$BACKUPS_DIR"
  if [ -e "$target" ]; then
    nddev::log "warn" "backup slot already occupied; removing stale: $target"
    if [ "${NDDEV_DRY_RUN:-1}" -eq 0 ]; then
      rm -rf "$target"
    fi
  fi
  nddev::move "$ZCODE_HOME" "$target"
  nddev::log "ok" "backup complete"
}

# --- Build (lay down clean ~/.zcode from source) -------------------------

# Create the empty runtime directories ZCode expects to find under ~/.zcode.
nddev::create_runtime_dirs() {
  local target=$1
  local dirs=(
    "$target/cli/agents"
    "$target/cli/db"
    "$target/cli/log"
    "$target/cli/plugins/cache"
    "$target/cli/plugins/data"
    "$target/cli/plugins/marketplaces"
    "$target/marketplaces"
    "$target/v2/logs"
    "$target/v2/crash"
  )
  local d
  for d in "${dirs[@]}"; do
    nddev::ensure_dir "$d"
  done
}

# Render the templated config files (secrets from build/.env, ${HOME} expanded).
nddev::render_configs() {
  local target=$1
  nddev::section "Render config templates"

  # cli/config.json — plugins, hooks, mcp servers.
  nddev::render_template "$SOURCE_DIR/cli-config.template.json" "$target/cli/config.json"

  # v2/config.json — provider definitions with ${API_KEY} placeholders.
  nddev::render_template "$SOURCE_DIR/v2-config.template.json" "$target/v2/config.json"

  # v2/setting.json — preferences with ${HOME} expanded.
  nddev::render_template "$SOURCE_DIR/v2-setting.template.json" "$target/v2/setting.json"
}

# Copy the static source tree (AGENTS.md, skills, commands, agents, marketplaces).
nddev::copy_source_tree() {
  local target=$1
  nddev::section "Copy source tree"

  # AGENTS.md -> ~/.zcode/AGENTS.md
  nddev::copy "$SOURCE_DIR/AGENTS.md" "$target/AGENTS.md"

  # skills/, commands/, agents/ -> ~/.zcode/{skills,commands,agents}/
  local d
  for d in skills commands agents; do
    if [ -d "$SOURCE_DIR/$d" ]; then
      nddev::copy "$SOURCE_DIR/$d/." "$target/$d/"
    fi
  done

  # marketplaces/ -> ~/.zcode/marketplaces/  (each subdir is one marketplace:
  # <name>/marketplace.json + <name>/plugins/<bundle>/).
  if [ -d "$SOURCE_DIR/marketplaces" ]; then
    nddev::copy "$SOURCE_DIR/marketplaces/." "$target/marketplaces/"
  fi
}

# Build a clean ~/.zcode from source: create dirs, render configs, copy source.
nddev::build_clean() {
  local target=$1
  nddev::section "Build clean ~/.zcode"
  nddev::ensure_dir "$target"
  nddev::ensure_dir "$target/cli"
  nddev::ensure_dir "$target/v2"
  nddev::create_runtime_dirs "$target"
  nddev::copy_source_tree "$target"
  nddev::render_configs "$target"
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
    # Validate every marketplace manifest under marketplaces/<name>/marketplace.json.
    local mp_dir mp_json
    for mp_dir in "$target"/marketplaces/*/; do
      [ -d "$mp_dir" ] || continue
      mp_json="${mp_dir}marketplace.json"
      if [ ! -f "$mp_json" ]; then
        nddev::log "missing" "marketplace.json missing in $(basename "$mp_dir")"
        errors=$((errors + 1))
      elif ! nddev::validate_json "$mp_json" 2>/dev/null; then
        nddev::log "missing" "$(basename "$mp_dir")/marketplace.json is not valid JSON"
        errors=$((errors + 1))
      fi
    done
  fi

  if [ "$errors" -gt 0 ]; then
    nddev::log "error" "$errors verification error(s)"
    return 1
  fi
  nddev::log "ok" "all checks passed"
}

# --- Orchestration -------------------------------------------------------

# Full install sequence. Called by the platform runners after they apply any
# platform-specific overlay. Sets the global NDDEV_BACKUP_PATH to the backup
# directory (empty on a fresh install with no prior ~/.zcode).
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
  nddev::build_clean "$ZCODE_HOME"
  nddev::write_version_stamp "$ZCODE_HOME"

  if [ -n "$backup_path" ]; then
    nddev::restore_runtime "$backup_path" "$ZCODE_HOME"
  fi

  nddev::verify_build "$ZCODE_HOME"

  NDDEV_BACKUP_PATH="$backup_path"
}
