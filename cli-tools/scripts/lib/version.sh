#!/usr/bin/env bash
# Version helpers for the nddev-zcode-app installer.
# Reads the build version from build/version.json and writes the BUILD-VERSION
# stamp into the target ~/.zcode directory. Also checks the running ZCode
# version against the pinned baseline and warns on mismatch.

# Read a field from build/version.json. $1 = key.
nddev::version_field() {
  local key=$1
  local root version_json
  root="$(nddev::repo_root)"
  version_json="$root/build/version.json"
  if [ ! -f "$version_json" ]; then
    nddev::log "error" "missing build/version.json"
    return 1
  fi
  python3 -c "import json,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2],'unknown'); print(v)" "$version_json" "$key" 2>/dev/null \
    || printf 'unknown'
}

# Read the build version string from build/version.json.
nddev::build_version() {
  nddev::version_field build_version
}

# Read the pinned ZCode app version from build/version.json.
nddev::pinned_app_version() {
  nddev::version_field zcode_app_version
}

# Read the pinned ZCode CLI version from build/version.json.
nddev::pinned_cli_version() {
  nddev::version_field zcode_cli_version
}

# Read the ZCode runtime baseline from build/version.json.
nddev::zcode_runtime() {
  nddev::version_field zcode_runtime
}

# Detect the RUNNING ZCode desktop app version.
# macOS: reads CFBundleShortVersionString from /Applications/ZCode.app.
# Linux: not detectable (no standard install path) — returns "unknown".
nddev::detect_app_version() {
  local plist
  case "$(uname -s)" in
    Darwin)
      # Check common locations.
      for app in "/Applications/ZCode.app" "$HOME/Applications/ZCode.app"; do
        plist="$app/Contents/Info.plist"
        if [ -f "$plist" ]; then
          /usr/bin/defaults read "$app/Contents/Info" CFBundleShortVersionString 2>/dev/null && return 0
        fi
      done
      printf 'unknown'
      ;;
    *)
      printf 'unknown'
      ;;
  esac
}

# Detect the RUNNING ZCode CLI version (if the `zcode` binary is on PATH).
nddev::detect_cli_version() {
  if command -v zcode >/dev/null 2>&1; then
    local ver
    ver="$(zcode --version 2>/dev/null | head -1 | sed 's/^v//; s/^[^0-9]*//' || true)"
    # M3: sed exits 0 even when it produces an empty string (non-numeric first
    # line). Default to "unknown" so check_runtime_version doesn't emit a
    # spurious mismatch warning with an empty version.
    [ -z "$ver" ] && ver='unknown'
    printf '%s\n' "$ver"
  else
    printf 'not-installed\n'
  fi
}

# Compare the running ZCode against the pinned baseline. Warns (does not fail)
# on mismatch — a newer ZCode may work, but this build was verified against the
# pin. Returns 0 always (advisory).
nddev::check_runtime_version() {
  local pinned_app pinned_cli running_app running_cli warnings=0

  pinned_app="$(nddev::pinned_app_version)"
  pinned_cli="$(nddev::pinned_cli_version)"

  nddev::section "ZCode version check"
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    nddev::log "info" "pinned app:  $pinned_app    running: skipped-plan"
    nddev::log "info" "pinned cli:  $pinned_cli    running: skipped-plan"
    nddev::log "info" "live runtime detection is skipped in plan mode"
    return 0
  fi

  running_app="$(nddev::detect_app_version)"
  running_cli="$(nddev::detect_cli_version)"

  nddev::log "info" "pinned app:  $pinned_app    running: $running_app"
  nddev::log "info" "pinned cli:  $pinned_cli    running: $running_cli"

  if [ "$running_app" != "unknown" ] && [ "$running_app" != "$pinned_app" ]; then
    nddev::log "warn" "ZCode app $running_app != pinned $pinned_app — this build was verified against $pinned_app; a different version may break."
    warnings=$((warnings + 1))
  fi
  if [ "$running_cli" != "not-installed" ] && [ "$running_cli" != "unknown" ] && [ "$running_cli" != "$pinned_cli" ]; then
    nddev::log "warn" "ZCode CLI $running_cli != pinned $pinned_cli — this build was verified against $pinned_cli."
    warnings=$((warnings + 1))
  fi

  if [ "$warnings" -eq 0 ]; then
    nddev::log "ok" "running ZCode matches pinned baseline"
  fi
  return 0
}

# Write the BUILD-VERSION stamp into the target ZCode home.
# $1 = target path, $2 = selected installer platform (macos|ubuntu).
nddev::write_version_stamp() {
  local target=$1
  local platform=$2
  local build_version zcode_runtime installed_at app_ver cli_ver

  case "$platform" in
    macos | ubuntu) ;;
    *)
      nddev::log "error" "invalid platform for BUILD-VERSION: $platform"
      return 2
      ;;
  esac

  build_version="$(nddev::build_version)"
  zcode_runtime="$(nddev::zcode_runtime)"
  app_ver="$(nddev::pinned_app_version)"
  cli_ver="$(nddev::pinned_cli_version)"
  installed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] write BUILD-VERSION -> %q\n' "$target/BUILD-VERSION"
    return 0
  fi

  cat > "$target/BUILD-VERSION" <<EOF
{
  "build_version": "$build_version",
  "zcode_app_version": "$app_ver",
  "zcode_cli_version": "$cli_ver",
  "zcode_runtime": "$zcode_runtime",
  "platform": "$platform",
  "installed_at": "$installed_at"
}
EOF
  nddev::log "ok" "wrote BUILD-VERSION ($build_version, $platform, zcode $app_ver)"
}
