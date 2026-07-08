#!/usr/bin/env bash
#
# bootstrap.sh — download and install the ZCode desktop app (and wire the CLI
# launcher) on macOS or Ubuntu. This is the "from zero" step: it puts the
# ZCode runtime on the machine so the config installer has something to
# configure.
#
# Reads the pinned version + CDN URLs from build/version.json.
#
# Usage:
#   cli-tools/scripts/bootstrap.sh [--platform macos|ubuntu] [--apply|--plan]
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

# shellcheck source=lib/common.sh
. "$LIB_DIR/common.sh"
# shellcheck source=lib/version.sh
. "$LIB_DIR/version.sh"

# Load build/.env (may override target, but bootstrap is about the app, not ~/.zcode).
nddev::load_env

APPLY=0
PLATFORM="auto"

usage() {
  cat <<'EOF'
Usage: cli-tools/scripts/bootstrap.sh [--platform macos|ubuntu] [--apply|--plan]

Downloads and installs the ZCode desktop app at the version pinned in
build/version.json, then wires the `zcode` CLI launcher into ~/.local/bin.

Options:
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute the download + install (default is --plan).
  --plan | --dry-run        Print actions without writing (default).
  -h, --help                Show this help.

Prerequisites:
  - curl (to download)
  - node (the CLI launcher runs the app's zcode.cjs through node)
  - On macOS: hdiutil + cp (built-in) to mount and copy the .dmg
  - On Ubuntu: dpkg (for .deb) OR a writable /opt (for AppImage)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --platform) PLATFORM="${2:?--platform requires macos|ubuntu}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --plan|--dry-run) APPLY=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

export NDDEV_DRY_RUN=$((1 - APPLY))

if [ "$PLATFORM" = "auto" ]; then
  PLATFORM="$(nddev::detect_platform)" || exit 1
fi

ROOT="$(nddev::repo_root)"
VERSION_JSON="$ROOT/build/version.json"

# Read pinned version and CDN base.
APP_VERSION="$(nddev::pinned_app_version)"
CDN_BASE="$(python3 -c "import json; print(json.load(open('$VERSION_JSON'))['zcode_cdn_base'])")"

nddev::section "nddev-zcode-app — bootstrap"
nddev::log "info" "mode: $([ "$APPLY" -eq 1 ] && echo 'APPLY' || echo 'PLAN (dry-run)')"
nddev::log "info" "platform: $PLATFORM"
nddev::log "info" "pinned ZCode app: $APP_VERSION"

# ─── Prerequisites ───────────────────────────────────────────────────────
nddev::require_cmd curl required || exit 1
nddev::require_cmd node required || exit 1

# ─── Detect architecture ─────────────────────────────────────────────────
arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) arch="x64" ;;
  arm64|aarch64) arch="arm64" ;;
  *) nddev::log "error" "unsupported architecture: $arch"; exit 2 ;;
esac
nddev::log "info" "architecture: $arch"

# ─── Check if already installed ──────────────────────────────────────────
nddev::check_runtime_version
running_app="$(nddev::detect_app_version)"
if [ "$running_app" = "$APP_VERSION" ]; then
  nddev::log "ok" "ZCode $APP_VERSION already installed; skipping app download"
else
  nddev::log "info" "ZCode $APP_VERSION not found (running: $running_app); will install"
fi

