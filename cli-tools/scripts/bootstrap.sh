#!/usr/bin/env bash
# Download, verify, install, and post-verify the pinned ZCode desktop runtime.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
# shellcheck source=lib/common.sh
. "$LIB_DIR/common.sh"
# shellcheck source=lib/version.sh
. "$LIB_DIR/version.sh"

APPLY=0
PLATFORM="auto"
TMP_ROOT=""
MOUNT_POINT=""
MOUNTED=0
MOUNT_ATTEMPTED=0
MOUNT_TOOL=""
APP_STAGE_PATH=""
APP_STAGE_IDENTITY=""
APP_OLD_PATH=""
APP_OLD_IDENTITY=""
APP_INSTALLED_PATH=""
APP_LIVE_IDENTITY=""
APP_SWAPPED=0
LAUNCHER_PATH=""
LAUNCHER_OLD_PATH=""
LAUNCHER_OLD_IDENTITY=""
LAUNCHER_STAGE_PATH=""
LAUNCHER_STAGE_IDENTITY=""
LAUNCHER_LIVE_IDENTITY=""
LAUNCHER_SWAPPED=0
BOOTSTRAP_COMMITTED=0
BOOTSTRAP_LOCK_PATHS=()
SEEN_APPLY=0
SEEN_PLAN=0
SEEN_PLATFORM=0

usage() {
  cat <<'EOF'
Usage: cli-tools/scripts/bootstrap.sh [--platform macos|ubuntu] [--apply|--plan]

Installs the exact ZCode desktop artifact pinned in build/version.json and
wires its embedded CLI into ~/.local/bin/zcode. Downloads are accepted only
after size and SHA-512 verification.

Options:
  --platform macos|ubuntu   Target platform (default: auto-detect).
  --apply                   Download, verify, install, and post-verify.
  --plan | --dry-run        Print the verified plan without writing (default).
  -h, --help                Show this help.

Ubuntu uses the verified DEB when complete dpkg tooling is available. A
verified, locally extracted AppImage is used only when DEB tooling is absent.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --platform)
      nddev::require_option_once "$SEEN_PLATFORM" "$1" || exit 2
      nddev::require_option_value "$1" "${2-}" || exit 2
      PLATFORM="$2"
      SEEN_PLATFORM=1
      shift 2
      ;;
    --apply)
      nddev::require_option_once "$SEEN_APPLY" "$1" || exit 2
      APPLY=1; SEEN_APPLY=1; shift
      ;;
    --plan | --dry-run)
      nddev::require_option_once "$SEEN_PLAN" "$1" || exit 2
      APPLY=0; SEEN_PLAN=1; shift
      ;;
    -h | --help) usage; exit 0 ;;
    *) nddev::log "error" "unknown argument"; usage >&2; exit 2 ;;
  esac
done
if [ "$SEEN_APPLY" -eq 1 ] && [ "$SEEN_PLAN" -eq 1 ]; then
  nddev::log "error" "--apply and --plan/--dry-run are mutually exclusive"
  exit 2
fi
export NDDEV_DRY_RUN=$((1 - APPLY))

if [ "$PLATFORM" = "auto" ]; then
  PLATFORM="$(nddev::detect_platform)" || exit 1
fi
case "$PLATFORM" in macos | ubuntu) ;; *) nddev::log "error" "unsupported platform"; exit 2 ;; esac

nddev::require_cmd python3 required || exit 1
nddev::require_cmd curl required || exit 1
nddev::require_cmd node required || exit 1

nddev::bootstrap_destination() {
  local role=$1 path=$2
  python3 -I - "$role" "$path" <<'PY'
import os
import pathlib
import sys

role, path = sys.argv[1:]
if not path or not os.path.isabs(path) or path == "/" or any(ord(char) < 32 or ord(char) == 127 for char in path):
    raise SystemExit(f"{role} must be a non-root absolute path")
parts = pathlib.PurePath(path).parts
if any(part in {".", ".."} for part in parts):
    raise SystemExit(f"{role} must not contain dot traversal components")
if os.path.normpath(path) != path or os.path.realpath(path) != path:
    raise SystemExit(f"{role} must be canonical and must not traverse symlinked parents")
probe = pathlib.Path(path)
while not probe.exists():
    if probe.parent == probe:
        break
    probe = probe.parent
if probe.is_symlink() or not probe.is_dir():
    raise SystemExit(f"{role} nearest existing parent must be a real directory")
if os.path.lexists(path) and (os.path.islink(path) or not os.path.isdir(path)):
    raise SystemExit(f"{role} must be a real directory or absent")
print(path)
PY
}

ROOT="$(nddev::repo_root)"
VERSION_JSON="$ROOT/build/version.json"
APP_VERSION="$(nddev::pinned_app_version)"
CLI_VERSION="$(nddev::pinned_cli_version)"

arch="$(uname -m)"
case "$arch" in
  x86_64 | amd64) arch="x64"; deb_arch="amd64" ;;
  arm64 | aarch64) arch="arm64"; deb_arch="arm64" ;;
  *) nddev::log "error" "unsupported architecture: $arch"; exit 2 ;;
esac

INSTALL_KIND=""
case "$PLATFORM" in
  macos) INSTALL_KIND="dmg"; artifact_key="macos-$arch" ;;
  ubuntu)
    if command -v dpkg >/dev/null 2>&1 \
      && command -v dpkg-deb >/dev/null 2>&1 \
      && command -v dpkg-query >/dev/null 2>&1; then
      INSTALL_KIND="deb"
      artifact_key="linux-$arch-deb"
    else
      INSTALL_KIND="appimage"
      artifact_key="linux-$arch-appimage"
    fi
    ;;
esac

# Load and validate the complete artifact contract in one parse. Tab characters
# are prohibited in all string fields by the validator, making this Bash 3.2
# compatible assignment unambiguous.
artifact_record="$(python3 -I - "$VERSION_JSON" "$artifact_key" "$APP_VERSION" "$deb_arch" <<'PY'
import json
import re
import sys
from urllib.parse import urlparse

path, key, expected_app_version, expected_deb_arch = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    data = json.load(stream)
if not isinstance(data, dict) or data.get("schema") != 2:
    raise SystemExit("build/version.json requires schema 2")
base = data.get("zcode_cdn_base")
parsed = urlparse(base) if isinstance(base, str) else None
if (
    not parsed
    or parsed.scheme != "https"
    or parsed.netloc != "cdn-zcode.z.ai"
    or parsed.hostname != "cdn-zcode.z.ai"
    or parsed.port is not None
    or parsed.path != "/zcode/electron/releases"
    or parsed.params
    or parsed.username
    or parsed.password
    or parsed.query
    or parsed.fragment
):
    raise SystemExit(
        "zcode_cdn_base must be exactly "
        "https://cdn-zcode.z.ai/zcode/electron/releases"
    )
artifacts = data.get("zcode_download_artifacts")
artifact = artifacts.get(key) if isinstance(artifacts, dict) else None
if not isinstance(artifact, dict):
    raise SystemExit(f"missing artifact metadata object: {key}")
filename = artifact.get("filename")
digest = artifact.get("sha512")
size = artifact.get("size_bytes")
if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", filename):
    raise SystemExit(f"invalid artifact filename: {key}")
if "/" in filename or "\\" in filename or any(ord(char) < 32 for char in filename):
    raise SystemExit(f"artifact filename must be a basename: {key}")
