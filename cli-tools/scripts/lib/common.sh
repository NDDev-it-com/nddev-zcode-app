#!/usr/bin/env bash
# Shared helpers for the nddev-zcode-app installer.
# Callers enable strict shell mode. NDDEV_DRY_RUN=1 means plan (no writes), and
# NDDEV_DRY_RUN=0 means apply.

# Runtime configuration and restored credentials are private by default. Each
# copied executable keeps its source mode, while newly created files cannot be
# group- or world-readable.
umask 077

# Single Python-compatible SemVer 2.0.0 grammar for every version consumer.
readonly NDDEV_SEMVER_PATTERN='(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'

nddev::repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s\n' "$(cd "$script_dir/../../.." && pwd)"
}

# Load build/.env without evaluating shell syntax. Existing environment values
# win. `paths-only` imports only the two documented path keys. `full` also
# imports variables referenced by the already validated marketplace JSON.
nddev::parse_env_file() {
  local path=$1 expected_digest=${2:-} snapshot_dest=${3:-}
  python3 -I - "$path" "$expected_digest" "$snapshot_dest" <<'PY'
import hashlib
import os
import re
import stat
import sys
import tempfile

path, expected_digest, snapshot_dest = sys.argv[1:]
try:
    before = os.lstat(path)
except OSError as exc:
    raise SystemExit("build/.env cannot be inspected") from exc
if not stat.S_ISREG(before.st_mode):
    raise SystemExit("build/.env must be a regular non-symlink file")
if before.st_uid != os.getuid():
    raise SystemExit("build/.env must be owned by the current user")
if stat.S_IMODE(before.st_mode) & 0o077:
    raise SystemExit("build/.env must not grant group or world permissions")

flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
try:
    descriptor = os.open(path, flags)
except OSError as exc:
    raise SystemExit("build/.env cannot be opened safely") from exc
try:
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) & 0o077
        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
    ):
        raise SystemExit("build/.env changed during validation")
    chunks = []
    total = 0
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        total += len(chunk)
        if total > 1024 * 1024:
            raise SystemExit("build/.env exceeds the 1 MiB safety limit")
        chunks.append(chunk)
finally:
    os.close(descriptor)
raw = b"".join(chunks)
digest = hashlib.sha256(raw).hexdigest()
if expected_digest and digest != expected_digest:
    raise SystemExit("build/.env changed after it was loaded")
try:
    text = raw.decode("utf-8")
except UnicodeDecodeError as exc:
    raise SystemExit("build/.env must be valid UTF-8") from exc
if any(ord(char) < 32 and char != "\n" or ord(char) == 127 for char in text):
    raise SystemExit("build/.env contains unsupported control characters")

assignment = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)")
reserved_exact = {
    "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "BASH_ENV", "ENV", "IFS",
    "CDPATH", "GLOBIGNORE", "SHELLOPTS", "BASHOPTS", "PS4", "PROMPT_COMMAND",
    "NODE_OPTIONS", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB", "ZDOTDIR",
    "GIT_ASKPASS", "SSH_ASKPASS",
}
reserved_prefixes = (
    "XDG_", "GIT_CONFIG_", "PYTHON", "NODE_", "LD_", "DYLD_", "NDDEV_",
)

def fail(message, line_number):
    raise SystemExit(f"{message} at line {line_number}")

def decode_value(value, line_number):
    if not value:
        return ""
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'") or "'" in value[1:-1]:
            fail("build/.env has malformed single-quoted value", line_number)
        decoded = value[1:-1]
    elif value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            fail("build/.env has malformed double-quoted value", line_number)
        content = value[1:-1]
        decoded_chars = []
        index = 0
        while index < len(content):
            char = content[index]
            if char == '"':
                fail("build/.env has unescaped quote in value", line_number)
            if char == "\\":
                index += 1
                if index >= len(content) or content[index] not in {'"', "\\"}:
                    fail("build/.env has unsupported escape in value", line_number)
                char = content[index]
            decoded_chars.append(char)
            index += 1
        decoded = "".join(decoded_chars)
    else:
        if value != value.strip() or any(char in value for char in "#'\""):
            fail("build/.env has ambiguous unquoted value", line_number)
        decoded = value
    if any(ord(char) < 32 or ord(char) == 127 for char in decoded):
        fail("build/.env value contains a control character", line_number)
    return decoded