# ─── Download + install per platform ─────────────────────────────────────
if [ "$running_app" != "$APP_VERSION" ]; then
  case "$PLATFORM" in
    macos)
      artifact="ZCode-${APP_VERSION}-mac-${arch}.dmg"
      url="${CDN_BASE}/${APP_VERSION}/${artifact}"
      tmp_dmg="$(mktemp -t nddev-zcode.XXXXXX).dmg"

      nddev::section "Download ZCode.app ($artifact)"
      nddev::log "info" "url: $url"
      if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
        printf '[DRY-RUN] curl -fL -o %q %q\n' "$tmp_dmg" "$url"
      else
        curl -fL --progress-bar -o "$tmp_dmg" "$url"
        nddev::log "ok" "downloaded $(du -h "$tmp_dmg" | cut -f1)"
      fi

      nddev::section "Install ZCode.app"
      mount_point="/Volumes/ZCode-${APP_VERSION}"
      if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
        printf '[DRY-RUN] hdiutil attach %q\n' "$tmp_dmg"
        printf '[DRY-RUN] cp -R "/Volumes/ZCode/ZCode.app" /Applications/\n'
        printf '[DRY-RUN] hdiutil detach %q\n' "$mount_point"
      else
        hdiutil attach "$tmp_dmg" -nobrowse -mountpoint "$mount_point" >/dev/null 2>&1
        cp -R "${mount_point}/ZCode.app" /Applications/
        hdiutil detach "$mount_point" >/dev/null 2>&1
        nddev::log "ok" "installed ZCode.app to /Applications/"
      fi
      rm -f "$tmp_dmg"
      app_entry="/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs"
      ;;

    ubuntu)
      # Prefer .deb (cleaner uninstall); fall back to AppImage.
      artifact="ZCode-${APP_VERSION}-linux-${arch}.deb"
      url="${CDN_BASE}/${APP_VERSION}/${artifact}"
      tmp_deb="$(mktemp -t nddev-zcode.XXXXXX).deb"

      nddev::section "Download ZCode ($artifact)"
      nddev::log "info" "url: $url"
      if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
        printf '[DRY-RUN] curl -fL -o %q %q\n' "$tmp_deb" "$url"
        printf '[DRY-RUN] sudo dpkg -i %q\n' "$tmp_deb"
      else
        curl -fL --progress-bar -o "$tmp_deb" "$url"
        nddev::log "ok" "downloaded $(du -h "$tmp_deb" | cut -f1)"
        if command -v sudo >/dev/null 2>&1; then
          sudo dpkg -i "$tmp_deb" || sudo apt-get install -f -y
        else
          dpkg -i "$tmp_deb" || apt-get install -f -y
        fi
        nddev::log "ok" "installed ZCode via dpkg"
      fi
      rm -f "$tmp_deb"
      app_entry="/opt/ZCode/resources/glm/zcode.cjs"
      ;;
  esac
fi

# ─── Wire the CLI launcher ───────────────────────────────────────────────
nddev::section "Wire zcode CLI launcher"
bin_dir="${HOME}/.local/bin"
launcher="${bin_dir}/zcode"

# Resolve the entry point based on what exists.
[ -z "${app_entry:-}" ] && app_entry="/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs"
if [ ! -f "$app_entry" ]; then
  # Try the Linux path.
  app_entry="/opt/ZCode/resources/glm/zcode.cjs"
fi

if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
  printf '[DRY-RUN] write zcode launcher -> %q (entry: %s)\n' "$launcher" "$app_entry"
else
  mkdir -p "$bin_dir"
  cat > "$launcher" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
# Managed by nddev-zcode-app bootstrap. Launches the ZCode CLI (zcode.cjs inside
# the desktop app bundle) through node. No args -> TUI; 'zcode -p "<prompt>"'
# runs headless.
ZCODE_CJS="${app_entry}"
[ -f "\$ZCODE_CJS" ] || { echo "zcode: entry not found at \$ZCODE_CJS (is ZCode installed?)" >&2; exit 127; }
exec node "\$ZCODE_CJS" "\$@"
LAUNCHER
  chmod +x "$launcher"
  nddev::log "ok" "wrote $launcher"

  # Ensure ~/.local/bin is on PATH (best-effort, non-clobbering).
  case ":${PATH}:" in
    *":${bin_dir}:"*) ;;
    *)
      nddev::log "warn" "${bin_dir} is not on PATH; add it to your shell rc to use 'zcode'"
      ;;
  esac
fi

# ─── Verify ──────────────────────────────────────────────────────────────
nddev::section "Verify"
nddev::check_runtime_version

nddev::section "Bootstrap complete"
nddev::log "ok" "ZCode app: $(nddev::detect_app_version)"
nddev::log "ok" "ZCode CLI: $(nddev::detect_cli_version)"
nddev::log "info" "next: run 'install.sh install --marketplace <name> --apply' to configure ~/.zcode"