cdn_subpath = artifact.get("cdn_subpath")
# A single lowercase path segment (e.g. macos-arm64, linux-x64). It sits between
# the version and the filename in the artifact URL, so it must not smuggle in
# extra path structure or traversal.
if not isinstance(cdn_subpath, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cdn_subpath):
    raise SystemExit(f"artifact cdn_subpath must be a lowercase path segment: {key}")
if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{128}", digest):
    raise SystemExit(f"artifact sha512 must be 128 hexadecimal characters: {key}")
if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 2 * 1024**3:
    raise SystemExit(f"artifact size_bytes must be between 1 byte and 2 GiB: {key}")

team_id = bundle_id = bundle_version = package_name = package_arch = package_version = ""
if key.startswith("macos-"):
    team_id = artifact.get("team_id")
    bundle_id = artifact.get("bundle_id")
    bundle_version = artifact.get("bundle_version")
    app_version = artifact.get("app_version")
    if not isinstance(team_id, str) or not re.fullmatch(r"[A-Z0-9]{10}", team_id):
        raise SystemExit(f"invalid macOS team_id: {key}")
    if not isinstance(bundle_id, str) or not re.fullmatch(r"[A-Za-z0-9.-]+", bundle_id):
        raise SystemExit(f"invalid macOS bundle_id: {key}")
    if app_version != expected_app_version:
        raise SystemExit(f"macOS artifact app_version mismatch: {key}")
    if not isinstance(bundle_version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", bundle_version):
        raise SystemExit(f"invalid macOS bundle_version: {key}")
elif key.endswith("-deb"):
    package_name = artifact.get("package_name")
    package_arch = artifact.get("package_arch")
    package_version = artifact.get("package_version")
    if not isinstance(package_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", package_name):
        raise SystemExit(f"invalid DEB package_name: {key}")
    if package_arch != expected_deb_arch:
        raise SystemExit(f"DEB package_arch mismatch: {key}")
    if not isinstance(package_version, str) or not re.fullmatch(r"[0-9A-Za-z.+:~_-]+", package_version):
        raise SystemExit(f"invalid DEB package_version: {key}")

launcher = data.get("zcode_cli_launcher")
expected_launcher = {
    "macos_entry": "/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs",
    "linux_deb_entry": "/opt/ZCode/resources/glm/zcode.cjs",
    "linux_appimage_entry": "${HOME}/.local/opt/ZCode/resources/glm/zcode.cjs",
    "wrapper_target": "${HOME}/.local/bin/zcode",
}
if launcher != expected_launcher:
    raise SystemExit("zcode_cli_launcher must match the verified launcher contract exactly")

fields = (
    base.rstrip("/"), cdn_subpath, filename, digest.lower(), str(size), team_id, bundle_id,
    bundle_version, package_name, package_arch, package_version,
    launcher["linux_deb_entry"],
)
if any("|" in field or "\n" in field or "\r" in field for field in fields):
    raise SystemExit("artifact metadata contains a forbidden control character")
print("|".join(fields))
PY
)" || exit 1
IFS='|' read -r CDN_BASE CDN_SUBPATH artifact expected_sha512 expected_size TEAM_ID BUNDLE_ID BUNDLE_VERSION PACKAGE_NAME PACKAGE_ARCH PACKAGE_VERSION DEB_CLI_ENTRY <<< "$artifact_record"
url="${CDN_BASE}/${APP_VERSION}/${CDN_SUBPATH}/${artifact}"

python3 -I - "$url" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
if (
    parsed.scheme != "https"
    or not parsed.netloc
    or parsed.username
    or parsed.password
    or parsed.query
    or parsed.fragment
):
    raise SystemExit("artifact URL must remain HTTPS and credential-free")
PY

nddev::section "nddev-zcode-app — verified bootstrap"
nddev::log "info" "mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo 'PLAN (dry-run)')"
nddev::log "info" "platform: $PLATFORM"
nddev::log "info" "architecture: $arch"
nddev::log "info" "install kind: $INSTALL_KIND"
nddev::log "info" "pinned app/CLI: $APP_VERSION / $CLI_VERSION"
nddev::log "info" "artifact: $artifact ($expected_size bytes)"
nddev::log "info" "sha512: $expected_sha512"

nddev::release_bootstrap_locks() {
  local index lock errors=0
  local -a remaining=()
  for ((index=${#BOOTSTRAP_LOCK_PATHS[@]} - 1; index >= 0; index--)); do
    lock="${BOOTSTRAP_LOCK_PATHS[$index]}"
    if [ "$APPLY" -eq 0 ]; then
      printf '[DRY-RUN] release bootstrap lock %q\n' "$lock"
    elif [ -d "$lock" ] && [ ! -L "$lock" ]; then
      if ! nddev::remove_direct_child_tree "$(dirname "$lock")" "$lock"; then
        nddev::log "error" "bootstrap lock cleanup failed; inspect manually: $lock"
        remaining+=("$lock")
        errors=1
      fi
    elif [ -e "$lock" ] || [ -L "$lock" ]; then
      nddev::log "error" "bootstrap lock endpoint changed type; inspect manually: $lock"
      remaining+=("$lock")
      errors=1
    fi
  done
  BOOTSTRAP_LOCK_PATHS=()
  if [ "${#remaining[@]}" -gt 0 ]; then
    BOOTSTRAP_LOCK_PATHS=("${remaining[@]}")
  fi
  return "$errors"
}

nddev::acquire_bootstrap_locks() {
  local lock parent
  BOOTSTRAP_LOCK_PATHS=()
  while IFS= read -r lock; do
    [ -n "$lock" ] || continue
    parent="$(dirname "$lock")"
    nddev::assert_direct_child "$parent" "$lock" || return 1
    if [ "$APPLY" -eq 0 ]; then
      printf '[DRY-RUN] acquire bootstrap lock %q\n' "$lock"
      BOOTSTRAP_LOCK_PATHS+=("$lock")
      continue
    fi
    if [ ! -d "$parent" ] || [ -L "$parent" ]; then
      nddev::log "error" "bootstrap lock parent must be an existing real directory: $parent"
      nddev::release_bootstrap_locks || true
      return 1
    fi
    if ! mkdir -m 700 "$lock" 2>/dev/null; then
      nddev::log "error" "another bootstrap holds or left a stale lock: $lock"
      nddev::log "error" "inspect owner metadata manually only after validating $lock/owner"
      nddev::log "error" "remove a stale lock only after verifying no bootstrap process is active"
      nddev::release_bootstrap_locks || true
      return 1
    fi
    BOOTSTRAP_LOCK_PATHS+=("$lock")
    if ! printf 'pid=%s\nstarted_at=%s\nplatform=%s\n' \
      "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PLATFORM" > "$lock/owner" \
      || ! chmod 600 "$lock/owner"; then
      nddev::log "error" "failed to initialize bootstrap lock: $lock"
      nddev::release_bootstrap_locks || true
      return 1
    fi
  done < <(printf '%s\n' "$@" | LC_ALL=C sort -u)
}

nddev::bootstrap_cleanup() {
  local status=$? cleanup_mode=0 cleanup_failed=0
  trap - EXIT INT TERM HUP
  [ "$BOOTSTRAP_COMMITTED" -eq 1 ] && cleanup_mode=1
  if [ "$BOOTSTRAP_COMMITTED" -ne 1 ] && [ "$status" -eq 0 ]; then
    status=1
  fi
  if ! nddev::cleanup_bootstrap_resources "$cleanup_mode"; then
    cleanup_failed=1
    nddev::log "error" "bootstrap cleanup is incomplete; inspect the recovery paths reported above"
  fi
  [ "$status" -ne 0 ] || status=$cleanup_failed
  exit "$status"
}

nddev::detach_image() {
  local detached=0
  { [ "$MOUNTED" -eq 1 ] || [ "$MOUNT_ATTEMPTED" -eq 1 ]; } && [ -n "$MOUNT_POINT" ] || return 0
  if [ "$MOUNT_TOOL" = "diskutil" ]; then
    if diskutil eject "$MOUNT_POINT" >/dev/null 2>&1 \
      || hdiutil detach "$MOUNT_POINT" >/dev/null 2>&1; then
      detached=1
    fi
  else
    hdiutil detach "$MOUNT_POINT" >/dev/null 2>&1 && detached=1
  fi
  if [ "$detached" -ne 1 ] && [ "$MOUNTED" -ne 1 ] \
    && python3 -I -c 'import os,sys; raise SystemExit(0 if not os.path.ismount(sys.argv[1]) else 1)' \
      "$MOUNT_POINT"; then
    # A failed attach may leave no mount at all. This is a clean no-op, while
    # failure to detach a verified successful mount remains observable.
    detached=1
  fi
  if [ "$detached" -ne 1 ]; then
    nddev::log "error" "failed to detach mounted image; mount is preserved at $MOUNT_POINT"
    return 1
  fi
  MOUNTED=0
  MOUNT_ATTEMPTED=0
  MOUNT_POINT=""
  MOUNT_TOOL=""
}

nddev::bootstrap_identity_preflight() {
  local success=$1

  # Reconcile the application stage rename if a signal arrived between the
  # native rename and the following shell assignment.
  if [ -n "$APP_STAGE_PATH" ]; then
    if nddev::identity_matches "$APP_STAGE_PATH" directory "$APP_STAGE_IDENTITY"; then
      : # Stage rename did not occur.
    elif [ -n "$APP_INSTALLED_PATH" ] \
      && nddev::identity_matches "$APP_INSTALLED_PATH" directory "$APP_STAGE_IDENTITY" \
      && { [ ! -e "$APP_STAGE_PATH" ] && [ ! -L "$APP_STAGE_PATH" ]; }; then
      APP_LIVE_IDENTITY="$APP_STAGE_IDENTITY"
      APP_STAGE_PATH=""
    else
      nddev::log "error" "application stage identity changed; preserving recovery state and bootstrap locks"
      return 1
    fi
  fi

  if [ -n "$APP_OLD_PATH" ]; then
    if nddev::identity_matches "$APP_OLD_PATH" directory "$APP_OLD_IDENTITY"; then
      :
    elif [ "$success" -eq 1 ] && [ -n "$APP_LIVE_IDENTITY" ] \
      && { [ ! -e "$APP_OLD_PATH" ] && [ ! -L "$APP_OLD_PATH" ]; }; then
      # Re-entered committed cleanup after the old app was deleted.
      APP_OLD_PATH=""
      APP_OLD_IDENTITY=""
    elif [ -z "$APP_LIVE_IDENTITY" ] && [ -n "$APP_STAGE_PATH" ] \
      && nddev::identity_matches "$APP_INSTALLED_PATH" directory "$APP_OLD_IDENTITY" \
      && { [ ! -e "$APP_OLD_PATH" ] && [ ! -L "$APP_OLD_PATH" ]; }; then
      # The old-app rename failed before consuming its source.
      APP_OLD_PATH=""
      APP_OLD_IDENTITY=""
      APP_SWAPPED=0
    else
      nddev::log "error" "old application identity changed; preserving recovery state and bootstrap locks"
      return 1
    fi
  fi

  if [ -n "$APP_LIVE_IDENTITY" ]; then
    if ! nddev::identity_matches "$APP_INSTALLED_PATH" directory "$APP_LIVE_IDENTITY"; then
      nddev::log "error" "installed application identity changed; preserving recovery state and bootstrap locks"
      return 1
    fi
  elif [ "$APP_SWAPPED" -eq 1 ]; then
    if [ -z "$APP_STAGE_PATH" ]; then
      nddev::log "error" "application swap state is ambiguous; preserving recovery state and bootstrap locks"
      return 1
    fi
    if [ -e "$APP_INSTALLED_PATH" ] || [ -L "$APP_INSTALLED_PATH" ]; then
      nddev::log "error" "application destination became foreign before commit; preserving recovery state and bootstrap locks"
      return 1
    fi
  fi

  # Apply the same reconciliation and identity contract to the launcher.
  if [ -n "$LAUNCHER_STAGE_PATH" ]; then
    if nddev::identity_matches "$LAUNCHER_STAGE_PATH" regular "$LAUNCHER_STAGE_IDENTITY"; then
      :
    elif nddev::identity_matches "$LAUNCHER_PATH" regular "$LAUNCHER_STAGE_IDENTITY" \
      && { [ ! -e "$LAUNCHER_STAGE_PATH" ] && [ ! -L "$LAUNCHER_STAGE_PATH" ]; }; then
      LAUNCHER_LIVE_IDENTITY="$LAUNCHER_STAGE_IDENTITY"
      LAUNCHER_STAGE_PATH=""
    else
      nddev::log "error" "launcher stage identity changed; preserving recovery state and bootstrap locks"
      return 1
    fi
  fi

  if [ -n "$LAUNCHER_OLD_PATH" ]; then
    if nddev::identity_matches "$LAUNCHER_OLD_PATH" regular "$LAUNCHER_OLD_IDENTITY"; then
      :
    elif [ "$success" -eq 1 ] && [ -n "$LAUNCHER_LIVE_IDENTITY" ] \
      && { [ ! -e "$LAUNCHER_OLD_PATH" ] && [ ! -L "$LAUNCHER_OLD_PATH" ]; }; then
      LAUNCHER_OLD_PATH=""
      LAUNCHER_OLD_IDENTITY=""
    elif [ -z "$LAUNCHER_LIVE_IDENTITY" ] && [ -n "$LAUNCHER_STAGE_PATH" ] \
      && nddev::identity_matches "$LAUNCHER_PATH" regular "$LAUNCHER_OLD_IDENTITY" \
      && { [ ! -e "$LAUNCHER_OLD_PATH" ] && [ ! -L "$LAUNCHER_OLD_PATH" ]; }; then
      LAUNCHER_OLD_PATH=""
      LAUNCHER_OLD_IDENTITY=""
      LAUNCHER_SWAPPED=0
    else
      nddev::log "error" "old launcher identity changed; preserving recovery state and bootstrap locks"
      return 1
    fi
  fi

  if [ -n "$LAUNCHER_LIVE_IDENTITY" ]; then
    if ! nddev::identity_matches "$LAUNCHER_PATH" regular "$LAUNCHER_LIVE_IDENTITY"; then
      nddev::log "error" "installed launcher identity changed; preserving recovery state and bootstrap locks"
      return 1
    fi
  elif [ "$LAUNCHER_SWAPPED" -eq 1 ]; then
    if [ -z "$LAUNCHER_STAGE_PATH" ]; then
      nddev::log "error" "launcher swap state is ambiguous; preserving recovery state and bootstrap locks"
      return 1
    fi
    if [ -e "$LAUNCHER_PATH" ] || [ -L "$LAUNCHER_PATH" ]; then
      nddev::log "error" "launcher destination became foreign before commit; preserving recovery state and bootstrap locks"
      return 1
    fi
  fi
}

nddev::cleanup_bootstrap_swaps() {
  local success=$1 failed_path="" errors=0
  nddev::bootstrap_identity_preflight "$success" || return 1
  if [ "$LAUNCHER_SWAPPED" -eq 1 ]; then
    if [ "$success" -ne 1 ] && [ -n "$LAUNCHER_STAGE_PATH" ] \
      && [ -f "$LAUNCHER_STAGE_PATH" ] && { [ -e "$LAUNCHER_PATH" ] || [ -L "$LAUNCHER_PATH" ]; }; then
      nddev::log "error" "launcher destination became occupied before commit; preserving it and rollback state for inspection"
      errors=1
    elif [ "$success" -eq 1 ]; then
      if [ -n "$LAUNCHER_OLD_PATH" ]; then
        if [ -f "$LAUNCHER_OLD_PATH" ] && [ ! -L "$LAUNCHER_OLD_PATH" ]; then
          if nddev::remove_regular_file "$LAUNCHER_OLD_PATH" "$LAUNCHER_OLD_IDENTITY"; then
            LAUNCHER_OLD_PATH=""
            LAUNCHER_OLD_IDENTITY=""
          else
            nddev::log "error" "committed launcher is safe, but old launcher cleanup failed: $LAUNCHER_OLD_PATH"
            errors=1
          fi
        elif [ -e "$LAUNCHER_OLD_PATH" ] || [ -L "$LAUNCHER_OLD_PATH" ]; then
          nddev::log "error" "old launcher endpoint changed type; inspect manually: $LAUNCHER_OLD_PATH"
          errors=1
        else
          LAUNCHER_OLD_PATH=""
          LAUNCHER_OLD_IDENTITY=""
        fi
      fi
      [ -n "$LAUNCHER_OLD_PATH" ] || LAUNCHER_SWAPPED=0
    else
      if [ -n "$LAUNCHER_OLD_PATH" ] && [ -f "$LAUNCHER_OLD_PATH" ] \
        && [ ! -L "$LAUNCHER_OLD_PATH" ]; then
        failed_path="$(dirname "$LAUNCHER_PATH")/.zcode.launcher.failed.$$"
        if [ -e "$failed_path" ] || [ -L "$failed_path" ]; then
          nddev::log "error" "launcher rollback path collision: $failed_path"
          errors=1
        elif { [ ! -e "$LAUNCHER_PATH" ] && [ ! -L "$LAUNCHER_PATH" ]; } \
          || { [ -f "$LAUNCHER_PATH" ] && [ ! -L "$LAUNCHER_PATH" ] \
            && nddev::rename_noreplace \
              "$LAUNCHER_PATH" "$failed_path" regular "$LAUNCHER_LIVE_IDENTITY"; }; then
          if nddev::rename_noreplace \
            "$LAUNCHER_OLD_PATH" "$LAUNCHER_PATH" regular "$LAUNCHER_OLD_IDENTITY"; then
            LAUNCHER_OLD_PATH=""
            LAUNCHER_OLD_IDENTITY=""
            LAUNCHER_SWAPPED=0
            if [ -f "$failed_path" ] \
              && ! nddev::remove_regular_file "$failed_path" "$LAUNCHER_LIVE_IDENTITY"; then
              nddev::log "error" "launcher rollback succeeded, but failed launcher cleanup did not: $failed_path"
              errors=1
            fi
          else
            nddev::log "error" "failed to restore old launcher from $LAUNCHER_OLD_PATH"
            errors=1
            if [ -f "$failed_path" ] && [ ! -e "$LAUNCHER_PATH" ]; then
              nddev::rename_noreplace \
                "$failed_path" "$LAUNCHER_PATH" regular "$LAUNCHER_LIVE_IDENTITY" \
                || nddev::log "error" "failed launcher remains recoverable at $failed_path"
            fi
          fi
        else
          nddev::log "error" "new launcher endpoint is unsafe or could not be moved for rollback: $LAUNCHER_PATH"
          errors=1
        fi
      elif [ -n "$LAUNCHER_OLD_PATH" ]; then
        nddev::log "error" "old launcher rollback source is missing or unsafe: $LAUNCHER_OLD_PATH"
        errors=1
      elif [ -f "$LAUNCHER_PATH" ] && [ ! -L "$LAUNCHER_PATH" ]; then
        if nddev::remove_regular_file "$LAUNCHER_PATH" "$LAUNCHER_LIVE_IDENTITY"; then
          LAUNCHER_SWAPPED=0
        else
          nddev::log "error" "failed to remove new launcher during rollback: $LAUNCHER_PATH"
          errors=1
        fi
      elif [ -e "$LAUNCHER_PATH" ] || [ -L "$LAUNCHER_PATH" ]; then
        nddev::log "error" "new launcher endpoint changed type during rollback: $LAUNCHER_PATH"
        errors=1
      else
        LAUNCHER_SWAPPED=0
      fi
    fi
  fi
  if [ "$APP_SWAPPED" -eq 1 ]; then
    if [ "$success" -ne 1 ] && [ -n "$APP_STAGE_PATH" ] \
      && [ -d "$APP_STAGE_PATH" ] && { [ -e "$APP_INSTALLED_PATH" ] || [ -L "$APP_INSTALLED_PATH" ]; }; then
      nddev::log "error" "application destination became occupied before commit; preserving it and rollback state for inspection"
      errors=1
    elif [ "$success" -eq 1 ]; then
      if [ -n "$APP_OLD_PATH" ] && [ -d "$APP_OLD_PATH" ] && [ ! -L "$APP_OLD_PATH" ]; then
        if nddev::remove_direct_child_tree \
          "$(dirname "$APP_OLD_PATH")" "$APP_OLD_PATH" "$APP_OLD_IDENTITY"; then
          APP_OLD_PATH=""
          APP_OLD_IDENTITY=""
        else
          nddev::log "error" "committed application is safe, but old application cleanup failed: $APP_OLD_PATH"
          errors=1
        fi
      elif [ -n "$APP_OLD_PATH" ] && { [ -e "$APP_OLD_PATH" ] || [ -L "$APP_OLD_PATH" ]; }; then
        nddev::log "error" "old application endpoint changed type; inspect manually: $APP_OLD_PATH"
        errors=1
      else
        APP_OLD_PATH=""
        APP_OLD_IDENTITY=""
      fi
      [ -n "$APP_OLD_PATH" ] || APP_SWAPPED=0
    elif [ -n "$APP_OLD_PATH" ] && [ -d "$APP_OLD_PATH" ] && [ ! -L "$APP_OLD_PATH" ]; then
      if [ ! -e "$APP_INSTALLED_PATH" ]; then
        if nddev::rename_noreplace \
          "$APP_OLD_PATH" "$APP_INSTALLED_PATH" directory "$APP_OLD_IDENTITY"; then
          APP_OLD_PATH=""
          APP_OLD_IDENTITY=""
          APP_SWAPPED=0
        else
          nddev::log "error" "failed to restore old application from $APP_OLD_PATH"
          errors=1
        fi
      elif [ -L "$APP_INSTALLED_PATH" ] || [ ! -d "$APP_INSTALLED_PATH" ]; then
        nddev::log "error" "installed application endpoint changed type during rollback: $APP_INSTALLED_PATH"
        errors=1
      else
        failed_path="$(dirname "$APP_INSTALLED_PATH")/.nddev-failed-app.$$"
        if [ -e "$failed_path" ] || [ -L "$failed_path" ]; then
          nddev::log "error" "application rollback path collision: $failed_path"
          errors=1
        elif nddev::rename_noreplace \
          "$APP_INSTALLED_PATH" "$failed_path" directory "$APP_LIVE_IDENTITY"; then
          if nddev::rename_noreplace \
            "$APP_OLD_PATH" "$APP_INSTALLED_PATH" directory "$APP_OLD_IDENTITY"; then
            APP_OLD_PATH=""
            APP_OLD_IDENTITY=""
            APP_SWAPPED=0
            if ! nddev::remove_direct_child_tree \
              "$(dirname "$failed_path")" "$failed_path" "$APP_LIVE_IDENTITY"; then
              nddev::log "error" "application rollback succeeded, but failed application cleanup did not: $failed_path"
              errors=1
            fi
          else
            nddev::log "error" "failed to restore old application from $APP_OLD_PATH"
            errors=1
            if [ ! -e "$APP_INSTALLED_PATH" ]; then
              nddev::rename_noreplace \
                "$failed_path" "$APP_INSTALLED_PATH" directory "$APP_LIVE_IDENTITY" \
                || nddev::log "error" "failed application remains recoverable at $failed_path"
            fi
          fi
        else
          nddev::log "error" "failed to move new application aside for rollback: $APP_INSTALLED_PATH"
          errors=1
        fi
      fi
    elif [ -n "$APP_OLD_PATH" ]; then
      nddev::log "error" "old application rollback source is missing or unsafe: $APP_OLD_PATH"
      errors=1
    elif [ -d "$APP_INSTALLED_PATH" ] && [ ! -L "$APP_INSTALLED_PATH" ]; then
      if nddev::remove_direct_child_tree \
        "$(dirname "$APP_INSTALLED_PATH")" "$APP_INSTALLED_PATH" "$APP_LIVE_IDENTITY"; then
        APP_SWAPPED=0
      else
        nddev::log "error" "failed to remove new application during rollback: $APP_INSTALLED_PATH"
        errors=1
      fi
    elif [ -e "$APP_INSTALLED_PATH" ] || [ -L "$APP_INSTALLED_PATH" ]; then
      nddev::log "error" "new application endpoint changed type during rollback: $APP_INSTALLED_PATH"
      errors=1
    else
      APP_SWAPPED=0
    fi
  fi
  if [ -n "$APP_STAGE_PATH" ]; then
    if [ -d "$APP_STAGE_PATH" ] && [ ! -L "$APP_STAGE_PATH" ]; then
      if nddev::remove_direct_child_tree \
        "$(dirname "$APP_STAGE_PATH")" "$APP_STAGE_PATH" "$APP_STAGE_IDENTITY"; then
        APP_STAGE_PATH=""
        APP_STAGE_IDENTITY=""
      else
        nddev::log "error" "failed to remove application staging tree: $APP_STAGE_PATH"
        errors=1
      fi
    elif [ -e "$APP_STAGE_PATH" ] || [ -L "$APP_STAGE_PATH" ]; then
      nddev::log "error" "application staging endpoint changed type: $APP_STAGE_PATH"
      errors=1
    else
      APP_STAGE_PATH=""
      APP_STAGE_IDENTITY=""
    fi
  fi
  if [ -n "$LAUNCHER_STAGE_PATH" ]; then
    if [ -f "$LAUNCHER_STAGE_PATH" ] && [ ! -L "$LAUNCHER_STAGE_PATH" ]; then
      if nddev::remove_regular_file "$LAUNCHER_STAGE_PATH" "$LAUNCHER_STAGE_IDENTITY"; then
        LAUNCHER_STAGE_PATH=""
        LAUNCHER_STAGE_IDENTITY=""
      else
        nddev::log "error" "failed to remove launcher staging file: $LAUNCHER_STAGE_PATH"
        errors=1
      fi
    elif [ -e "$LAUNCHER_STAGE_PATH" ] || [ -L "$LAUNCHER_STAGE_PATH" ]; then
      nddev::log "error" "launcher staging endpoint changed type: $LAUNCHER_STAGE_PATH"
      errors=1
    else
      LAUNCHER_STAGE_PATH=""
      LAUNCHER_STAGE_IDENTITY=""
    fi
  fi
  return "$errors"
}

nddev::cleanup_bootstrap_resources() {
  local success=$1 errors=0 swaps_clean=1
  if { [ "$MOUNTED" -eq 1 ] || [ "$MOUNT_ATTEMPTED" -eq 1 ]; } && [ -n "$MOUNT_POINT" ]; then
    nddev::detach_image || errors=1
  fi
  nddev::cleanup_bootstrap_swaps "$success" || {
    errors=1
    swaps_clean=0
  }
  if [ -n "$TMP_ROOT" ]; then
    if [ "$MOUNTED" -eq 1 ] || [ "$MOUNT_ATTEMPTED" -eq 1 ]; then
      nddev::log "error" "temporary bootstrap root is preserved because its image is still mounted: $TMP_ROOT"
      errors=1
    elif [ -d "$TMP_ROOT" ] && [ ! -L "$TMP_ROOT" ]; then
      if nddev::remove_direct_child_tree "$(dirname "$TMP_ROOT")" "$TMP_ROOT"; then
        TMP_ROOT=""
      else
        nddev::log "error" "failed to remove temporary bootstrap root: $TMP_ROOT"
        errors=1
      fi
    elif [ -e "$TMP_ROOT" ] || [ -L "$TMP_ROOT" ]; then
      nddev::log "error" "temporary bootstrap root changed type; inspect manually: $TMP_ROOT"
      errors=1
    else
      TMP_ROOT=""
    fi
  fi
  if [ "$swaps_clean" -eq 1 ]; then
    nddev::release_bootstrap_locks || errors=1
  elif [ "${#BOOTSTRAP_LOCK_PATHS[@]}" -gt 0 ]; then
    nddev::log "error" "bootstrap locks are preserved because swap recovery is incomplete"
  fi
  return "$errors"
}

if [ "$APPLY" -eq 1 ]; then
  TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/nddev-zcode-bootstrap.XXXXXX")"
  trap 'nddev::bootstrap_cleanup' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
  chmod 700 "$TMP_ROOT"
  downloaded="$TMP_ROOT/$artifact"
else
  downloaded="${TMPDIR:-/tmp}/$artifact"
fi

nddev::sha512_file() {
  python3 -I - "$1" <<'PY'
import hashlib
import sys

digest = hashlib.sha512()
with open(sys.argv[1], "rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
print(digest.hexdigest())
PY
}

nddev::verify_download() {
  local path=$1 actual_size actual_sha
  actual_size="$(wc -c < "$path" | tr -d '[:space:]')"
  if [ "$actual_size" != "$expected_size" ]; then
    nddev::log "error" "artifact size mismatch: expected $expected_size, got $actual_size"
    return 1
  fi
  actual_sha="$(nddev::sha512_file "$path")"
  if [ "$actual_sha" != "$expected_sha512" ]; then
    nddev::log "error" "artifact SHA-512 mismatch: expected $expected_sha512, got $actual_sha"
    return 1
  fi
  nddev::log "ok" "artifact size and SHA-512 verified"
}

nddev::section "Download and verify artifact"
nddev::log "info" "url: $url"
if [ "$APPLY" -eq 0 ]; then
  printf '[DRY-RUN] curl --disable --fail --location --proto =https --proto-redir =https --tlsv1.2 --max-filesize %s --output %q %q\n' "$expected_size" "$downloaded" "$url"
  printf '[DRY-RUN] verify size=%s and sha512=%s\n' "$expected_size" "$expected_sha512"
else
  curl --disable --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --retry 3 --retry-all-errors --connect-timeout 20 --max-filesize "$expected_size" \
    --output "$downloaded" "$url"
  chmod 600 "$downloaded"
  nddev::verify_download "$downloaded"
fi

nddev::macos_identity() {
  local app=$1 actual_version actual_build actual_bundle actual_team details assessment
  [ -d "$app" ] && [ ! -L "$app" ] || { nddev::log "error" "invalid ZCode.app endpoint: $app"; return 1; }
  codesign --verify --deep --strict --verbose=2 "$app" >/dev/null 2>&1 || {
    nddev::log "error" "ZCode.app code signature verification failed"
    return 1
  }
  assessment="$(LC_ALL=C spctl --assess --type execute --verbose=4 "$app" 2>&1)" || {
    nddev::log "error" "ZCode.app Gatekeeper assessment failed"
    return 1
  }
  if ! printf '%s\n' "$assessment" | grep -q '^source=Notarized Developer ID$'; then
    nddev::log "error" "ZCode.app is not accepted as a notarized Developer ID application"
    return 1
  fi
  actual_version="$(/usr/bin/defaults read "$app/Contents/Info" CFBundleShortVersionString 2>/dev/null || true)"
  actual_build="$(/usr/bin/defaults read "$app/Contents/Info" CFBundleVersion 2>/dev/null || true)"
  actual_bundle="$(/usr/bin/defaults read "$app/Contents/Info" CFBundleIdentifier 2>/dev/null || true)"
  details="$(LC_ALL=C codesign -dv --verbose=4 "$app" 2>&1)"
  actual_team="$(printf '%s\n' "$details" | sed -n 's/^TeamIdentifier=//p' | head -1)"
  [ "$actual_version" = "$APP_VERSION" ] || { nddev::log "error" "macOS app version mismatch: $actual_version"; return 1; }
  [ "$actual_build" = "$BUNDLE_VERSION" ] || { nddev::log "error" "macOS bundle version mismatch: $actual_build"; return 1; }
  [ "$actual_bundle" = "$BUNDLE_ID" ] || { nddev::log "error" "macOS bundle identifier mismatch: $actual_bundle"; return 1; }
  [ "$actual_team" = "$TEAM_ID" ] || { nddev::log "error" "macOS Team ID mismatch: $actual_team"; return 1; }
}

nddev::deb_identity() {
  local path=$1 actual_name actual_version actual_arch
  actual_name="$(dpkg-deb -f "$path" Package 2>/dev/null || true)"
  actual_version="$(dpkg-deb -f "$path" Version 2>/dev/null || true)"
  actual_arch="$(dpkg-deb -f "$path" Architecture 2>/dev/null || true)"
  [ "$actual_name" = "$PACKAGE_NAME" ] || { nddev::log "error" "DEB package mismatch: $actual_name"; return 1; }
  [ "$actual_version" = "$PACKAGE_VERSION" ] || { nddev::log "error" "DEB version mismatch: $actual_version"; return 1; }
  [ "$actual_arch" = "$PACKAGE_ARCH" ] || { nddev::log "error" "DEB architecture mismatch: $actual_arch"; return 1; }
  nddev::log "ok" "DEB control metadata verified ($actual_name $actual_version $actual_arch)"
}

nddev::resolve_deb_cli() {
  local package=$1 expected=$2
  dpkg-query -L "$package" 2>/dev/null | python3 -I -c '
import os
import sys

expected = sys.argv[1]
if not os.path.isabs(expected) or os.path.normpath(expected) != expected:
    raise SystemExit("unsafe expected package CLI path")
matches = []
unexpected = []
for raw in sys.stdin:
    path = raw.rstrip("\n")
    if not path.endswith("/resources/glm/zcode.cjs"):
        continue
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise SystemExit("unsafe package CLI path")
    if path == expected:
        matches.append(path)
    else:
        unexpected.append(path)
if unexpected:
    raise SystemExit("package CLI path does not match the verified layout")
if len(matches) != 1:
    raise SystemExit(f"expected one exact package-owned CLI entry, found {len(matches)}")
print(matches[0])
' "$expected"
}

bin_raw="$(nddev::canonical_path "$HOME")/.local/bin"
bin_dir="$(nddev::bootstrap_destination "CLI launcher directory" "$bin_raw")" || exit 2
launcher="$bin_dir/zcode"
LAUNCHER_PATH="$launcher"
if [ "$APPLY" -eq 1 ]; then
  nddev::ensure_dir "$bin_dir"
fi

app_entry=""
case "$INSTALL_KIND" in
  dmg)
    applications_raw="${NDDEV_APPLICATIONS_DIR-/Applications}"
    applications="$(nddev::bootstrap_destination "applications directory" "$applications_raw")" || exit 2
    if [ "$APPLY" -eq 1 ] && [ ! -d "$applications" ]; then
      nddev::log "error" "applications directory must already exist in apply mode: $applications"
      exit 2
    fi
    nddev::acquire_bootstrap_locks \
      "$applications/.ZCode.app.nddev-bootstrap-lock" \
      "$bin_dir/.zcode.nddev-bootstrap-lock" || exit 1
    if [ "$APPLY" -eq 0 ]; then
      printf '[DRY-RUN] hdiutil verify %q\n' "$downloaded"
      printf '[DRY-RUN] mount, verify Team ID %s / bundle %s / versions %s (%s), then atomically install %q\n' \
        "$TEAM_ID" "$BUNDLE_ID" "$APP_VERSION" "$BUNDLE_VERSION" "$applications/ZCode.app"
      app_entry="$applications/ZCode.app/Contents/Resources/glm/zcode.cjs"
    else
      nddev::require_cmd hdiutil required
      nddev::require_cmd codesign required
      nddev::require_cmd spctl required
      nddev::require_cmd ditto required
      hdiutil verify "$downloaded" >/dev/null
      MOUNT_POINT="$TMP_ROOT/mount"
      mkdir -m 700 "$MOUNT_POINT"
      if command -v diskutil >/dev/null 2>&1 && diskutil image attach --help >/dev/null 2>&1; then
        MOUNT_TOOL="diskutil"
        MOUNT_ATTEMPTED=1
        diskutil image attach --readOnly --nobrowse --mountPoint "$MOUNT_POINT" "$downloaded" >/dev/null
      else
        MOUNT_TOOL="hdiutil"
        MOUNT_ATTEMPTED=1
        hdiutil attach "$downloaded" -nobrowse -readonly -mountpoint "$MOUNT_POINT" >/dev/null
      fi
      source_app="$MOUNT_POINT/ZCode.app"
      if [ ! -d "$source_app" ] || [ -L "$source_app" ]; then
        nddev::log "error" "disk image attach returned without the expected application endpoint"
        exit 1
      fi
      MOUNTED=1
      nddev::macos_identity "$source_app"

      installed_app="$applications/ZCode.app"
      stage_app="$applications/.ZCode.app.nddev-stage.$$"
      old_app="$applications/.ZCode.app.nddev-old.$$"
      if [ -e "$stage_app" ] || [ -L "$stage_app" ] \
        || [ -e "$old_app" ] || [ -L "$old_app" ]; then
        nddev::log "error" "macOS install staging collision"
        exit 1
      fi
      if [ -L "$installed_app" ] || { [ -e "$installed_app" ] && [ ! -d "$installed_app" ]; }; then
        nddev::log "error" "existing app endpoint is not a real directory: $installed_app"
        exit 1
      fi
      APP_STAGE_PATH="$stage_app"
      ditto "$source_app" "$stage_app"
      nddev::macos_identity "$stage_app"
      APP_STAGE_IDENTITY="$(nddev::path_identity "$stage_app" directory)" || exit 1
      APP_INSTALLED_PATH="$installed_app"
      if [ -d "$installed_app" ]; then
        APP_OLD_PATH="$old_app"
        APP_OLD_IDENTITY="$(nddev::path_identity "$installed_app" directory)" || exit 1
        APP_SWAPPED=1
        if ! nddev::rename_noreplace \
          "$installed_app" "$old_app" directory "$APP_OLD_IDENTITY"; then
          if [ -d "$installed_app" ] && [ ! -e "$old_app" ]; then
            APP_OLD_PATH=""
            APP_OLD_IDENTITY=""
            APP_SWAPPED=0
          fi
          exit 1
        fi
      fi
      APP_SWAPPED=1
      if ! nddev::rename_noreplace \
        "$stage_app" "$installed_app" directory "$APP_STAGE_IDENTITY"; then
        exit 1
      fi
      APP_LIVE_IDENTITY="$APP_STAGE_IDENTITY"
      APP_STAGE_PATH=""
      APP_SWAPPED=1
      nddev::macos_identity "$installed_app"
      app_entry="$installed_app/Contents/Resources/glm/zcode.cjs"
    fi
    ;;

  deb)
    app_entry="<dpkg-owned>/resources/glm/zcode.cjs"
    nddev::acquire_bootstrap_locks "$bin_dir/.zcode.nddev-bootstrap-lock" || exit 1
    if [ "$APPLY" -eq 0 ]; then
      printf '[DRY-RUN] verify DEB Package=%s Version=%s Architecture=%s CLI=%s\n' "$PACKAGE_NAME" "$PACKAGE_VERSION" "$PACKAGE_ARCH" "$DEB_CLI_ENTRY"
      printf '[DRY-RUN] require successful dpkg --dry-run -i, then install with dpkg -i; errors are fatal (no AppImage fallback)\n'
    else
      nddev::deb_identity "$downloaded"
      deb_extract_root="$TMP_ROOT/deb-extract"
      mkdir -m 700 "$deb_extract_root"
      dpkg-deb -x "$downloaded" "$deb_extract_root"
      preinstall_cli="$deb_extract_root/${DEB_CLI_ENTRY#/}"
      python3 -I - "$deb_extract_root" "$DEB_CLI_ENTRY" <<'PY'
import os
import stat
import sys

root, expected = sys.argv[1:]
expected_relative = expected.lstrip("/")
matches = []
for directory, names, files in os.walk(root, topdown=True, followlinks=False):
    for name in names + files:
        path = os.path.join(directory, name)
        relative = os.path.relpath(path, root)
        if relative.endswith("resources/glm/zcode.cjs"):
            matches.append(relative)
if matches != [expected_relative]:
    raise SystemExit(f"DEB payload CLI layout mismatch: {matches}")
candidate = os.path.join(root, expected_relative)
metadata = os.lstat(candidate)
if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
    raise SystemExit("DEB payload CLI must be one uniquely linked regular file")
PY
      preinstall_cli_version="$(nddev::probe_cli_version node "$preinstall_cli")"
      [ "$preinstall_cli_version" = "$CLI_VERSION" ] \
        || { nddev::log "error" "DEB payload CLI mismatch before install: $preinstall_cli_version"; exit 1; }
      preinstall_cli_sha="$(nddev::sha512_file "$preinstall_cli")"
      nddev::log "ok" "DEB payload exact CLI layout and version verified before install"
      if [ "$(id -u)" -eq 0 ]; then
        dpkg --dry-run -i "$downloaded"
        dpkg -i "$downloaded"
      else
        nddev::require_cmd sudo required
        sudo -- dpkg --dry-run -i "$downloaded"
        sudo -- dpkg -i "$downloaded"
      fi
      installed_version="$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME" 2>/dev/null || true)"
      installed_arch="$(dpkg-query -W -f='${Architecture}' "$PACKAGE_NAME" 2>/dev/null || true)"
      [ "$installed_version" = "$PACKAGE_VERSION" ] || { nddev::log "error" "installed DEB version mismatch: $installed_version"; exit 1; }
      [ "$installed_arch" = "$PACKAGE_ARCH" ] || { nddev::log "error" "installed DEB architecture mismatch: $installed_arch"; exit 1; }
      package_cli="$(nddev::resolve_deb_cli "$PACKAGE_NAME" "$DEB_CLI_ENTRY")" || { nddev::log "error" "installed DEB has no exact package-owned CLI entry"; exit 1; }
      [ -f "$package_cli" ] && [ ! -L "$package_cli" ] || { nddev::log "error" "package-owned CLI entry is missing or unsafe: $package_cli"; exit 1; }
      package_cli_version="$(nddev::probe_cli_version node "$package_cli")"
      [ "$package_cli_version" = "$CLI_VERSION" ] || { nddev::log "error" "installed DEB CLI mismatch: $package_cli_version"; exit 1; }
      installed_cli_sha="$(nddev::sha512_file "$package_cli")"
      [ "$installed_cli_sha" = "$preinstall_cli_sha" ] \
        || { nddev::log "error" "installed DEB CLI differs from the verified payload"; exit 1; }
      app_entry="$package_cli"
    fi
    ;;

  appimage)
    if [ -n "${NDDEV_APPIMAGE_INSTALL_DIR+x}" ]; then
      appimage_raw="$NDDEV_APPIMAGE_INSTALL_DIR"
    else
      appimage_raw="$(nddev::canonical_path "$HOME")/.local/opt/ZCode"
    fi
    appimage_root="$(nddev::bootstrap_destination "AppImage install directory" "$appimage_raw")" || exit 2
    app_parent="$(dirname "$appimage_root")"
    if [ "$APPLY" -eq 1 ]; then
      nddev::ensure_dir "$app_parent"
    fi
    nddev::acquire_bootstrap_locks \
      "$app_parent/.ZCode.nddev-bootstrap-lock" \
      "$bin_dir/.zcode.nddev-bootstrap-lock" || exit 1
    app_entry="$appimage_root/resources/glm/zcode.cjs"
    if [ "$APPLY" -eq 0 ]; then
      printf '[DRY-RUN] extract verified AppImage into same-filesystem stage and atomically install %q\n' "$appimage_root"
    else
      chmod 700 "$downloaded"
      extract_root="$TMP_ROOT/appimage-extract"
      mkdir -m 700 "$extract_root"
      (cd "$extract_root" && "$downloaded" --appimage-extract >/dev/null)
      extracted="$extract_root/squashfs-root"
      extracted_entry="$extracted/resources/glm/zcode.cjs"
      [ -f "$extracted_entry" ] || { nddev::log "error" "AppImage does not contain the expected CLI entry"; exit 1; }
      embedded_cli="$(nddev::probe_cli_version node "$extracted_entry")"
      [ "$embedded_cli" = "$CLI_VERSION" ] || { nddev::log "error" "AppImage embedded CLI mismatch: $embedded_cli"; exit 1; }

      if [ -L "$appimage_root" ] || { [ -e "$appimage_root" ] && [ ! -d "$appimage_root" ]; }; then
        nddev::log "error" "existing AppImage install root is not a real directory"
        exit 1
      fi
      app_stage="$(mktemp -d "$app_parent/.ZCode.stage.XXXXXX")"
      APP_STAGE_PATH="$app_stage"
      chmod 700 "$app_stage"
      cp -R "$extracted/." "$app_stage/"
      cp "$downloaded" "$app_stage/ZCode.AppImage"
      chmod 700 "$app_stage/ZCode.AppImage"
      printf '%s\n' "$APP_VERSION" > "$app_stage/.nddev-app-version"
      chmod 600 "$app_stage/.nddev-app-version"
      APP_STAGE_IDENTITY="$(nddev::path_identity "$app_stage" directory)" || exit 1
      app_old="$app_parent/.ZCode.old.$$"
      [ ! -e "$app_old" ] && [ ! -L "$app_old" ] || { nddev::log "error" "AppImage rollback path collision"; exit 1; }
      APP_INSTALLED_PATH="$appimage_root"
      if [ -d "$appimage_root" ]; then
        APP_OLD_PATH="$app_old"
        APP_OLD_IDENTITY="$(nddev::path_identity "$appimage_root" directory)" || exit 1
        APP_SWAPPED=1
        if ! nddev::rename_noreplace \
          "$appimage_root" "$app_old" directory "$APP_OLD_IDENTITY"; then
          if [ -d "$appimage_root" ] && [ ! -e "$app_old" ]; then
            APP_OLD_PATH=""
            APP_OLD_IDENTITY=""
            APP_SWAPPED=0
          fi
          exit 1
        fi
      fi
      APP_SWAPPED=1
      if ! nddev::rename_noreplace \
        "$app_stage" "$appimage_root" directory "$APP_STAGE_IDENTITY"; then
        exit 1
      fi
      APP_LIVE_IDENTITY="$APP_STAGE_IDENTITY"
      APP_STAGE_PATH=""
      APP_SWAPPED=1
      app_entry="$appimage_root/resources/glm/zcode.cjs"
    fi
    ;;
esac

nddev::section "Wire exact CLI launcher"
if [ "$APPLY" -eq 0 ]; then
  printf '[DRY-RUN] atomically write launcher %q -> %q\n' "$launcher" "$app_entry"
else
  [ -f "$app_entry" ] && [ ! -L "$app_entry" ] || { nddev::log "error" "installed CLI entry missing or unsafe: $app_entry"; exit 1; }
  if [ -L "$launcher" ] || { [ -e "$launcher" ] && [ ! -f "$launcher" ]; }; then
    nddev::log "error" "refusing to replace unsafe launcher endpoint: $launcher"
    exit 1
  fi
  launcher_tmp="$(mktemp "$bin_dir/.zcode.launcher.XXXXXX")"
  LAUNCHER_STAGE_PATH="$launcher_tmp"
  app_entry_quoted="$(printf '%q' "$app_entry")"
  # shellcheck disable=SC2016 # launcher variables expand when the generated script runs.
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    "ZCODE_CJS=$app_entry_quoted" \
    '[ -f "$ZCODE_CJS" ] || { echo "zcode: managed entry is missing: $ZCODE_CJS" >&2; exit 127; }' \
    'exec node "$ZCODE_CJS" "$@"' > "$launcher_tmp"
  chmod 755 "$launcher_tmp"
  LAUNCHER_STAGE_IDENTITY="$(nddev::path_identity "$launcher_tmp" regular)" || exit 1
  launcher_old="$bin_dir/.zcode.launcher.old.$$"
  [ ! -e "$launcher_old" ] && [ ! -L "$launcher_old" ] || { nddev::log "error" "launcher rollback path collision"; exit 1; }
  if [ -f "$launcher" ]; then
    LAUNCHER_OLD_PATH="$launcher_old"
    LAUNCHER_OLD_IDENTITY="$(nddev::path_identity "$launcher" regular)" || exit 1
    LAUNCHER_SWAPPED=1
    if ! nddev::rename_noreplace \
      "$launcher" "$launcher_old" regular "$LAUNCHER_OLD_IDENTITY"; then
      if [ -f "$launcher" ] && [ ! -e "$launcher_old" ]; then
        LAUNCHER_OLD_PATH=""
        LAUNCHER_OLD_IDENTITY=""
        LAUNCHER_SWAPPED=0
      fi
      exit 1
    fi
  fi
  LAUNCHER_SWAPPED=1
  if ! nddev::rename_noreplace \
    "$launcher_tmp" "$launcher" regular "$LAUNCHER_STAGE_IDENTITY"; then
    exit 1
  fi
  LAUNCHER_LIVE_IDENTITY="$LAUNCHER_STAGE_IDENTITY"
  LAUNCHER_STAGE_PATH=""
fi

nddev::section "Strict postconditions"
if [ "$APPLY" -eq 0 ]; then
  nddev::log "info" "plan will require exact app $APP_VERSION, CLI $CLI_VERSION, entrypoint, and platform identity"
else
  if [ -n "$APP_LIVE_IDENTITY" ] \
    && ! nddev::identity_matches "$APP_INSTALLED_PATH" directory "$APP_LIVE_IDENTITY"; then
    nddev::log "error" "installed application identity changed before postconditions"
    exit 1
  fi
  if ! nddev::identity_matches "$LAUNCHER_PATH" regular "$LAUNCHER_LIVE_IDENTITY"; then
    nddev::log "error" "installed launcher identity changed before postconditions"
    exit 1
  fi
  [ -f "$app_entry" ] && [ ! -L "$app_entry" ] || { nddev::log "error" "entrypoint postcondition failed"; exit 1; }
  case "$INSTALL_KIND" in
    dmg) nddev::macos_identity "$applications/ZCode.app" ;;
    deb)
      final_deb_version="$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME" 2>/dev/null || true)"
      final_deb_arch="$(dpkg-query -W -f='${Architecture}' "$PACKAGE_NAME" 2>/dev/null || true)"
      [ "$final_deb_version" = "$PACKAGE_VERSION" ] && [ "$final_deb_arch" = "$PACKAGE_ARCH" ] \
        || { nddev::log "error" "DEB identity postcondition failed"; exit 1; }
      ;;
    appimage)
      [ "$(sed -n '1p' "$appimage_root/.nddev-app-version" 2>/dev/null || true)" = "$APP_VERSION" ] \
        || { nddev::log "error" "AppImage version postcondition failed"; exit 1; }
      ;;
  esac
  detected_cli="$(nddev::detect_cli_version_at "$launcher")"
  [ "$detected_cli" = "$CLI_VERSION" ] || { nddev::log "error" "CLI postcondition failed: $detected_cli"; exit 1; }
  nddev::log "ok" "ZCode app $APP_VERSION and CLI $CLI_VERSION verified exactly"
fi

if [ "$APPLY" -eq 1 ]; then
  # Postconditions define the commit point. Cleanup after this point may fail
  # visibly, but it must never roll back the verified launcher/application.
  BOOTSTRAP_COMMITTED=1
  if ! nddev::cleanup_bootstrap_resources 1; then
    trap - EXIT INT TERM HUP
    nddev::log "error" "bootstrap committed safely, but cleanup is incomplete; command reports failure"
    exit 1
  fi
  trap - EXIT INT TERM HUP
else
  nddev::release_bootstrap_locks
fi

nddev::section "Bootstrap complete"
nddev::log "info" "next: install.sh install --marketplace <name> --apply"