records = []
seen = set()
for line_number, line in enumerate(text.split("\n"), 1):
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    match = assignment.fullmatch(line)
    if match is None:
        fail("build/.env line must be exactly KEY=VALUE", line_number)
    key, encoded_value = match.groups()
    if key in seen:
        fail("build/.env contains a duplicate key", line_number)
    seen.add(key)
    if key in reserved_exact or key.startswith(reserved_prefixes):
        fail("build/.env contains a forbidden execution-control key", line_number)
    records.append((key, decode_value(encoded_value, line_number)))

if snapshot_dest:
    destination_parent = os.path.dirname(snapshot_dest)
    descriptor, temporary = tempfile.mkstemp(prefix=".nddev-env.", dir=destination_parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, snapshot_dest)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

print(f"@sha256\t{digest}")
for key, value in records:
    print(f"{key}\t{value}")
PY
}

nddev::assert_private_env_file() {
  nddev::parse_env_file "$1" >/dev/null
}

nddev::load_env() {
  local mode=${1:-full} marketplace_dir=${2:-}
  local env_file parsed key val first_record=1 allowed_keys expected_digest=""
  case "$mode" in
    paths-only) allowed_keys="ZCODE_TARGET ZCODE_BACKUPS_DIR" ;;
    full)
      if [ -z "$marketplace_dir" ]; then
        nddev::log "error" "full build/.env loading requires a validated marketplace directory"
        return 2
      fi
      allowed_keys="$(python3 -I - "$marketplace_dir" <<'PY'
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
placeholder = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
names = {"ZCODE_TARGET", "ZCODE_BACKUPS_DIR"}
for filename in (
    "cli-config.template.json",
    "v2-config.template.json",
    "v2-setting.template.json",
    "hooks.json",
    "mcp.json",
):
    path = root / filename
    if not path.exists():
        continue
    if path.is_symlink() or not path.is_file():
        raise SystemExit("unsafe marketplace environment template")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            names.update(placeholder.findall(current))
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, dict):
            stack.extend(current.values())
print(" ".join(sorted(names)))
PY
)" || return 1
      ;;
    *) nddev::log "error" "unsupported build/.env load mode"; return 2 ;;
  esac
  env_file="$(nddev::repo_root)/build/.env"
  if [ ! -e "$env_file" ] && [ ! -L "$env_file" ]; then
    if [ -n "${NDDEV_ENV_DIGEST:-}" ] && [ "$NDDEV_ENV_DIGEST" != "absent" ]; then
      nddev::log "error" "build/.env disappeared between environment-loading phases"
      return 1
    fi
    # Read by build.sh in the same runner process.
    # shellcheck disable=SC2034
    NDDEV_ENV_DIGEST="absent"
    return 0
  fi
  if [ "${NDDEV_ENV_DIGEST:-}" = "absent" ]; then
    nddev::log "error" "build/.env appeared between environment-loading phases"
    return 1
  fi
  expected_digest="${NDDEV_ENV_DIGEST:-}"
  if ! parsed="$(nddev::parse_env_file "$env_file" "$expected_digest")"; then
    nddev::log "error" "refusing invalid or unsafe secret source: build/.env"
    return 1
  fi

  while IFS=$'\t' read -r key val; do
    if [ "$first_record" -eq 1 ]; then
      first_record=0
      if [ "$key" != "@sha256" ] || ! printf '%s\n' "$val" | grep -qE '^[0-9a-f]{64}$'; then
        nddev::log "error" "internal build/.env parser contract failed"
        return 1
      fi
      # Read by build.sh in the same runner process.
      # shellcheck disable=SC2034
      NDDEV_ENV_DIGEST="$val"
      continue
    fi
    case " $allowed_keys " in
      *" $key "*) ;;
      *) continue ;;
    esac
    # The parser never evaluates shell syntax. Only the two documented path
    # keys support a narrowly scoped HOME prefix for portable .env files.
    case "$key" in
      ZCODE_TARGET | ZCODE_BACKUPS_DIR)
        case "$val" in
          "\$HOME") val="$HOME" ;;
          "\$HOME/"*) val="$HOME/${val#\$HOME/}" ;;
          "\${HOME}") val="$HOME" ;;
          "\${HOME}/"*) val="$HOME/${val#\$\{HOME\}/}" ;;
        esac
        ;;
    esac
    if [ -z "${!key+x}" ]; then
      export "$key=$val"
    fi
  done <<< "$parsed"
  if [ "$first_record" -eq 1 ]; then
    nddev::log "error" "internal build/.env parser produced no digest"
    return 1
  fi
}

