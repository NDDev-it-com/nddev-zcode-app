#!/usr/bin/env bash
#
# Ubuntu runner for the nddev-zcode-app installer.
# Sources the shared build library, selects the marketplace passed from
# install.sh, and runs the full install sequence. Supports desktop or server.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$SCRIPT_DIR/../lib" && pwd)"

# shellcheck source=lib/common.sh
. "$LIB_DIR/common.sh"
# shellcheck source=lib/version.sh
. "$LIB_DIR/version.sh"
# shellcheck source=lib/build.sh
. "$LIB_DIR/build.sh"

# Load build/.env (idempotent — env vars already set win, so this is safe even
# when install.sh already loaded them before exec).
nddev::load_env

# Re-select the marketplace (install.sh validated it, but this is a fresh process).
nddev::select_marketplace "${NDDEV_MARKETPLACE:?NDDEV_MARKETPLACE must be set by install.sh}"

# On a headless server there is no desktop app; the ~/.zcode config still applies
# to the CLI and any agent sessions run there.
PROFILE="desktop"
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  PROFILE="server"
fi
nddev::log "info" "profile: $PROFILE (Ubuntu)"

# Ubuntu-specific overlay: apply templates from cli-tools/templates/ubuntu/ if present.
OVERLAY_DIR="$(nddev::repo_root)/cli-tools/templates/ubuntu"
if [ -d "$OVERLAY_DIR" ] && [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
  nddev::log "info" "Ubuntu overlay dir present: $OVERLAY_DIR (reserved)"
fi

nddev::install_sequence "ubuntu"

nddev::section "Install complete"
nddev::log "ok" "marketplace: ${NDDEV_MARKETPLACE}"
nddev::log "ok" "build version: $(nddev::build_version)"
nddev::log "ok" "platform: ubuntu ($PROFILE)"
if [ -n "$NDDEV_BACKUP_PATH" ]; then
  nddev::log "ok" "backup: $NDDEV_BACKUP_PATH"
fi
nddev::log "info" "next: credentials.json restored from backup (re-auth in the app if it expired)."
