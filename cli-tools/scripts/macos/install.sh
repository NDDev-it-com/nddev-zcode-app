#!/usr/bin/env bash
#
# macOS runner for the nddev-zcode-app installer.
# Sources the shared build library, selects the marketplace passed from
# install.sh, and runs the full install sequence. macOS is always desktop.
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

# Re-select the marketplace (install.sh validated it, but this is a fresh process).
nddev::select_marketplace "${NDDEV_MARKETPLACE:?NDDEV_MARKETPLACE must be set by install.sh}"

nddev::log "info" "profile: desktop (macOS)"

# macOS-specific overlay: apply templates from cli-tools/templates/macos/ if present.
OVERLAY_DIR="$(nddev::repo_root)/cli-tools/templates/macos"
if [ -d "$OVERLAY_DIR" ] && [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
  nddev::log "info" "macOS overlay dir present: $OVERLAY_DIR (reserved)"
fi

nddev::install_sequence "macos"

nddev::section "Install complete"
nddev::log "ok" "marketplace: ${NDDEV_MARKETPLACE}"
nddev::log "ok" "build version: $(nddev::build_version)"
nddev::log "ok" "platform: macos (desktop)"
if [ -n "$NDDEV_BACKUP_PATH" ]; then
  nddev::log "ok" "backup: $NDDEV_BACKUP_PATH"
fi
nddev::log "info" "next: open the ZCode desktop app. credentials.json restored from backup."
