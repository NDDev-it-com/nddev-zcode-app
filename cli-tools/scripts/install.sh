#!/usr/bin/env bash
# Trusted compatibility shim for the Python 3.9 ZCode transaction core.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MANAGER="$SCRIPT_DIR/../nddev_zcode.py"
PYTHON="/usr/bin/python3"

if [ ! -f "$PYTHON" ] || [ -L "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  printf '[error] /usr/bin/python3 must be a regular executable file\n' >&2
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
info = os.lstat(python)
if not stat.S_ISREG(info.st_mode) or not os.access(python, os.X_OK):
    raise SystemExit("/usr/bin/python3 must be a regular executable file")
if sys.version_info < (3, 9):
    raise SystemExit("/usr/bin/python3 must be Python 3.9 or newer")
PY

unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE PYTHONINSPECT
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" -I -B "$MANAGER" "$@"
