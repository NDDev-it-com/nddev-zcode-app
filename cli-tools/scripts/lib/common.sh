#!/usr/bin/env bash
# Shared helpers for the nddev-zcode-app installer.
# Sourced by install.sh and the macos/ubuntu runners.
# Conventions mirror rldyour-new-mac-or-ubuntu: set -euo pipefail at the caller,
# NDDEV_DRY_RUN=1 means plan (no writes), NDDEV_DRY_RUN=0 means apply.

# Resolve the repository root (three levels up from this file:
# lib/ -> scripts/ -> cli-tools/ -> repo root).
nddev::repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s\n' "$(cd "$script_dir/../../.." && pwd)"
}

nddev::log() {
  local level=$1
  shift
  printf '[%s] %s\n' "$level" "$*"
}

nddev::section() {
  printf '\n==> %s\n' "$*"
}

# Run a command unless in dry-run mode. In dry-run, print what would run.
nddev::run() {
  local -a cmd=("$@")
  local rendered
  rendered=$(printf " %q" "${cmd[@]}")
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] %s\n' "${rendered# }"
    return 0
  fi
  "${cmd[@]}"
}

# Require a command on PATH. Level: required | optional.
nddev::require_cmd() {
  local name=$1
  local level=${2:-required}
  if command -v "$name" >/dev/null 2>&1; then
    nddev::log "ok" "$name on PATH"
    return 0
  fi
  if [ "$level" = "required" ]; then
    nddev::log "missing" "required command not found: $name"
    return 1
  fi
  nddev::log "warn" "optional command not found: $name"
  return 0
}

# Ensure a directory exists (mkdir -p), honoring dry-run.
nddev::ensure_dir() {
  local dir=$1
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] mkdir -p %q\n' "$dir"
    return 0
  fi
  mkdir -p "$dir"
}

# Copy a file or directory tree, honoring dry-run. $1=src $2=dest.
nddev::copy() {
  local src=$1 dest=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] cp -R %q %q\n' "$src" "$dest"
    return 0
  fi
  cp -R "$src" "$dest"
}

# Move a path, honoring dry-run. $1=src $2=dest.
nddev::move() {
  local src=$1 dest=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] mv %q %q\n' "$src" "$dest"
    return 0
  fi
  mv "$src" "$dest"
}

# Detect the platform: darwin -> macos, linux -> ubuntu.
nddev::detect_platform() {
  case "$(uname -s)" in
    Darwin) printf 'macos\n' ;;
    Linux) printf 'ubuntu\n' ;;
    *) nddev::log "error" "Unsupported OS: $(uname -s)"; return 1 ;;
  esac
}

# Read the current installed build version from ~/.zcode/BUILD-VERSION, or "unknown".
nddev::current_version() {
  local stamp="$HOME/.zcode/BUILD-VERSION"
  if [ -f "$stamp" ]; then
    python3 -c "import json,sys; print(json.load(open('$stamp')).get('build_version','unknown'))" 2>/dev/null \
      || printf 'unknown'
  else
    printf 'unknown'
  fi
}

# Compute today's date in DD.MM.YYYY.
nddev::today() {
  date +%d.%m.%Y
}

# Compute the next backup directory name: <N>-<DD.MM.YYYY>-<VERSION>-old.zcode
# N is a 1-9 rotation index: the lowest free slot (1..9). If all 1..9 are taken,
# reuse the oldest existing backup's slot (overwrite).
nddev::backup_name() {
  local version=$1
  local backups_dir="$HOME/.zcode-backups"
  local today slot i existing

  today="$(nddev::today)"

  # Find the lowest free slot 1..9.
  slot=""
  for i in $(seq 1 9); do
    existing="$(find "$backups_dir" -maxdepth 1 -name "${i}-*-old.zcode" 2>/dev/null | head -1)"
    if [ -z "$existing" ]; then
      slot=$i
      break
    fi
  done

  # If no free slot, reuse the oldest (lowest mtime) — its slot number is reused.
  if [ -z "$slot" ]; then
    local oldest
    oldest="$(find "$backups_dir" -maxdepth 1 -name "*-old.zcode" -print0 2>/dev/null \
      | xargs -0 stat -f '%m %N' 2>/dev/null | sort -n | head -1 | sed 's/.*\///')"
    slot="${oldest%%-*}"
    [ -z "$slot" ] && slot=1
  fi

  printf '%s-%s-%s-old.zcode\n' "$slot" "$today" "$version"
}

# Render a JSON template by substituting ${VAR} placeholders from the environment
# (loaded from build/.env). Writes the rendered file. $1=template $2=dest.
# Uses python3 so escaping is safe. Unknown placeholders are left as-is.
nddev::render_template() {
  local template=$1 dest=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] render %q -> %q (substitute ${VAR} from env)\n' "$template" "$dest"
    return 0
  fi
  python3 - "$template" "$dest" <<'PY'
import json
import os
import re
import sys

template_path, dest_path = sys.argv[1], sys.argv[2]

with open(template_path, "r", encoding="utf-8") as f:
    raw = f.read()

# Read build/.env if present and export into os.environ for substitution.
env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(template_path))), "build", ".env")
if os.path.isfile(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

def repl(match):
    var = match.group(1)
    return os.environ.get(var, match.group(0))

rendered = re.sub(r"\$\{([A-Z0-9_]+)\}", repl, raw)

# Strip the leading "_comment" key so the rendered file is clean runtime config.
try:
    data = json.loads(rendered)
    data.pop("_comment", None)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
except json.JSONDecodeError:
    # Not JSON (or intentionally not JSON): write the rendered text as-is.
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(rendered)
PY
}

# Validate that a file is well-formed JSON. Returns non-zero on failure.
nddev::validate_json() {
  local path=$1
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$path"
}
