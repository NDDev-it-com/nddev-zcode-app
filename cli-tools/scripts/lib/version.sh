#!/usr/bin/env bash
# Version helpers for the nddev-zcode-app installer.

nddev::version_field() {
  local key=$1 root version_json
  root="$(nddev::repo_root)"
  version_json="$root/build/version.json"
  if [ ! -f "$version_json" ]; then
    nddev::log "error" "missing build/version.json"
    return 1
  fi
  python3 -I - "$version_json" "$key" <<'PY'
import json
import sys

path, key = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    data = json.load(stream)
if not isinstance(data, dict) or key not in data:
    raise SystemExit(f"missing build/version.json field: {key}")
value = data[key]
if not isinstance(value, str):
    raise SystemExit(f"build/version.json field must be a string: {key}")
print(value)
PY
}

nddev::build_version() {
  local value
  value="$(nddev::version_field build_version)" || return 1
  nddev::is_semver "$value" || { nddev::log "error" "invalid build_version: $value"; return 1; }
  printf '%s\n' "$value"
}

nddev::pinned_app_version() {
  local value
  value="$(nddev::version_field zcode_app_version)" || return 1
  nddev::is_semver "$value" || { nddev::log "error" "invalid zcode_app_version: $value"; return 1; }
  printf '%s\n' "$value"
}

nddev::pinned_cli_version() {
  local value
  value="$(nddev::version_field zcode_cli_version)" || return 1
  nddev::is_semver "$value" || { nddev::log "error" "invalid zcode_cli_version: $value"; return 1; }
  printf '%s\n' "$value"
}

nddev::zcode_runtime() {
  local value
  value="$(nddev::version_field zcode_runtime)" || return 1
  [ -n "$value" ] || { nddev::log "error" "zcode_runtime is empty"; return 1; }
  printf '%s\n' "$value"
}

nddev::linux_deb_contract() {
  local root machine key
  root="$(nddev::repo_root)"
  machine="$(uname -m)"
  case "$machine" in
    x86_64 | amd64) key="linux-x64-deb" ;;
    arm64 | aarch64) key="linux-arm64-deb" ;;
    *) return 1 ;;
  esac
  python3 -I - "$root/build/version.json" "$key" <<'PY'
import json
import re
import sys

path, key = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    data = json.load(stream)
artifact = data.get("zcode_download_artifacts", {}).get(key, {})
name = artifact.get("package_name")
version = artifact.get("package_version")
if data.get("schema") != 2:
    raise SystemExit("unsupported artifact schema")
if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name):
    raise SystemExit("invalid pinned DEB package name")
if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+:~_-]+", version):
    raise SystemExit("invalid pinned DEB package version")
print(f"{name}|{version}")
PY
}

nddev::detect_app_version() {
  local app plist applications detected contract package_name expected_package_version package_record package_status installed_version marker
  case "$(uname -s)" in
    Darwin)
      applications="${NDDEV_APPLICATIONS_DIR:-/Applications}"
      for app in "$applications/ZCode.app" "$HOME/Applications/ZCode.app"; do
        plist="$app/Contents/Info.plist"
        if [ -d "$app" ] && [ ! -L "$app" ] && [ -f "$plist" ] && [ ! -L "$plist" ]; then
          detected="$(/usr/bin/defaults read "$app/Contents/Info" CFBundleShortVersionString 2>/dev/null || true)"
          if nddev::is_semver "$detected"; then
            printf '%s\n' "$detected"
            return 0
          fi
        fi
      done
      ;;
    *)
      contract="$(nddev::linux_deb_contract 2>/dev/null || true)"
      if [ -n "$contract" ] && command -v dpkg-query >/dev/null 2>&1; then
        package_name="${contract%%|*}"
        expected_package_version="${contract#*|}"
        package_record="$(dpkg-query -W -f='${Status}|${Version}' "$package_name" 2>/dev/null || true)"
        package_status="${package_record%%|*}"
        installed_version="${package_record#*|}"
        if [ "$package_status" = "install ok installed" ]; then
          if [ "$installed_version" = "$expected_package_version" ]; then
            nddev::pinned_app_version
          elif printf '%s\n' "$installed_version" | grep -qE '^[0-9A-Za-z.+:~_-]+$'; then
            printf 'deb:%s\n' "$installed_version"
          else
            printf 'deb:invalid\n'
          fi
          return 0
        fi
      fi
      marker="${NDDEV_APPIMAGE_INSTALL_DIR:-$HOME/.local/opt/ZCode}/.nddev-app-version"
      if [ -f "$marker" ] && [ ! -L "$marker" ]; then
        detected="$(sed -n '1p' "$marker")"
        nddev::is_semver "$detected" && printf '%s\n' "$detected" || printf 'appimage:invalid\n'
        return 0
      fi
      ;;
  esac
  printf 'unknown\n'
}

nddev::parse_cli_version() {
  local value=$1
  value="$(printf '%s\n' "$value" | head -1 | sed 's/^v//; s/^[^0-9]*//')"
  nddev::is_semver "$value" && printf '%s\n' "$value" || printf 'unknown\n'
}

nddev::probe_cli_version() {
  local output
  [ "$#" -gt 0 ] || { printf 'unknown\n'; return 0; }
  output="$(python3 -I - "$@" <<'PY'
import os
import resource
import signal
import subprocess
import sys
import tempfile

command = sys.argv[1:]
limit = 64 * 1024
timeout = 3

def constrain_output():
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))