nddev::log() {
  local level=$1
  shift
  case "$level" in
    error | missing) printf '[%s] %s\n' "$level" "$*" >&2 ;;
    *) printf '[%s] %s\n' "$level" "$*" ;;
  esac
}

nddev::section() {
  printf '\n==> %s\n' "$*"
}

nddev::require_option_value() {
  local option=$1 value=${2-}
  if [ -z "$value" ] || [[ "$value" == -* ]]; then
    nddev::log "error" "$option requires a non-empty value; another option token is not a value"
    return 2
  fi
}

nddev::require_option_once() {
  local seen=$1 option=$2
  if [ "$seen" -eq 1 ]; then
    nddev::log "error" "duplicate option is not allowed: $option"
    return 2
  fi
}

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
}

# Return an absolute canonical path. Existing parent symlinks (for example
# /tmp -> /private/tmp on macOS) are resolved; the final path itself is checked
# separately before any mutation.
nddev::canonical_path() {
  local path=$1
  python3 -I - "$path" <<'PY'
import os
import pathlib
import sys

path = sys.argv[1]
if any(ord(char) < 32 or ord(char) == 127 for char in path):
    raise SystemExit("path contains a forbidden control character")
if not os.path.isabs(path):
    raise SystemExit("path must be absolute")
if any(part in {".", ".."} for part in pathlib.PurePath(path).parts):
    raise SystemExit("path must not contain dot traversal")
print(os.path.realpath(path))
PY
}

# Validate an install/backup directory endpoint. The endpoint may be absent or
# a real directory, but never a file or symlink. Canonical path is printed.
nddev::validate_directory_endpoint() {
  local role=$1 path=$2 canonical
  if ! canonical="$(nddev::canonical_path "$path")"; then
    nddev::log "error" "invalid $role path"
    return 2
  fi
  if [ "$canonical" = "/" ]; then
    nddev::log "error" "refusing to use filesystem root as $role"
    return 2
  fi
  if [ -L "$path" ]; then
    nddev::log "error" "$role must not be a symlink: $path"
    return 2
  fi
  if [ -e "$path" ] && [ ! -d "$path" ]; then
    nddev::log "error" "$role must be a directory or absent: $path"
    return 2
  fi
  printf '%s\n' "$canonical"
}

# Reject nested/equal target and backup roots. Keeping the roots disjoint makes
# backup rotation and rollback containment mechanically provable.
nddev::validate_disjoint_roots() {
  local target=$1 backups=$2
  python3 -I - "$target" "$backups" <<'PY'
import os
import sys

target, backups = map(os.path.realpath, sys.argv[1:])
if target == backups:
    raise SystemExit("target and backup roots are identical")
if os.path.commonpath((target, backups)) in (target, backups):
    raise SystemExit("target and backup roots must not contain one another")
PY
}

nddev::same_filesystem() {
  local left=$1 right=$2
  python3 -I - "$left" "$right" <<'PY'
import os
import sys

left, right = sys.argv[1:]
left_probe = left if os.path.exists(left) else os.path.dirname(left)
right_probe = right if os.path.exists(right) else os.path.dirname(right)
raise SystemExit(0 if os.stat(left_probe).st_dev == os.stat(right_probe).st_dev else 1)
PY
}

# Return a stable identity for a real filesystem endpoint. Transactions use it
# to reconcile a signal delivered in the narrow window after an atomic rename
# but before the shell can update its in-memory state.
nddev::path_identity() {
  local path=$1 expected_kind=${2:-any}
  python3 -I - "$path" "$expected_kind" <<'PY'
import os
import stat
import sys

path, expected_kind = sys.argv[1:]
metadata = os.lstat(path)
if stat.S_ISLNK(metadata.st_mode):
    raise SystemExit("filesystem endpoint must not be a symlink")
if expected_kind == "directory" and not stat.S_ISDIR(metadata.st_mode):
    raise SystemExit("filesystem endpoint must be a directory")
if expected_kind == "regular" and not stat.S_ISREG(metadata.st_mode):
    raise SystemExit("filesystem endpoint must be a regular file")
if expected_kind not in {"any", "directory", "regular"}:
    raise SystemExit("unsupported filesystem endpoint kind")
print(f"{metadata.st_dev}:{metadata.st_ino}")
PY
}

