#!/usr/bin/env bash
# Version helpers for the nddev-zcode-app installer.
# Reads the build version from build/version.json and writes the BUILD-VERSION
# stamp into the target ~/.zcode directory.

# Read the build version string from build/version.json.
nddev::build_version() {
  local root version_json
  root="$(nddev::repo_root)"
  version_json="$root/build/version.json"
  if [ ! -f "$version_json" ]; then
    nddev::log "error" "missing build/version.json"
    return 1
  fi
  python3 -c "import json; print(json.load(open('$version_json'))['build_version'])"
}

# Read the ZCode runtime baseline from build/version.json.
nddev::zcode_runtime() {
  local root version_json
  root="$(nddev::repo_root)"
  version_json="$root/build/version.json"
  python3 -c "import json; print(json.load(open('$version_json')).get('zcode_runtime','unknown'))" 2>/dev/null \
    || printf 'unknown'
}

# Write the BUILD-VERSION stamp into the target zcode home. $1=target ~/.zcode path.
nddev::write_version_stamp() {
  local target=$1
  local build_version zcode_runtime platform installed_at

  build_version="$(nddev::build_version)"
  zcode_runtime="$(nddev::zcode_runtime)"
  platform="$(nddev::detect_platform)"
  installed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] write BUILD-VERSION -> %q\n' "$target/BUILD-VERSION"
    return 0
  fi

  cat > "$target/BUILD-VERSION" <<EOF
{
  "build_version": "$build_version",
  "zcode_runtime": "$zcode_runtime",
  "platform": "$platform",
  "installed_at": "$installed_at"
}
EOF
  nddev::log "ok" "wrote BUILD-VERSION ($build_version, $platform)"
}