try:
    with tempfile.TemporaryDirectory(prefix="nddev-zcode-probe-") as probe_home, tempfile.TemporaryFile() as output:
        xdg_config = os.path.join(probe_home, "config")
        xdg_cache = os.path.join(probe_home, "cache")
        xdg_data = os.path.join(probe_home, "data")
        xdg_state = os.path.join(probe_home, "state")
        for directory in (xdg_config, xdg_cache, xdg_data, xdg_state):
            os.mkdir(directory, 0o700)
        child_env = {
            "HOME": probe_home,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TMPDIR": probe_home,
            "XDG_CONFIG_HOME": xdg_config,
            "XDG_CACHE_HOME": xdg_cache,
            "XDG_DATA_HOME": xdg_data,
            "XDG_STATE_HOME": xdg_state,
        }
        for key in ("LANG", "LC_ALL", "LC_CTYPE", "TZ"):
            value = os.environ.get(key)
            if value:
                child_env[key] = value
        process = subprocess.Popen(
            [*command, "--version"],
            cwd=probe_home,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=constrain_output,
        )
        timed_out = False
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            returncode = process.wait()
        # The launcher may have forked a background descendant and exited.
        # Always terminate the dedicated process group before returning.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output.seek(0)
        captured = output.read(limit + 1)
except (OSError, subprocess.SubprocessError):
    print("unknown")
    raise SystemExit(0)

if timed_out or returncode != 0 or len(captured) > limit:
    print("unknown")
else:
    print(captured.decode("utf-8", errors="replace").splitlines()[0] if captured else "unknown")
PY
)" || output="unknown"
  nddev::parse_cli_version "$output"
}

nddev::detect_cli_version() {
  local executable
  executable="$(python3 -I - <<'PY'
import os
import shutil

path = shutil.which("zcode")
if path:
    path = os.path.realpath(path)
    if os.path.isfile(path) and os.access(path, os.X_OK):
        print(path)
PY
)"
  if [ -z "$executable" ]; then
    printf 'not-installed\n'
    return 0
  fi
  nddev::probe_cli_version "$executable"
}

nddev::detect_cli_version_at() {
  local launcher=$1
  if [ -x "$launcher" ] && [ ! -L "$launcher" ]; then
    nddev::probe_cli_version "$launcher"
  else
    printf 'not-installed\n'
  fi
}

# Advisory by default; pass "strict" for bootstrap postconditions.
nddev::check_runtime_version() {
  local mode=${1:-advisory}
  local pinned_app pinned_cli running_app running_cli failures=0

  pinned_app="$(nddev::pinned_app_version)" || return 1
  pinned_cli="$(nddev::pinned_cli_version)" || return 1
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

  if [ "$running_app" != "$pinned_app" ]; then
    nddev::log "warn" "ZCode app $running_app != pinned $pinned_app"
    failures=$((failures + 1))
  fi
  if [ "$running_cli" != "$pinned_cli" ]; then
    nddev::log "warn" "ZCode CLI $running_cli != pinned $pinned_cli"
    failures=$((failures + 1))
  fi
  if [ "$failures" -eq 0 ]; then
    nddev::log "ok" "running ZCode matches pinned baseline"
  elif [ "$mode" = "strict" ]; then
    nddev::log "error" "runtime postconditions failed"
    return 1
  fi
}

nddev::write_version_stamp() {
  local target=$1 platform=$2 setup_id=$3
  local build_version zcode_runtime installed_at app_ver cli_ver
  case "$platform" in macos | ubuntu) ;; *) nddev::log "error" "invalid platform: $platform"; return 2 ;; esac
  if ! printf '%s\n' "$setup_id" | grep -qE '^[a-z0-9][a-z0-9-]*$'; then
    nddev::log "error" "invalid setup id: $setup_id"
    return 2
  fi

  build_version="$(nddev::build_version)" || return 1
  zcode_runtime="$(nddev::zcode_runtime)" || return 1
  app_ver="$(nddev::pinned_app_version)" || return 1
  cli_ver="$(nddev::pinned_cli_version)" || return 1
  installed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] write BUILD-VERSION -> %q\n' "$target/BUILD-VERSION"
    return 0
  fi

  python3 -I - "$target/BUILD-VERSION" "$build_version" "$app_ver" "$cli_ver" "$zcode_runtime" "$platform" "$setup_id" "$installed_at" <<'PY' || return 1
import json
import os
import sys
import tempfile

path, build, app, cli, runtime, platform, setup_id, installed = sys.argv[1:]
payload = {
    "schema": 2,
    "setup_id": setup_id,
    "build_version": build,
    "zcode_app_version": app,
    "zcode_cli_version": cli,
    "zcode_runtime": runtime,
    "platform": platform,
    "installed_at": installed,
}
fd, temporary = tempfile.mkstemp(prefix=".nddev-stamp.", dir=os.path.dirname(path), text=True)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
  chmod 600 "$target/BUILD-VERSION" || return 1
  nddev::stamp_version "$target" >/dev/null || return 1
  nddev::log "ok" "wrote BUILD-VERSION ($build_version, setup $setup_id, $platform, zcode $app_ver)"
}