nddev::identity_matches() {
  local path=$1 expected_kind=$2 expected_identity=$3 actual_identity
  [ -n "$expected_identity" ] || return 1
  actual_identity="$(nddev::path_identity "$path" "$expected_kind" 2>/dev/null)" || return 1
  [ "$actual_identity" = "$expected_identity" ]
}

# Atomically rename without ever overwriting an endpoint or allowing `mv` to
# reinterpret an occupied directory as a destination parent. Linux and macOS
# both expose a native exclusive-rename primitive; unsupported kernels fail
# closed. The destination is verified to contain the exact source inode.
nddev::rename_noreplace() {
  local source=$1 destination=$2 expected_kind=${3:-any} expected_identity=${4:-}
  python3 -I - "$source" "$destination" "$expected_kind" "$expected_identity" <<'PY'
import ctypes
import errno
import os
import stat
import sys

source, destination, expected_kind, expected_identity = sys.argv[1:]
if any(
    not path
    or not os.path.isabs(path)
    or any(ord(char) < 32 or ord(char) == 127 for char in path)
    for path in (source, destination)
):
    raise SystemExit("exclusive rename requires safe absolute paths")
try:
    metadata = os.lstat(source)
except OSError as exc:
    raise SystemExit("exclusive rename source is unavailable") from exc
if stat.S_ISLNK(metadata.st_mode):
    raise SystemExit("exclusive rename source must not be a symlink")
if expected_kind == "directory" and not stat.S_ISDIR(metadata.st_mode):
    raise SystemExit("exclusive rename source must be a directory")
if expected_kind == "regular" and not stat.S_ISREG(metadata.st_mode):
    raise SystemExit("exclusive rename source must be a regular file")
if expected_kind not in {"any", "directory", "regular"}:
    raise SystemExit("unsupported exclusive rename source kind")
identity = f"{metadata.st_dev}:{metadata.st_ino}"
if expected_identity and identity != expected_identity:
    raise SystemExit("exclusive rename source identity changed")
if os.path.lexists(destination):
    raise SystemExit("exclusive rename destination already exists")

libc = ctypes.CDLL(None, use_errno=True)
encoded_source = os.fsencode(source)
encoded_destination = os.fsencode(destination)
if sys.platform.startswith("linux"):
    try:
        rename = libc.renameat2
    except AttributeError as exc:
        raise SystemExit("native exclusive rename is unavailable") from exc
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    def perform(encoded_from, encoded_to):
        return rename(-100, encoded_from, -100, encoded_to, 1)
elif sys.platform == "darwin":
    try:
        rename = libc.renamex_np
    except AttributeError as exc:
        raise SystemExit("native exclusive rename is unavailable") from exc
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    def perform(encoded_from, encoded_to):
        return rename(encoded_from, encoded_to, 0x00000004)
else:
    raise SystemExit("native exclusive rename is unsupported on this platform")
result = perform(encoded_source, encoded_destination)
if result != 0:
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise SystemExit("exclusive rename destination became occupied")
    raise SystemExit("native exclusive rename failed")

try:
    renamed = os.lstat(destination)
except OSError as exc:
    raise SystemExit("exclusive rename destination cannot be verified") from exc
if os.path.lexists(source) or (renamed.st_dev, renamed.st_ino) != (metadata.st_dev, metadata.st_ino):
    if not os.path.lexists(source) and os.path.lexists(destination):
        if perform(encoded_destination, encoded_source) == 0:
            raise SystemExit("exclusive rename source changed during commit; foreign state restored")
        raise SystemExit("exclusive rename postcondition failed; destination requires manual recovery")
    raise SystemExit("exclusive rename postcondition failed")
PY
}

nddev::ensure_dir() {
  local dir=$1
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] mkdir -p -m 700 %q\n' "$dir"
    return 0
  fi
  if [ -L "$dir" ] || { [ -e "$dir" ] && [ ! -d "$dir" ]; }; then
    nddev::log "error" "refusing unsafe directory endpoint: $dir"
    return 1
  fi
  mkdir -p "$dir" || return 1
  chmod 700 "$dir" || return 1
}

