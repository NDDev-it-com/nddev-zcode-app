#!/usr/bin/env bash
# Trusted compatibility shim for the Python 3.9 ZCode transaction core.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MANAGER="$SCRIPT_DIR/../nddev_zcode.py"
PYTHON="/usr/bin/python3"

# Validate what the path resolves to, not the shape of the path. Every Linux
# distribution ships /usr/bin/python3 as a symlink to python3.<minor> while
# macOS ships a regular file, so rejecting symlinks outright rejects Ubuntu --
# a platform this installer documents as supported. /usr/bin is root-owned and
# not user-writable, so the link itself cannot be repointed by the caller; what
# matters is that it lands on a real executable.
if [ ! -x "$PYTHON" ]; then
  printf '[error] %s must be an executable file\n' "$PYTHON" >&2
  exit 2
fi
if [ ! -f "$MANAGER" ] || [ -L "$MANAGER" ]; then
  printf '[error] missing public transaction manager: %s\n' "$MANAGER" >&2
  exit 2
fi

"$PYTHON" -I -B - "$PYTHON" <<'PY'
import os
import stat
import sys

python = sys.argv[1]
resolved = os.path.realpath(python)
info = os.stat(resolved)
if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
    raise SystemExit(f"{python} must resolve to a regular executable file")
if stat.S_IMODE(info.st_mode) & 0o022:
    raise SystemExit(f"{python} must not resolve to a group- or world-writable interpreter")
if sys.version_info < (3, 9):
    raise SystemExit(f"{python} must be Python 3.9 or newer")
PY

unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE PYTHONINSPECT
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" -I -B "$MANAGER" "$@"