nddev::copy() {
  local src=$1 dest=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    printf '[DRY-RUN] cp -R %q %q\n' "$src" "$dest"
    return 0
  fi
  cp -R "$src" "$dest"
}

nddev::detect_platform() {
  case "$(uname -s)" in
    Darwin) printf 'macos\n' ;;
    Linux) printf 'ubuntu\n' ;;
    *) nddev::log "error" "unsupported OS: $(uname -s)"; return 1 ;;
  esac
}

nddev::is_semver() {
  python3 -I - "$NDDEV_SEMVER_PATTERN" "$1" <<'PY'
import re
import sys

pattern, value = sys.argv[1:]
raise SystemExit(0 if re.fullmatch(pattern, value) else 1)
PY
}

# Validate a managed BUILD-VERSION stamp and print its sanitized build version.
# The complete schema is required so a marker file alone cannot authorize a
# destructive remove or restore.
nddev::stamp_version() {
  local tree=$1
  python3 -I - "$tree/BUILD-VERSION" "$NDDEV_SEMVER_PATTERN" <<'PY'
import datetime as dt
import json
import re
import sys

path, semver_pattern = sys.argv[1:]
semver = re.compile(semver_pattern)
try:
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid BUILD-VERSION: {exc}")
if not isinstance(data, dict):
    raise SystemExit("BUILD-VERSION must be a JSON object")
# Schema 0 is the fully populated legacy 2.0.0 stamp (no explicit schema key).
# New stamps are schema 1; every other version fails closed.
schema = data.get("schema", 0)
if isinstance(schema, bool) or schema not in {0, 1}:
    raise SystemExit("unsupported BUILD-VERSION schema")
for key in ("build_version", "zcode_app_version", "zcode_cli_version"):
    value = data.get(key)
    if not isinstance(value, str) or not semver.fullmatch(value):
        raise SystemExit(f"BUILD-VERSION.{key} must be SemVer")
runtime = data.get("zcode_runtime")
if not isinstance(runtime, str) or not runtime.strip() or len(runtime) > 128:
    raise SystemExit("BUILD-VERSION.zcode_runtime must be a non-empty string")
if data.get("platform") not in {"macos", "ubuntu"}:
    raise SystemExit("BUILD-VERSION.platform must be macos or ubuntu")
installed_at = data.get("installed_at")
if not isinstance(installed_at, str):
    raise SystemExit("BUILD-VERSION.installed_at must be a UTC timestamp")
try:
    parsed = dt.datetime.fromisoformat(installed_at.replace("Z", "+00:00"))
except ValueError as exc:
    raise SystemExit("BUILD-VERSION.installed_at is invalid") from exc
if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
    raise SystemExit("BUILD-VERSION.installed_at must include UTC timezone")
print(data["build_version"])
PY
}

nddev::current_version() {
  local zcode_home="${NDDEV_TARGET:-${ZCODE_HOME:-$HOME/.zcode}}"
  if [ ! -e "$zcode_home" ]; then
    printf 'unmanaged\n'
    return 0
  fi
  if [ -L "$zcode_home" ] || [ ! -d "$zcode_home" ]; then
    nddev::log "error" "install target is not a real directory: $zcode_home" >&2
    return 1
  fi
  if [ ! -f "$zcode_home/BUILD-VERSION" ] || [ -L "$zcode_home/BUILD-VERSION" ]; then
    printf 'unmanaged\n'
    return 0
  fi
  nddev::stamp_version "$zcode_home"
}

# Choose a direct backup slot. Corrupt, duplicate, or symlinked slot entries
# fail closed instead of being ignored by rotation.
nddev::backup_slot() {
  local backups_dir="${BACKUPS_DIR:-${NDDEV_BACKUPS_DIR:-$HOME/.zcode-backups}}"
  python3 -I - "$backups_dir" "$NDDEV_SEMVER_PATTERN" <<'PY'
import os
import re
import sys

root = os.path.realpath(sys.argv[1])
semver = sys.argv[2]
if not os.path.isdir(root):
    print(0)
    raise SystemExit(0)
pattern = re.compile(rf"^([0-9])-(unmanaged|{semver})-old\.zcode$")
slots = {}
for entry in os.scandir(root):
    match = pattern.fullmatch(entry.name)
    if not match:
        if re.fullmatch(r"[0-9]-.*-old\.zcode", entry.name):
            raise SystemExit("invalid backup slot name")
        if entry.name.startswith(".slot-") and ".hold." in entry.name:
            raise SystemExit("stale backup recovery hold requires attention")
        continue
    slot = int(match.group(1))
    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
        raise SystemExit("unsafe backup slot entry")
    if slot in slots:
        raise SystemExit(f"duplicate backup slot: {slot}")
    slots[slot] = (entry.stat(follow_symlinks=False).st_mtime_ns, entry.name)
for slot in range(10):
    if slot not in slots:
        print(slot)
        raise SystemExit(0)
print(min(slots, key=lambda value: (slots[value][0], value)))
PY
}

nddev::backup_name() {
  local version=$1 slot=${2:-}
  if [ "$version" != "unmanaged" ] && ! nddev::is_semver "$version"; then
    nddev::log "error" "unsafe backup version: $version"
    return 2
  fi
  if [ -z "$slot" ]; then
    slot="$(nddev::backup_slot)" || return 1
  fi
  case "$slot" in [0-9]) ;; *) nddev::log "error" "invalid backup slot: $slot"; return 2 ;; esac
  printf '%s-%s-old.zcode\n' "$slot" "$version"
}

# Assert that candidate is a direct child of parent, with no symlink endpoint.
nddev::assert_direct_child() {
  local parent=$1 candidate=$2
  python3 -I - "$parent" "$candidate" <<'PY'
import os
import sys

parent, candidate = map(os.path.realpath, sys.argv[1:])
if os.path.dirname(candidate) != parent:
    raise SystemExit("path escapes its parent")
PY
  if [ -L "$candidate" ]; then
    nddev::log "error" "refusing symlinked child: $candidate"
    return 1
  fi
}

# Move the exact inode to an unpredictable same-parent quarantine using the
# native no-replace primitive, then remove only that quarantine. This prevents
# a replacement at the public endpoint from being consumed by cleanup.
nddev::remove_identity_bound_path() {
  local parent=$1 candidate=$2 expected_kind=$3 expected_identity=$4
  python3 -I - "$parent" "$candidate" "$expected_kind" "$expected_identity" <<'PY'
import ctypes
import os
import shutil
import stat
import sys
import tempfile

parent, candidate, expected_kind, expected_identity = sys.argv[1:]
parent = os.path.realpath(parent)
if os.path.dirname(os.path.realpath(candidate)) != parent:
    raise SystemExit("identity-bound cleanup path escapes its parent")
name = os.path.basename(candidate)
metadata = os.lstat(candidate)
if stat.S_ISLNK(metadata.st_mode):
    raise SystemExit("identity-bound cleanup source must not be a symlink")
if expected_kind == "directory" and not stat.S_ISDIR(metadata.st_mode):
    raise SystemExit("identity-bound cleanup source must be a directory")
if expected_kind == "regular" and not stat.S_ISREG(metadata.st_mode):
    raise SystemExit("identity-bound cleanup source must be a regular file")
identity = f"{metadata.st_dev}:{metadata.st_ino}"
if identity != expected_identity:
    raise SystemExit("identity-bound cleanup source changed")

parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
parent_fd = os.open(parent, parent_flags)
quarantine_path = tempfile.mkdtemp(prefix=".nddev-delete.", dir=parent)
os.rmdir(quarantine_path)
quarantine_name = os.path.basename(quarantine_path)

def native_rename_noreplace(source_name, destination_name):
    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform.startswith("linux"):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(parent_fd, source, parent_fd, destination, 1)
    elif sys.platform == "darwin":
        rename = libc.renameatx_np
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(parent_fd, source, parent_fd, destination, 0x00000004)
    else:
        raise SystemExit("native exclusive cleanup rename is unsupported")
    if result != 0:
        raise SystemExit("native exclusive cleanup rename failed")

try:
    # Revalidate through the opened parent immediately before consuming the
    # public name, then verify that the exact inode arrived in quarantine.
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (before.st_dev, before.st_ino) != (metadata.st_dev, metadata.st_ino):
        raise SystemExit("identity-bound cleanup source changed")
    native_rename_noreplace(name, quarantine_name)
    quarantined = os.stat(quarantine_name, dir_fd=parent_fd, follow_symlinks=False)
    if (quarantined.st_dev, quarantined.st_ino) != (metadata.st_dev, metadata.st_ino):
        try:
            native_rename_noreplace(quarantine_name, name)
        except BaseException as exc:
            raise SystemExit(f"cleanup quarantine requires manual recovery: {quarantine_path}") from exc
        raise SystemExit("identity-bound cleanup source changed during quarantine; foreign state restored")
    if expected_kind == "directory":
        if not shutil.rmtree.avoids_symlink_attacks:
            raise SystemExit(f"fd-safe directory cleanup is unavailable; preserved: {quarantine_path}")
        # Python 3.10 lacks shutil.rmtree(dir_fd=...). Pin the process cwd to
        # the already opened parent instead; the symlink-safe rmtree variant
        # then resolves the unpredictable quarantine name through that fd.
        os.fchdir(parent_fd)
        shutil.rmtree(quarantine_name)
    else:
        descriptor = os.open(
            quarantine_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise SystemExit(f"file cleanup quarantine changed; preserved: {quarantine_path}")
            os.unlink(quarantine_name, dir_fd=parent_fd)
        finally:
            os.close(descriptor)
finally:
    os.close(parent_fd)
PY
}

nddev::remove_direct_child_tree() {
  local parent=$1 candidate=$2 expected_identity=${3:-}
  nddev::assert_direct_child "$parent" "$candidate" || return 1
  if [ -e "$candidate" ]; then
    [ -d "$candidate" ] || { nddev::log "error" "expected directory: $candidate"; return 1; }
    if [ -n "$expected_identity" ]; then
      nddev::remove_identity_bound_path "$parent" "$candidate" directory "$expected_identity"
    else
      rm -rf -- "$candidate"
    fi
  fi
}

nddev::remove_regular_file() {
  local candidate=$1 expected_identity=${2:-}
  if [ -e "$candidate" ] || [ -L "$candidate" ]; then
    if [ ! -f "$candidate" ] || [ -L "$candidate" ]; then
      nddev::log "error" "expected regular file: $candidate"
      return 1
    fi
    if [ -n "$expected_identity" ]; then
      nddev::remove_identity_bound_path \
        "$(dirname "$candidate")" "$candidate" regular "$expected_identity"
    else
      rm -f -- "$candidate"
    fi
  fi
}

# Managed state may contain only ordinary directories and uniquely linked
# regular files. This excludes symlink traversal, device/FIFO/socket copying,
# and hard-link aliases whose chmod could mutate data outside the tree.
nddev::assert_safe_tree() {
  local root=$1
  python3 -I - "$root" <<'PY'
import os
import stat
import sys

root = sys.argv[1]
for directory, names, files in os.walk(root, topdown=True, followlinks=False):
    for name in names + files:
        path = os.path.join(directory, name)
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            raise SystemExit("symlink is not allowed in managed state")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise SystemExit("special file is not allowed in managed state")
        if os.lstat(path).st_nlink != 1:
            raise SystemExit("hard-linked file is not allowed in managed state")
PY
}

# JSON templates are parsed before recursive substitution. This preserves JSON
# escaping for arbitrary secret values and never falls back to raw text.
nddev::render_template() {
  local template=$1 dest=$2
  if [ "${NDDEV_DRY_RUN:-1}" -eq 1 ]; then
    # shellcheck disable=SC2016 # ${VAR} is documentation in the plan output.
    printf '[DRY-RUN] render JSON %q -> %q (recursive ${VAR} substitution)\n' "$template" "$dest"
    return 0
  fi
  python3 -I - "$template" "$dest" <<'PY' || return 1
import json
import os
import re
import sys
import tempfile

template_path, dest_path = sys.argv[1:]
with open(template_path, encoding="utf-8") as stream:
    data = json.load(stream)
if not isinstance(data, dict):
    raise SystemExit(f"JSON template must contain an object: {template_path}")
data.pop("_comment", None)
placeholder = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def substitute(value):
    if isinstance(value, str):
        def replace(match):
            replacement = os.environ.get(match.group(1))
            return replacement if replacement not in (None, "") else match.group(0)
        return placeholder.sub(replace, value)
    if isinstance(value, list):
        return [substitute(item) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item) for key, item in value.items()}
    return value

rendered = substitute(data)
directory = os.path.dirname(dest_path)
fd, temporary = tempfile.mkstemp(prefix=".nddev-json.", dir=directory, text=True)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(rendered, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, dest_path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
  chmod 600 "$dest" || return 1
}

nddev::validate_json() {
  local path=$1
  python3 -I - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
if not isinstance(value, dict):
    raise SystemExit("expected a JSON object")
PY
}

# Every active rendered branch must be concrete. Only explicitly disabled
# provider and MCP server nodes may retain dormant placeholders.
nddev::validate_required_placeholders() {
  local cli_config=$1 provider_config=$2 setting_config=$3
  python3 -I - "$cli_config" "$provider_config" "$setting_config" <<'PY'
import json
import re
import sys

placeholder = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")

def child_path(path, key):
    return f"{path}[{key!r}]"

def unresolved_keys(value, path):
    failures = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(unresolved_keys(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            location = child_path(path, key)
            if isinstance(key, str) and placeholder.search(key):
                failures.append(f"{location}.<placeholder-key>")
            failures.extend(unresolved_keys(item, location))
    return failures

def unresolved_values(value, path):
    failures = []
    if isinstance(value, str) and placeholder.search(value):
        failures.append(path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(unresolved_values(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            failures.extend(unresolved_values(item, child_path(path, key)))
    return failures

with open(sys.argv[1], encoding="utf-8") as stream:
    cli = json.load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    providers = json.load(stream)
with open(sys.argv[3], encoding="utf-8") as stream:
    settings = json.load(stream)
failures = []
for root_name, value in (
    ("provider-config", providers),
    ("setting", settings),
    ("cli", cli),
):
    failures.extend(unresolved_keys(value, root_name))

for key, value in providers.items():
    if key != "provider":
        failures.extend(unresolved_values(value, child_path("provider-config", key)))
        continue
    if not isinstance(value, dict):
        failures.extend(unresolved_values(value, child_path("provider-config", key)))
        continue
    for name, provider in value.items():
        if isinstance(provider, dict) and provider.get("enabled") is False:
            continue
        failures.extend(unresolved_values(provider, child_path("provider", name)))

failures.extend(unresolved_values(settings, "setting"))

for key, value in cli.items():
    if key != "mcp":
        failures.extend(unresolved_values(value, child_path("cli", key)))
        continue
    if not isinstance(value, dict):
        failures.extend(unresolved_values(value, child_path("cli", key)))
        continue
    for mcp_key, mcp_value in value.items():
        if mcp_key != "servers":
            failures.extend(unresolved_values(mcp_value, child_path("mcp", mcp_key)))
            continue
        if not isinstance(mcp_value, dict):
            failures.extend(unresolved_values(mcp_value, child_path("mcp", mcp_key)))
            continue
        for name, server in mcp_value.items():
            if isinstance(server, dict) and server.get("enabled") is False:
                continue
            failures.extend(unresolved_values(server, child_path("mcp.servers", name)))
if failures:
    raise SystemExit("unresolved required placeholder(s): " + ", ".join(failures))
PY
}

nddev::normalize_tree_permissions() {
  local root=$1
  [ -d "$root" ] && [ ! -L "$root" ] || return 1
  nddev::assert_safe_tree "$root" || return 1
  python3 -I - "$root" <<'PY'
import os
import sys

root = sys.argv[1]
for directory, names, files in os.walk(root, topdown=True, followlinks=False):
    os.chmod(directory, 0o700)
    for name in files:
        path = os.path.join(directory, name)
        relative = os.path.relpath(path, root)
        if relative in {
            ".env",
            "BUILD-VERSION",
            "cli/config.json",
            "v2/config.json",
            "v2/credentials.json",
        } or name == "credentials.json":
            os.chmod(path, 0o600)
PY
}

nddev::sync_directory() {
  local directory=$1
  python3 -I - "$directory" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

# Persist a fully prepared tree before its atomic rename becomes visible.
nddev::sync_tree() {
  local root=$1
  python3 -I - "$root" <<'PY'
import os
import sys

root = sys.argv[1]
directories = []
for directory, names, files in os.walk(root, topdown=True, followlinks=False):
    directories.append(directory)
    for name in files:
        path = os.path.join(directory, name)
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
for directory in reversed(directories):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
}
