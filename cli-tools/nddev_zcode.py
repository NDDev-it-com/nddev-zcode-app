#!/usr/bin/env python3
"""Dependency-free ZCode setup manager.

The shell entrypoint preserves the public CLI surface; this module owns the
filesystem transaction, monotonic coordination anchors, and machine-readable
state.  Keep this file Python 3.9-compatible.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
import platform as platform_module
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "cli-tools" / "scripts"
BOOTSTRAP = SCRIPT_DIR / "bootstrap.sh"
MARKETPLACES = ROOT / "zcode_tools" / "marketplaces"
VERSION_JSON = ROOT / "build" / "version.json"
ENV_FILE = ROOT / "build" / ".env"

PRODUCT = "nddev-zcode-app"
ANCHOR_SCHEMA = 1
CLEANUP_SCHEMA = 1
SEMVER_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
SETUP_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
BACKUP_RE = re.compile(r"([0-9])-(?:unmanaged|" + SEMVER_RE.pattern + r")-old\.zcode")
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

MAX_NAMESPACE_ENTRIES = 512
MAX_ANCHOR_BYTES = 8192
MAX_CLEANUP_BYTES = 512 * 1024
ANCHOR_TEMP_RE = re.compile(r"\.nddev-zcode-anchor\.[0-9]+\.[0-9a-f]{16}\.tmp")

RUNTIME_RESTORE_PATHS = (
    "v2/credentials.json",
    "v2/certs",
    "v2/tasks-index.sqlite",
    "v2/sessions",
    "v2/bot-config.json",
    "v2/bot-state.json",
    "v2/bot-state.v2.json",
    "cli/agents",
    "cli/db",
    "cli/artifacts",
)
RUNTIME_SKIP_PATHS = (
    "cli/log",
    "cli/exec",
    "cli/rollout",
    "v2/logs",
    "v2/crash",
    "cli/plugins/cache",
    "v2/bots-model-cache.json",
    "v2/bots-model-cache.v2.json",
    "v2/coding-plan-cache.json",
    "v2/telemetry-state.json",
)


class ManagerError(Exception):
    """Expected manager failure with an exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class ConcurrentNamespaceChange(ManagerError):
    """Cold uncoordinated read observed product namespace churn."""

    def __init__(self, message: str = "product coordination namespace changed during cold read") -> None:
        super().__init__(message, 75)


@dataclass
class Options:
    command: str = "install"
    apply: bool = False
    platform: str = "auto"
    setup: str = ""
    target: str = ""
    keep_backup: str = ""
    slot: str = ""
    adopt_unmanaged: bool = False
    allow_target_relocation: bool = False
    allow_pinned_unnotarized: bool = False
    list_backups: bool = False
    json_output: bool = False


@dataclass(frozen=True)
class FileIdentity:
    dev: int
    ino: int
    mode: int
    uid: int
    nlink: int
    size: int
    mtime_ns: int
    kind: str


@dataclass
class LockHandle:
    path: Path
    fd: int
    shared: bool

    def close(self) -> None:
        errors: list[str] = []
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError as exc:
            errors.append(str(exc))
        try:
            os.close(self.fd)
        except OSError as exc:
            errors.append(str(exc))
        if errors:
            raise ManagerError(f"cannot release coordination lock safely: {errors[0]}")


def usage() -> str:
    return """Usage: cli-tools/scripts/install.sh [bootstrap|install|remove|restore|list|status] [options]

Commands:
  bootstrap             Download and install the ZCode desktop app + CLI (from zero).
  install (default)     Build ~/.zcode from a setup.
  remove                Back up and delete the installed ~/.zcode.
  restore               Restore ~/.zcode from a backup slot (0-9).
  list                  List available setups (and backups with --backups).
  status                Show the installed setup and validated version stamp.

Options (bootstrap):
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute the download + install (default is --plan).
  --allow-pinned-unnotarized
                            Explicitly accept an exact pinned macOS artifact
                            whose Gatekeeper source is Unnotarized Developer ID.

Options (install):
  --setup <id>              Which setup to build from (required for install).
  --marketplace <id>        Backward-compatible alias for --setup.
  --target <dir>            Install directory (default: ~/.zcode, or ZCODE_TARGET in .env).
  --platform macos|ubuntu   Target platform (default: auto-detect from uname).
  --apply                   Execute (default is --plan / dry-run).
  --plan | --dry-run        Print actions without writing (default).
  --adopt-unmanaged         Allow install to replace an explicitly selected,
                            existing unstamped --target after backing it up.

Options (remove):
  --target <dir>            Directory to remove (default: ~/.zcode, or ZCODE_TARGET in .env).
  --apply                   Actually delete (default is --plan).
  --keep-backup <dir>       Use this backup root for the generated numbered slot.

Options (restore):
  --slot <N>                Backup slot to restore (0-9). Required.
  --target <dir>            Restore destination (default: ~/.zcode, or ZCODE_TARGET in .env).
  --allow-target-relocation Restore an adopted-unmanaged envelope to a different,
                            explicitly selected --target.
  --apply                   Execute the restore (default is --plan).

Options (list/status):
  --json                    Emit stable machine-readable JSON.
  --target <dir>            Status target (default: ~/.zcode, or ZCODE_TARGET in .env).

Target resolution (install/remove/restore/status):
  --target flag > ZCODE_TARGET (build/.env) > ~/.zcode

Backup convention:
  ~/.zcode -> <backups>/<N>-<VERSION>-old.zcode  (10 slots 0-9; oldest overwritten when full)
"""


def log(kind: str, message: str, *, json_output: bool = False) -> None:
    if json_output:
        return
    print(f"[{kind}] {message}")


def section(title: str, *, json_output: bool = False) -> None:
    if json_output:
        return
    print()
    print(f"==> {title}")


def fail(message: str, code: int = 1) -> None:
    raise ManagerError(message, code)


def require_semver(value: Any, field: str) -> str:
    if not isinstance(value, str) or SEMVER_RE.fullmatch(value) is None:
        fail(f"invalid {field}: {value!r}")
    return value


def load_version() -> dict[str, Any]:
    try:
        data = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"missing or invalid build/version.json: {exc}")
    if not isinstance(data, dict):
        fail("build/version.json must contain an object")
    return data


def build_version() -> str:
    return require_semver(load_version().get("build_version"), "build_version")


def pinned_app_version() -> str:
    return require_semver(load_version().get("zcode_app_version"), "zcode_app_version")


def pinned_cli_version() -> str:
    return require_semver(load_version().get("zcode_cli_version"), "zcode_cli_version")


def zcode_runtime() -> str:
    value = load_version().get("zcode_runtime")
    if not isinstance(value, str) or not value.strip():
        fail("zcode_runtime is empty")
    return value


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def current_uid() -> int:
    return os.getuid()


def fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def lstat_identity(path: Path) -> FileIdentity:
    try:
        info = os.lstat(str(path))
    except OSError as exc:
        fail(f"cannot inspect path safely: {path}: {exc}", 2)
    mode = info.st_mode
    if stat.S_ISDIR(mode):
        kind = "directory"
    elif stat.S_ISREG(mode):
        kind = "file"
    elif stat.S_ISLNK(mode):
        kind = "symlink"
    else:
        kind = "special"
    return FileIdentity(
        dev=info.st_dev,
        ino=info.st_ino,
        mode=stat.S_IMODE(mode),
        uid=info.st_uid,
        nlink=info.st_nlink,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        kind=kind,
    )


def identity_tuple(identity: FileIdentity) -> tuple[int, int]:
    return (identity.dev, identity.ino)


def identity_payload(identity: FileIdentity) -> dict[str, Any]:
    return {
        "dev": identity.dev,
        "ino": identity.ino,
        "mode": identity.mode,
        "uid": identity.uid,
        "nlink": identity.nlink,
        "size": identity.size,
        "mtime_ns": identity.mtime_ns,
        "kind": identity.kind,
    }


def identity_from_payload(value: Any, label: str) -> FileIdentity:
    keys = {"dev", "ino", "mode", "uid", "nlink", "size", "mtime_ns", "kind"}
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"{label} identity is malformed", 2)
    integers: dict[str, int] = {}
    for key in keys - {"kind"}:
        item = value[key]
        if not isinstance(item, int) or item < 0:
            fail(f"{label} identity field is invalid: {key}", 2)
        integers[key] = item
    kind = value["kind"]
    if kind not in {"directory", "file", "symlink", "special"}:
        fail(f"{label} identity kind is invalid", 2)
    return FileIdentity(kind=kind, **integers)


def path_exists(path: Path) -> bool:
    return os.path.lexists(str(path))


def require_private_directory(path: Path, label: str) -> FileIdentity:
    identity = lstat_identity(path)
    if identity.kind != "directory":
        fail(f"{label} must be a real non-symlink directory: {path}", 2)
    if identity.uid != current_uid():
        fail(f"{label} must be owned by the current user: {path}", 2)
    if identity.mode & 0o077:
        fail(f"{label} must not grant group/world permissions: {path}", 2)
    return identity


def require_safe_directory(path: Path, label: str) -> FileIdentity:
    identity = lstat_identity(path)
    if identity.kind != "directory":
        fail(f"{label} must be a real non-symlink directory: {path}", 2)
    return identity


def require_private_file_identity(path: Path, label: str) -> FileIdentity:
    identity = lstat_identity(path)
    if identity.kind != "file":
        fail(f"{label} must be a regular non-symlink file: {path}", 2)
    if identity.uid != current_uid():
        fail(f"{label} must be owned by the current user: {path}", 2)
    if identity.mode & 0o077:
        fail(f"{label} must not grant group/world permissions: {path}", 2)
    return identity


def read_file_no_follow(path: Path, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        fail(f"cannot open {label} safely: {path}: {exc}", 2)
    try:
        opened = os.fstat(fd)
        before = os.lstat(str(path))
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            fail(f"{label} changed while opening: {path}", 2)
        if not stat.S_ISREG(opened.st_mode):
            fail(f"{label} must be a regular file: {path}", 2)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                fail(f"{label} exceeds the {limit} byte safety limit: {path}", 2)
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    parent = path.parent
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(parent))
    temp = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp), str(path))
        fsync_dir(parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()
        raise


def coordination_root() -> Path:
    return Path("/tmp") / f"nddev-zcode-app-bootstrap-locks-{current_uid()}"


def product_anchor_path() -> Path:
    return coordination_root() / "global.lock"


def target_digest_for(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def target_anchor_path(digest: str) -> Path:
    return coordination_root() / f"{digest}.lock"


def anchor_payload(anchor: str, digest: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": ANCHOR_SCHEMA,
        "product": PRODUCT,
        "anchor": anchor,
    }
    if digest is not None:
        payload["target_digest"] = digest
    return payload


def anchor_bytes(anchor: str, digest: str | None) -> bytes:
    return json.dumps(anchor_payload(anchor, digest), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    ) + b"\n"


def ensure_coordination_root() -> None:
    root = coordination_root()
    if path_exists(root):
        require_private_directory(root, "product coordination namespace")
        return
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        require_private_directory(root, "product coordination namespace")
        return
    fsync_dir(root.parent)
    require_private_directory(root, "product coordination namespace")


def validate_product_namespace_empty() -> tuple[FileIdentity | None, tuple[tuple[str, FileIdentity], ...]]:
    root = coordination_root()
    if not path_exists(root):
        return None, ()
    root_identity = require_private_directory(root, "product coordination namespace")
    entries: list[tuple[str, FileIdentity]] = []
    try:
        names = sorted(os.listdir(str(root)))
    except OSError as exc:
        fail(f"cannot list product coordination namespace: {exc}", 2)
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("product coordination namespace exceeds bounded entry count", 2)
    for name in names:
        child = root / name
        identity = lstat_identity(child)
        entries.append((name, identity))
        fail(f"product coordination namespace is not empty while product anchor is absent: {name}", 2)
    return root_identity, tuple(entries)


def namespace_snapshot() -> tuple[FileIdentity | None, tuple[tuple[str, FileIdentity], ...]]:
    root = coordination_root()
    if not path_exists(root):
        return None, ()
    root_identity = require_private_directory(root, "product coordination namespace")
    names = sorted(os.listdir(str(root)))
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("product coordination namespace exceeds bounded entry count", 2)
    entries = tuple((name, lstat_identity(root / name)) for name in names)
    return root_identity, entries


def same_namespace(
    left: tuple[FileIdentity | None, tuple[tuple[str, FileIdentity], ...]],
    right: tuple[FileIdentity | None, tuple[tuple[str, FileIdentity], ...]],
) -> bool:
    return left == right


def recover_anchor_alias(path: Path, identity: tuple[int, int]) -> None:
    root = path.parent
    matches: list[Path] = []
    names = sorted(os.listdir(str(root)))
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("anchor alias scan exceeded bounded entry count", 2)
    for name in names:
        if name == path.name:
            continue
        child = root / name
        if not ANCHOR_TEMP_RE.fullmatch(name):
            if path_exists(child):
                fail(f"anchor parent contains unknown entry: {name}", 2)
            continue
        child_identity = require_private_file_identity(child, f"anchor temporary alias {name}")
        if identity_tuple(child_identity) == identity:
            matches.append(child)
    if len(matches) != 1:
        fail("anchor file has unexpected hard-link aliases", 2)
    matches[0].unlink()
    fsync_dir(root)


def validate_anchor_fd(
    fd: int,
    path: Path,
    *,
    anchor: str,
    digest: str | None,
    recover_aliases: bool,
) -> FileIdentity:
    try:
        opened = os.fstat(fd)
        current = os.lstat(str(path))
    except OSError as exc:
        fail(f"anchor binding cannot be inspected: {path}: {exc}", 2)
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise ConcurrentNamespaceChange(f"anchor file identity changed while opening: {path}")
    identity = FileIdentity(
        dev=opened.st_dev,
        ino=opened.st_ino,
        mode=stat.S_IMODE(opened.st_mode),
        uid=opened.st_uid,
        nlink=opened.st_nlink,
        size=opened.st_size,
        mtime_ns=opened.st_mtime_ns,
        kind="file" if stat.S_ISREG(opened.st_mode) else "other",
    )
    if identity.kind != "file":
        fail(f"anchor file must be regular: {path}", 2)
    if identity.uid != current_uid():
        fail(f"anchor file must be owned by the current user: {path}", 2)
    if identity.mode != 0o600:
        fail(f"anchor file must have mode 0600: {path}", 2)
    if identity.nlink != 1:
        if recover_aliases:
            recover_anchor_alias(path, identity_tuple(identity))
            reopened = os.stat(str(path))
            if (reopened.st_dev, reopened.st_ino) != identity_tuple(identity):
                raise ConcurrentNamespaceChange(f"anchor file changed during recovery: {path}")
            if reopened.st_nlink != 1:
                fail(f"anchor file must not have hard-link aliases: {path}", 2)
            identity = FileIdentity(
                dev=reopened.st_dev,
                ino=reopened.st_ino,
                mode=stat.S_IMODE(reopened.st_mode),
                uid=reopened.st_uid,
                nlink=reopened.st_nlink,
                size=reopened.st_size,
                mtime_ns=reopened.st_mtime_ns,
                kind="file",
            )
        else:
            fail(f"anchor file must not have hard-link aliases: {path}", 2)
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, MAX_ANCHOR_BYTES + 1)
    if len(raw) > MAX_ANCHOR_BYTES:
        fail(f"anchor file is over-bound: {path}", 2)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"anchor file is malformed: {path}: {exc}", 2)
    if payload != anchor_payload(anchor, digest):
        fail(f"anchor file binding mismatch: {path}", 2)
    return identity


def open_anchor(
    path: Path,
    *,
    anchor: str,
    digest: str | None = None,
    create: bool,
    shared: bool,
    recover_aliases: bool,
) -> LockHandle | None:
    if create:
        ensure_coordination_root()
    elif not path_exists(path):
        return None

    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        if not create:
            return None
        return publish_anchor(path, anchor=anchor, digest=digest, shared=shared)
    except OSError as exc:
        fail(f"cannot open anchor safely: {path}: {exc}", 2)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        validate_anchor_fd(fd, path, anchor=anchor, digest=digest, recover_aliases=recover_aliases)
        return LockHandle(path=path, fd=fd, shared=shared)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise


def publish_anchor(path: Path, *, anchor: str, digest: str | None, shared: bool) -> LockHandle:
    root = path.parent
    ensure_coordination_root()
    payload = anchor_bytes(anchor, digest)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".nddev-zcode-anchor.{os.getpid()}.", suffix=".tmp", dir=str(root)
    )
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
        try:
            os.link(str(temp), str(path))
        except FileExistsError:
            with contextlib.suppress(FileNotFoundError):
                temp.unlink()
            fsync_dir(root)
            os.close(fd)
            return open_anchor(
                path,
                anchor=anchor,
                digest=digest,
                create=False,
                shared=shared,
                recover_aliases=False,
            )  # type: ignore[return-value]
        except OSError as exc:
            fail(f"cannot publish anchor safely: {path}: {exc}", 2)
        try:
            temp.unlink()
            fsync_dir(root)
        finally:
            os.close(fd)
        handle = open_anchor(
            path,
            anchor=anchor,
            digest=digest,
            create=False,
            shared=shared,
            recover_aliases=True,
        )
        if handle is None:
            raise ConcurrentNamespaceChange("published anchor disappeared before open")
        return handle
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            if path_exists(temp):
                temp.unlink()
                fsync_dir(root)
        raise


@contextlib.contextmanager
def target_coordination(target_text: str, *, create: bool, shared: bool) -> Iterator[Path]:
    product = open_anchor(
        product_anchor_path(),
        anchor="product",
        create=create,
        shared=shared,
        recover_aliases=create,
    )
    if product is None:
        fail("product coordination anchor is absent", 2)
    try:
        target = canonical_target_from_text(target_text)
        digest = target_digest_for(target)
        target_path = target_anchor_path(digest)
        target_handle = open_anchor(
            target_path,
            anchor="target",
            digest=digest,
            create=create,
            shared=shared,
            recover_aliases=create,
        )
        if target_handle is None:
            if create:
                fail("target coordination anchor could not be published", 2)
            yield target
            return
        try:
            product.close()
            product = None
            yield target
        finally:
            target_handle.close()
    finally:
        if product is not None:
            product.close()


def run_read_only(target_text: str, callback: Callable[[Path], Any]) -> Any:
    product_path = product_anchor_path()
    product = open_anchor(
        product_path,
        anchor="product",
        create=False,
        shared=True,
        recover_aliases=False,
    )
    if product is not None:
        try:
            target = canonical_target_from_text(target_text)
            if path_exists(live_prepare_path(target)):
                product.close()
                product = None
                with target_coordination(target_text, create=False, shared=False) as locked:
                    recover_live_prepare_if_needed(locked)
                return run_read_only(target_text, callback)
            digest = target_digest_for(target)
            target_handle = open_anchor(
                target_anchor_path(digest),
                anchor="target",
                digest=digest,
                create=False,
                shared=True,
                recover_aliases=False,
            )
            if target_handle is None:
                return callback(target)
            try:
                product.close()
                product = None
                return callback(target)
            finally:
                target_handle.close()
        finally:
            if product is not None:
                product.close()

    before = validate_product_namespace_empty()
    result = callback(canonical_target_from_text(target_text))
    after = namespace_snapshot()
    if not same_namespace(before, after):
        with target_coordination(target_text, create=False, shared=True) as locked:
            return callback(locked)
    return result


def canonical_target_from_text(value: str) -> Path:
    if "\x00" in value or not value:
        fail("target path is invalid", 2)
    expanded = Path(value).expanduser()
    if not expanded.is_absolute():
        expanded = (Path.cwd() / expanded)
    name = expanded.name
    if not name or name in {".", ".."}:
        fail("target endpoint must not be a filesystem root", 2)
    parent = expanded.parent
    try:
        parent_real = parent.resolve(strict=True)
    except OSError as exc:
        fail(f"target parent cannot be resolved safely: {parent}: {exc}", 2)
    if str(parent_real) == "/":
        fail("target parent must not be filesystem root", 2)
    target = parent_real / name
    if path_exists(target):
        identity = lstat_identity(target)
        if identity.kind == "symlink":
            fail("install target must not be a symlink", 2)
        if identity.kind != "directory":
            fail("install target must be a directory endpoint", 2)
    return target


def parse_env_file() -> dict[str, str]:
    if not path_exists(ENV_FILE):
        return {}
    identity = require_private_file_identity(ENV_FILE, "build/.env")
    if identity.size > 1024 * 1024:
        fail("build/.env exceeds the 1 MiB safety limit")
    text = read_file_no_follow(ENV_FILE, 1024 * 1024, "build/.env").decode("utf-8")
    result: dict[str, str] = {}
    reserved_exact = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "BASH_ENV",
        "ENV",
        "IFS",
        "CDPATH",
        "GLOBIGNORE",
        "SHELLOPTS",
        "BASHOPTS",
        "PS4",
        "PROMPT_COMMAND",
        "NODE_OPTIONS",
        "RUBYOPT",
        "RUBYLIB",
        "PERL5OPT",
        "PERL5LIB",
        "ZDOTDIR",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
    }
    reserved_prefixes = ("XDG_", "GIT_CONFIG_", "PYTHON", "NODE_", "LD_", "DYLD_", "NDDEV_")
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if match is None:
            fail(f"build/.env line must be exactly KEY=VALUE at line {line_number}")
        key, value = match.groups()
        if key in result:
            fail(f"build/.env contains a duplicate key at line {line_number}")
        if key in reserved_exact or key.startswith(reserved_prefixes):
            fail(f"build/.env contains a forbidden execution-control key at line {line_number}")
        result[key] = decode_env_value(value, line_number)
    return result


def decode_env_value(value: str, line_number: int) -> str:
    if not value:
        return ""
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'") or "'" in value[1:-1]:
            fail(f"build/.env has malformed single-quoted value at line {line_number}")
        return value[1:-1]
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            fail(f"build/.env has malformed double-quoted value at line {line_number}")
        content = value[1:-1]
        decoded: list[str] = []
        index = 0
        while index < len(content):
            char = content[index]
            if char == '"':
                fail(f"build/.env has unescaped quote in value at line {line_number}")
            if char == "\\":
                index += 1
                if index >= len(content) or content[index] not in {'"', "\\"}:
                    fail(f"build/.env has unsupported escape in value at line {line_number}")
                char = content[index]
            decoded.append(char)
            index += 1
        return "".join(decoded)
    if value != value.strip() or any(char in value for char in "#'\""):
        fail(f"build/.env has ambiguous unquoted value at line {line_number}")
    return value


def resolve_target_option(options: Options, env_file: dict[str, str]) -> str:
    if options.target:
        return options.target
    if env_file.get("ZCODE_TARGET"):
        return env_file["ZCODE_TARGET"]
    return str(Path.home() / ".zcode")


def resolve_backups_option(options: Options, env_file: dict[str, str]) -> str:
    if options.keep_backup:
        return options.keep_backup
    if env_file.get("ZCODE_BACKUPS_DIR"):
        return env_file["ZCODE_BACKUPS_DIR"]
    return str(Path.home() / ".zcode-backups")


def detect_platform() -> str:
    system = platform_module.system()
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "ubuntu"
    fail("unsupported platform (expected macos|ubuntu)", 2)


def load_json_file(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        fail(f"missing safe JSON {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must contain a JSON object")
    return value


def list_setups(json_output: bool) -> int:
    setups: list[dict[str, Any]] = []
    if MARKETPLACES.exists():
        require_safe_directory(MARKETPLACES, "setup catalog root")
        for entry in sorted(MARKETPLACES.iterdir(), key=lambda item: item.name):
            if not SETUP_RE.fullmatch(entry.name):
                continue
            if entry.is_symlink() or not entry.is_dir():
                fail(f"unsafe setup catalog entry: {entry.name}")
            manifest = load_json_file(entry / "marketplace.json", "setup manifest")
            if manifest.get("name") != entry.name:
                fail(f"setup manifest identity mismatch: {entry.name}")
            description = manifest.get("description", "")
            plugins = manifest.get("plugins")
            if not isinstance(description, str) or not isinstance(plugins, list):
                fail(f"invalid setup manifest summary: {entry.name}")
            setups.append(
                {"id": entry.name, "description": description, "plugin_count": len(plugins)}
            )
    if json_output:
        print(json.dumps({"schema_version": 1, "setups": setups}, separators=(",", ":")))
    else:
        section("Available setups")
        if not setups:
            print("  no setups found")
        for setup in setups:
            print(f"  {setup['id']:<24} {setup['description']}")
    return 0


def stamp_metadata(target: Path) -> dict[str, Any]:
    path = target / "BUILD-VERSION"
    raw = read_file_no_follow(path, 64 * 1024, "BUILD-VERSION")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"BUILD-VERSION is invalid JSON: {exc}")
    if not isinstance(data, dict):
        fail("BUILD-VERSION must contain an object")
    required = ("build_version", "zcode_app_version", "zcode_cli_version", "zcode_runtime", "platform", "installed_at")
    for key in required:
        if key not in data:
            fail(f"BUILD-VERSION missing {key}")
    require_semver(data.get("build_version"), "BUILD-VERSION.build_version")
    require_semver(data.get("zcode_app_version"), "BUILD-VERSION.zcode_app_version")
    require_semver(data.get("zcode_cli_version"), "BUILD-VERSION.zcode_cli_version")
    if data.get("platform") not in {"macos", "ubuntu"}:
        fail("BUILD-VERSION.platform is invalid")
    if data.get("schema") == 2:
        setup = data.get("setup_id")
        if not isinstance(setup, str) or SETUP_RE.fullmatch(setup) is None:
            fail("BUILD-VERSION.setup_id must be kebab-case")
        stamp_schema = 2
    else:
        setup = None
        stamp_schema = 0 if "schema" not in data else 1
    return {
        "build_version": data["build_version"],
        "installed_at": data["installed_at"],
        "platform": data["platform"],
        "setup_id": setup,
        "stamp_schema": stamp_schema,
        "zcode_app_version": data["zcode_app_version"],
        "zcode_cli_version": data["zcode_cli_version"],
        "zcode_runtime": data["zcode_runtime"],
    }


def cleanup_root_for(target: Path) -> Path:
    return target.parent / ".nddev-zcode-cleanup" / target_digest_for(target)


def cleanup_journal_path(target: Path) -> Path:
    return cleanup_root_for(target) / "journal.json"


def cleanup_prepare_path(target: Path) -> Path:
    return cleanup_root_for(target) / "prepare.json"


def live_prepare_path(target: Path) -> Path:
    return cleanup_root_for(target) / "live-prepare.json"


def child_name(path: Path, parent: Path, label: str) -> str:
    if path.parent != parent or path.name in {"", ".", ".."} or "/" in path.name:
        fail(f"{label} must be a direct child of its declared parent", 2)
    return path.name


def bounded_relative(path: Path, parent: Path, label: str) -> str:
    try:
        relative = path.relative_to(parent)
    except ValueError:
        fail(f"{label} must stay within its declared parent", 2)
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail(f"{label} relative path is invalid", 2)
    return relative.as_posix()


def write_live_prepare(
    target: Path,
    backups: Path,
    *,
    operation: str,
    stage: Path | None,
    stage_identity: FileIdentity | None,
    source_identity: FileIdentity | None,
    destination: Path | None,
) -> None:
    root = cleanup_root_for(target)
    ensure_dir(root)
    payload = {
        "schema": CLEANUP_SCHEMA,
        "product": PRODUCT,
        "type": "live-rename-prepare",
        "operation": operation,
        "target": str(target),
        "target_digest": target_digest_for(target),
        "target_name": child_name(target, target.parent, "target"),
        "backup_root": str(backups),
        "stage_name": None if stage is None else child_name(stage, target.parent, "stage"),
        "backup_name": None if destination is None else bounded_relative(destination, backups, "backup destination"),
        "target_identity": None if source_identity is None else identity_payload(source_identity),
        "stage_identity": None if stage_identity is None else identity_payload(stage_identity),
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(data) > MAX_CLEANUP_BYTES:
        fail("live transaction prepare intent exceeds serialized byte bound", 2)
    atomic_write(live_prepare_path(target), data, 0o600)


def read_live_prepare(target: Path) -> dict[str, Any]:
    raw = read_file_no_follow(live_prepare_path(target), MAX_CLEANUP_BYTES, "live transaction prepare intent")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"live transaction prepare intent is malformed: {exc}", 2)
    if not isinstance(payload, dict):
        fail("live transaction prepare intent must contain an object", 2)
    required = {
        "schema",
        "product",
        "type",
        "operation",
        "target",
        "target_digest",
        "target_name",
        "backup_root",
        "stage_name",
        "backup_name",
        "target_identity",
        "stage_identity",
    }
    if set(payload) != required:
        fail("live transaction prepare intent keys are invalid", 2)
    if (
        payload["schema"] != CLEANUP_SCHEMA
        or payload["product"] != PRODUCT
        or payload["type"] != "live-rename-prepare"
    ):
        fail("live transaction prepare intent schema/product mismatch", 2)
    if payload["target"] != str(target) or payload["target_digest"] != target_digest_for(target):
        fail("live transaction prepare intent target binding mismatch", 2)
    if payload["operation"] not in {"install", "restore", "remove"}:
        fail("live transaction prepare operation is invalid", 2)
    if payload["target_name"] != target.name:
        fail("live transaction prepare target name mismatch", 2)
    if not isinstance(payload["backup_root"], str) or not os.path.isabs(payload["backup_root"]):
        fail("live transaction prepare backup root is invalid", 2)
    for key in ("stage_name", "backup_name"):
        value = payload[key]
        if value is not None and (
            not isinstance(value, str)
            or value in {"", ".", ".."}
            or value.startswith("/")
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            fail(f"live transaction prepare {key} is invalid", 2)
    if payload["target_identity"] is not None:
        identity_from_payload(payload["target_identity"], "live target")
    if payload["stage_identity"] is not None:
        identity_from_payload(payload["stage_identity"], "live stage")
    return payload


def unlink_live_prepare(target: Path) -> None:
    prepare = live_prepare_path(target)
    if path_exists(prepare):
        prepare.unlink()
        fsync_dir(prepare.parent)


def cleanup_empty_backup_container(destination: Path | None, backups: Path) -> None:
    if destination is None or destination.parent == backups:
        return
    container = destination.parent
    if path_exists(container):
        try:
            container.rmdir()
        except OSError:
            return
        fsync_dir(container.parent)


def recover_live_prepare_if_needed(target: Path) -> None:
    prepare = live_prepare_path(target)
    if not path_exists(prepare):
        return
    payload = read_live_prepare(target)
    backups = Path(payload["backup_root"])
    stage = target.parent / payload["stage_name"] if payload["stage_name"] is not None else None
    destination = backups / payload["backup_name"] if payload["backup_name"] is not None else None
    source_identity = (
        None
        if payload["target_identity"] is None
        else identity_from_payload(payload["target_identity"], "live target")
    )
    stage_identity = (
        None
        if payload["stage_identity"] is None
        else identity_from_payload(payload["stage_identity"], "live stage")
    )
    operation = payload["operation"]

    target_matches_source = (
        source_identity is not None and path_exists(target) and lstat_identity(target) == source_identity
    )
    target_matches_stage = (
        stage_identity is not None and path_exists(target) and lstat_identity(target) == stage_identity
    )
    stage_exists = stage is not None and path_exists(stage)
    destination_exists = destination is not None and path_exists(destination)

    if operation == "remove":
        if target_matches_source and not destination_exists:
            cleanup_empty_backup_container(destination, backups)
            unlink_live_prepare(target)
            return
        if not path_exists(target) and destination_exists:
            if source_identity is not None and lstat_identity(destination) != source_identity:
                fail("live remove backup identity changed before recovery", 2)
            unlink_live_prepare(target)
            return
        fail("live remove prepare state is incoherent", 2)

    if target_matches_stage and not stage_exists:
        unlink_live_prepare(target)
        return
    if target_matches_source and not stage_exists and not destination_exists:
        cleanup_empty_backup_container(destination, backups)
        unlink_live_prepare(target)
        return
    if target_matches_source and stage_exists and not destination_exists:
        if stage_identity is None:
            fail("live prepare stage identity is missing", 2)
        remove_tree_identity(stage, stage_identity)
        cleanup_empty_backup_container(destination, backups)
        unlink_live_prepare(target)
        return
    if not path_exists(target) and source_identity is not None and destination_exists:
        if lstat_identity(destination) != source_identity:
            fail("live rollback source identity changed before recovery", 2)
        if stage_exists:
            if stage_identity is None:
                fail("live prepare stage identity is missing", 2)
            remove_tree_identity(stage, stage_identity)
        rename_noreplace(destination, target, source_identity)
        cleanup_empty_backup_container(destination, backups)
        unlink_live_prepare(target)
        return
    if not path_exists(target) and source_identity is None and stage_exists:
        if stage_identity is None:
            fail("live prepare stage identity is missing", 2)
        remove_tree_identity(stage, stage_identity)
        unlink_live_prepare(target)
        return
    if not path_exists(target) and source_identity is None and not stage_exists:
        unlink_live_prepare(target)
        return
    fail("live transaction prepare state is incoherent", 2)


def cleanup_pending_state(target: Path, *, recover_aliases: bool = False) -> dict[str, Any]:
    if path_exists(live_prepare_path(target)):
        fail("live transaction recovery is incomplete", 2)
    journal = cleanup_journal_path(target)
    if not path_exists(journal):
        prepare = cleanup_prepare_path(target)
        if path_exists(prepare):
            fail("cleanup preparation is incomplete", 2)
        return {"cleanup_pending": False, "cleanup_pending_entries": []}
    payload = read_cleanup_journal(target, recover_aliases=recover_aliases)
    return {
        "cleanup_pending": True,
        "cleanup_pending_entries": [
            {"kind": entry["kind"], "relative": entry["relative"]} for entry in payload["entries"]
        ],
    }


def status_payload(target: Path) -> dict[str, Any]:
    cleanup = cleanup_pending_state(target, recover_aliases=False)
    if not path_exists(target):
        payload: dict[str, Any] = {"schema_version": 1, "state": "missing"}
    elif lstat_identity(target).kind != "directory":
        payload = {"schema_version": 1, "state": "unmanaged"}
    elif not path_exists(target / "BUILD-VERSION"):
        payload = {"schema_version": 1, "state": "unmanaged"}
    else:
        payload = {"schema_version": 1, "state": "managed", **stamp_metadata(target)}
    if cleanup["cleanup_pending"]:
        payload.update(cleanup)
    return payload


def show_status(options: Options, target_text: str) -> int:
    payload = run_read_only(target_text, status_payload)
    if options.json_output:
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    section("Installation status")
    print(f"  state: {payload['state']}")
    if payload["state"] == "managed":
        setup = payload.get("setup_id") or "unknown (legacy stamp)"
        print(f"  setup: {setup}")
        print(f"  build: {payload['build_version']}")
        print(f"  platform: {payload['platform']}")
        print(f"  installed: {payload['installed_at']}")
    if payload.get("cleanup_pending"):
        print("  cleanup_pending: true")
    return 0


def safe_copytree(src: Path, dst: Path) -> None:
    if src.is_symlink():
        fail(f"refusing to copy symlink: {src}")
    if src.is_dir():
        dst.mkdir(mode=0o700, exist_ok=False)
        for child in sorted(src.iterdir(), key=lambda item: item.name):
            safe_copytree(child, dst / child.name)
        shutil.copystat(src, dst, follow_symlinks=False)
        os.chmod(dst, 0o700)
    elif src.is_file():
        shutil.copy2(src, dst, follow_symlinks=False)
        mode = 0o700 if os.access(str(src), os.X_OK) else 0o600
        os.chmod(dst, mode)
    else:
        fail(f"refusing to copy special file: {src}")


def ensure_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def substitute_placeholders(value: Any, env: dict[str, str]) -> Any:
    if isinstance(value, str):
        return PLACEHOLDER_RE.sub(lambda m: env.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [substitute_placeholders(item, env) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and PLACEHOLDER_RE.search(key):
                fail("placeholder-bearing object keys are rejected")
            result[key] = substitute_placeholders(item, env)
        return result
    return value


def unresolved_paths(value: Any, path: str) -> list[str]:
    failures: list[str] = []
    if isinstance(value, str) and PLACEHOLDER_RE.search(value):
        failures.append(path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(unresolved_paths(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            failures.extend(unresolved_paths(item, f"{path}[{key!r}]"))
    return failures


def write_json(path: Path, value: Any, mode: int = 0o600) -> None:
    data = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    atomic_write(path, data, mode)


def validate_cli_model_provider(value: dict[str, Any]) -> None:
    model = value.get("model")
    if isinstance(model, str):
        main = model.strip()
    elif isinstance(model, dict) and isinstance(model.get("main"), str):
        main = model["main"].strip()
    else:
        fail("cli.model must declare an explicit main provider/model reference")
    provider_id, separator, model_id = main.partition("/")
    if not separator or not provider_id.strip() or not model_id.strip():
        fail("cli.model main reference must use provider/model format")
    provider_map = value.get("provider")
    if not isinstance(provider_map, dict):
        fail("cli.provider must be a JSON object")
    provider = provider_map.get(provider_id)
    if not isinstance(provider, dict):
        fail(f"cli.provider is missing the configured model provider: {provider_id}")
    options = provider.get("options")
    if not isinstance(options, dict) or not isinstance(options.get("baseURL"), str):
        fail(f"cli.provider.{provider_id}.options.baseURL is required")
    models = provider.get("models")
    if not isinstance(models, dict):
        fail(f"cli.provider.{provider_id}.models must be a JSON object")
    declared = models.get(model_id)
    if declared is None:
        declared = next(
            (
                item
                for item in models.values()
                if isinstance(item, dict) and item.get("id") == model_id
            ),
            None,
        )
    if not isinstance(declared, dict):
        fail(f"cli.provider.{provider_id}.models does not declare the configured model: {model_id}")


def validate_custom_provider_identities(value: dict[str, Any]) -> None:
    provider_map = value.get("provider")
    if not isinstance(provider_map, dict):
        fail("provider-config.provider must be a JSON object")
    for provider_id, provider in provider_map.items():
        if not isinstance(provider, dict):
            fail(f"provider-config.provider.{provider_id} must be a JSON object")
        if provider.get("source") == "custom" and provider_id.startswith("builtin:"):
            fail("custom provider identities must not reuse ZCode-owned builtin:* ids: " + provider_id)


def render_configs(source: Path, target: Path, env: dict[str, str]) -> None:
    cli = substitute_placeholders(load_json_file(source / "cli-config.template.json", "cli config"), env)
    providers = substitute_placeholders(
        load_json_file(source / "v2-config.template.json", "provider config"), env
    )
    settings = substitute_placeholders(
        load_json_file(source / "v2-setting.template.json", "settings"), env
    )
    hooks_path = source / "hooks.json"
    if hooks_path.exists():
        hooks = substitute_placeholders(load_json_file(hooks_path, "hooks"), env)
        hooks.pop("_comment", None)
        events = cli.setdefault("hooks", {}).setdefault("events", {})
        if not isinstance(events, dict):
            fail("hooks.events must be a JSON object")
        cli["hooks"].setdefault("enabled", True)
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                fail(f"hook event must contain a list: {event}")
            existing = events.setdefault(event, [])
            if not isinstance(existing, list):
                fail(f"configured hook event is not a list: {event}")
            existing.extend(entries)
    mcp_path = source / "mcp.json"
    if mcp_path.exists():
        mcp = substitute_placeholders(load_json_file(mcp_path, "mcp"), env)
        mcp.pop("_comment", None)
        servers = mcp.get("mcpServers", {})
        if not isinstance(servers, dict):
            fail("mcpServers must be a JSON object")
        configured = cli.setdefault("mcp", {}).setdefault("servers", {})
        if not isinstance(configured, dict):
            fail("mcp.servers must be a JSON object")
        configured.update(servers)
    validate_cli_model_provider(cli)
    validate_custom_provider_identities(providers)
    failures: list[str] = []
    failures.extend(unresolved_paths(settings, "setting"))
    for key, value in providers.items():
        if key != "provider":
            failures.extend(unresolved_paths(value, f"provider-config[{key!r}]"))
        elif isinstance(value, dict):
            for name, provider in value.items():
                if isinstance(provider, dict) and provider.get("enabled") is False:
                    continue
                failures.extend(unresolved_paths(provider, f"provider[{name!r}]"))
        else:
            failures.extend(unresolved_paths(value, f"provider-config[{key!r}]"))
    for key, value in cli.items():
        if key != "mcp":
            failures.extend(unresolved_paths(value, f"cli[{key!r}]"))
        elif isinstance(value, dict):
            for mcp_key, mcp_value in value.items():
                if mcp_key != "servers":
                    failures.extend(unresolved_paths(mcp_value, f"mcp[{mcp_key!r}]"))
                elif isinstance(mcp_value, dict):
                    for name, server in mcp_value.items():
                        if isinstance(server, dict) and server.get("enabled") is False:
                            continue
                        failures.extend(unresolved_paths(server, f"mcp.servers[{name!r}]"))
                else:
                    failures.extend(unresolved_paths(mcp_value, f"mcp[{mcp_key!r}]"))
        else:
            failures.extend(unresolved_paths(value, f"cli[{key!r}]"))
    if failures:
        fail("unresolved required placeholder(s): " + ", ".join(failures))
    write_json(target / "cli" / "config.json", cli)
    write_json(target / "v2" / "config.json", providers)
    write_json(target / "v2" / "setting.json", settings)


def write_env_snapshot(target: Path, env_values: dict[str, str]) -> None:
    if not path_exists(ENV_FILE):
        log("info", "no build/.env - runtime tools must receive secrets from the environment")
        return
    raw = read_file_no_follow(ENV_FILE, 1024 * 1024, "build/.env")
    atomic_write(target / ".env", raw, 0o600)


def assert_component_graph(source: Path) -> None:
    seen: dict[tuple[str, str], str] = {}
    roots = [("direct", source)]
    plugins = source / "plugins"
    if plugins.is_dir():
        for plugin in sorted(plugins.iterdir(), key=lambda item: item.name):
            if plugin.is_dir() and not plugin.is_symlink():
                roots.append((f"plugin {plugin.name}", plugin))
    for origin, root in roots:
        for component in ("skills", "commands", "agents"):
            directory = root / component
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir(), key=lambda item: item.name):
                if entry.name == ".gitkeep":
                    continue
                key = (component, entry.name)
                if key in seen:
                    fail(f"user-scope {component} name collision: {entry.name} (from {seen[key]}; {origin})")
                seen[key] = origin


def copy_source_tree(source: Path, target: Path) -> None:
    mp_name = source.name
    assert_component_graph(source)
    safe_copytree(source / "AGENTS.md", target / "AGENTS.md")
    ensure_dir(target / "marketplaces")
    safe_copytree(source, target / "marketplaces" / mp_name)
    for component in ("skills", "commands", "agents"):
        src = source / component
        if src.is_dir():
            ensure_dir(target / component)
            for child in sorted(src.iterdir(), key=lambda item: item.name):
                if child.name == ".gitkeep":
                    continue
                safe_copytree(child, target / component / child.name)
    plugins_root = target / "marketplaces" / mp_name / "plugins"
    if plugins_root.is_dir():
        for plugin in sorted(plugins_root.iterdir(), key=lambda item: item.name):
            for component in ("skills", "commands", "agents"):
                src = plugin / component
                if not src.is_dir():
                    continue
                ensure_dir(target / component)
                for child in sorted(src.iterdir(), key=lambda item: item.name):
                    if child.name == ".gitkeep":
                        continue
                    dest = target / component / child.name
                    if path_exists(dest):
                        fail(f"user-scope {component} name collision: {child.name}")
                    safe_copytree(child, dest)


def create_runtime_dirs(target: Path) -> None:
    for relative in (
        "cli/agents",
        "cli/artifacts",
        "cli/db",
        "cli/log",
        "cli/plugins/cache",
        "cli/plugins/data",
        "v2/logs",
        "v2/crash",
    ):
        ensure_dir(target / relative)


def safe_tree(path: Path) -> None:
    for root, dirs, files in os.walk(str(path), topdown=True, followlinks=False):
        root_path = Path(root)
        for name in dirs + files:
            child = root_path / name
            identity = lstat_identity(child)
            if identity.kind == "symlink" or identity.kind == "special":
                fail(f"unsafe filesystem entry: {child}")
            if identity.kind == "file" and identity.nlink != 1:
                fail(f"multiply-linked file is not allowed: {child}")


def normalize_tree(path: Path) -> None:
    for root, dirs, files in os.walk(str(path), topdown=False, followlinks=False):
        for name in files:
            child = Path(root) / name
            if child.is_symlink():
                fail(f"unsafe symlink in managed tree: {child}")
            os.chmod(child, 0o700 if os.access(str(child), os.X_OK) else 0o600)
        for name in dirs:
            child = Path(root) / name
            if child.is_symlink():
                fail(f"unsafe symlink in managed tree: {child}")
            os.chmod(child, 0o700)
    os.chmod(path, 0o700)


def fsync_tree(path: Path) -> None:
    for root, dirs, files in os.walk(str(path), topdown=False, followlinks=False):
        for name in files:
            child = Path(root) / name
            fd = os.open(str(child), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        fsync_dir(Path(root))


def write_stamp(target: Path, platform: str, setup: str) -> None:
    payload = {
        "schema": 2,
        "setup_id": setup,
        "build_version": build_version(),
        "zcode_app_version": pinned_app_version(),
        "zcode_cli_version": pinned_cli_version(),
        "zcode_runtime": zcode_runtime(),
        "platform": platform,
        "installed_at": utc_now(),
    }
    write_json(target / "BUILD-VERSION", payload)
    log(
        "ok",
        f"wrote BUILD-VERSION ({payload['build_version']}, setup {setup}, {platform}, zcode {payload['zcode_app_version']})",
    )


def build_stage(source: Path, stage: Path, env_values: dict[str, str], platform: str, setup: str) -> None:
    section("Build isolated staging tree")
    ensure_dir(stage)
    ensure_dir(stage / "cli")
    ensure_dir(stage / "v2")
    create_runtime_dirs(stage)
    section(f"Copy source tree (marketplace: {setup})")
    copy_source_tree(source, stage)
    section("Render config templates")
    render_configs(source, stage, env_values)
    write_env_snapshot(stage, env_values)
    write_stamp(stage, platform, setup)
    verify_managed_tree(stage, setup=setup)
    normalize_tree(stage)
    fsync_tree(stage)


def copy_runtime_state(source: Path, target: Path, *, unmanaged: bool = False) -> None:
    if not source.is_dir():
        log("info", "no existing state to adopt (fresh install)")
        return
    section("Restore selected runtime state into staging")
    restored = 0
    missing = 0
    for relative in RUNTIME_RESTORE_PATHS:
        src = source / relative
        dst = target / relative
        if not path_exists(src):
            missing += 1
            log("info", f"not in backup (skip): {relative}")
            continue
        if src.is_symlink():
            fail(f"unsafe runtime restore source: {relative}")
        if relative == "cli/db" and src.is_dir() and not src.is_symlink():
            ensure_dir(dst)
            for child in sorted(src.iterdir(), key=lambda item: item.name):
                target_child = dst / child.name
                if path_exists(target_child):
                    if target_child.is_dir() and not target_child.is_symlink():
                        shutil.rmtree(str(target_child))
                    else:
                        target_child.unlink()
                safe_copytree(child, target_child)
            restored += 1
            continue
        if path_exists(dst):
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(str(dst))
            else:
                dst.unlink()
        ensure_dir(dst.parent)
        safe_copytree(src, dst)
        restored += 1
    log("info", f"restored {restored} path(s), {missing} absent in backup")


def verify_managed_tree(target: Path, *, setup: str | None = None) -> None:
    if not target.is_dir() or target.is_symlink():
        fail(f"managed tree is not a real directory: {target}")
    safe_tree(target)
    stamp = stamp_metadata(target)
    if setup is not None and stamp.get("setup_id") != setup:
        fail("BUILD-VERSION setup identity does not match selected setup")
    for relative in ("cli/config.json", "v2/config.json", "v2/setting.json"):
        load_json_file(target / relative, relative)
    if not (target / "AGENTS.md").is_file():
        fail("AGENTS.md not found")
    if setup is not None:
        load_json_file(target / "marketplaces" / setup / "marketplace.json", "marketplace")


def runtime_quiescent(target: Path, *, plan: bool) -> None:
    if plan or not target.is_dir():
        return
    for database in (target / "v2" / "tasks-index.sqlite", target / "cli" / "db" / "db.sqlite"):
        for suffix in ("-wal", "-shm", "-journal"):
            if path_exists(Path(str(database) + suffix)):
                fail(
                    "quit ZCode cleanly before setup changes; runtime database has an active "
                    f"recovery sidecar: {database}{suffix}"
                )
    # Keep this advisory and best-effort, matching the historical shell helper.
    inspector = shutil.which("lsof") or shutil.which("fuser")
    if inspector:
        for database in (target / "v2" / "tasks-index.sqlite", target / "cli" / "db" / "db.sqlite"):
            if database.is_file():
                result = subprocess.run(
                    [inspector, "-t", str(database)] if Path(inspector).name == "lsof" else [inspector, str(database)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    fail(f"quit ZCode cleanly before setup changes; runtime database is open: {database}")


def probe_cli_version() -> str:
    trusted_path = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
    executable = shutil.which("zcode", path=trusted_path)
    if executable is None:
        return "not-installed"
    try:
        with tempfile.TemporaryDirectory(prefix="nddev-zcode-probe-") as probe_home:
            result = subprocess.run(
                [executable, "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=30,
                check=False,
                env={"HOME": probe_home, "PATH": trusted_path, "TMPDIR": probe_home},
            )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    text = (result.stdout or "").splitlines()[0] if result.stdout else ""
    text = re.sub(r"^v|^[^0-9]*", "", text.strip())
    return text if SEMVER_RE.fullmatch(text) else "unknown"


def detect_app_version() -> str:
    if platform_module.system() == "Darwin":
        apps = [Path(os.environ.get("NDDEV_APPLICATIONS_DIR", "/Applications")) / "ZCode.app", Path.home() / "Applications" / "ZCode.app"]
        for app in apps:
            plist = app / "Contents" / "Info.plist"
            if app.is_dir() and plist.is_file() and not plist.is_symlink():
                result = subprocess.run(
                    ["/usr/bin/defaults", "read", str(app / "Contents" / "Info"), "CFBundleShortVersionString"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    check=False,
                )
                value = result.stdout.strip()
                if SEMVER_RE.fullmatch(value):
                    return value
    return "unknown"


def check_runtime_version(*, plan: bool) -> None:
    section("ZCode version check")
    pinned_app = pinned_app_version()
    pinned_cli = pinned_cli_version()
    if plan:
        log("info", f"pinned app:  {pinned_app}    running: skipped-plan")
        log("info", f"pinned cli:  {pinned_cli}    running: skipped-plan")
        log("info", "live runtime detection is skipped in plan mode")
        return
    running_app = detect_app_version()
    running_cli = probe_cli_version()
    log("info", f"pinned app:  {pinned_app}    running: {running_app}")
    log("info", f"pinned cli:  {pinned_cli}    running: {running_cli}")
    if running_app != pinned_app:
        log("warn", f"ZCode app {running_app} != pinned {pinned_app}")
    if running_cli != pinned_cli:
        log("warn", f"ZCode CLI {running_cli} != pinned {pinned_cli}")


def select_marketplace(name: str) -> Path:
    if SETUP_RE.fullmatch(name) is None:
        fail("invalid setup id", 2)
    source = MARKETPLACES / name
    if not source.is_dir() or source.is_symlink():
        fail(f"unknown setup: {name}")
    manifest = load_json_file(source / "marketplace.json", "marketplace")
    if manifest.get("name") != name:
        fail(f"setup manifest identity mismatch: {name}")
    return source


def backup_entries(backups: Path) -> list[Path]:
    if not path_exists(backups):
        return []
    if not backups.is_dir() or backups.is_symlink():
        fail(f"backup root must be a real directory: {backups}", 2)
    entries: list[Path] = []
    seen: set[str] = set()
    for entry in sorted(backups.iterdir(), key=lambda item: item.name):
        match = BACKUP_RE.fullmatch(entry.name)
        if match is None:
            if re.fullmatch(r"[0-9]-.*-old\.zcode", entry.name):
                fail("invalid backup slot name")
            if entry.name.startswith(".slot-") and ".hold." in entry.name:
                fail("stale backup recovery hold requires attention", 2)
            continue
        if entry.is_symlink() or not entry.is_dir():
            fail("unsafe backup slot entry", 2)
        slot = match.group(1)
        if slot in seen:
            fail(f"duplicate backup slot: {slot}", 2)
        seen.add(slot)
        entries.append(entry)
    return entries


def backup_version_name(version: str, slot: int) -> str:
    if version != "unmanaged" and SEMVER_RE.fullmatch(version) is None:
        fail(f"invalid backup version: {version}")
    return f"{slot}-{version}-old.zcode"


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_backup_root(backups: Path, target: Path, *, create: bool) -> None:
    if backups == target or path_contains(backups, target) or path_contains(target, backups):
        fail("backup root must be disjoint from the target", 2)
    target_parent_identity = require_safe_directory(target.parent, "target parent")
    backup_parent_identity = require_safe_directory(backups.parent, "backup root parent")
    if target_parent_identity.uid != current_uid():
        fail("target parent must be owned by the current user", 2)
    if backup_parent_identity.uid != current_uid():
        fail("backup root parent must be owned by the current user", 2)
    if backup_parent_identity.dev != target_parent_identity.dev:
        fail("backup root must be on the same filesystem as the target", 2)
    if path_exists(backups):
        backup_identity = require_private_directory(backups, "backup root")
        if backup_identity.dev != target_parent_identity.dev:
            fail("backup root must be on the same filesystem as the target", 2)
    elif create:
        ensure_dir(backups)
        backup_identity = require_private_directory(backups, "backup root")
        if backup_identity.dev != target_parent_identity.dev:
            fail("backup root must be on the same filesystem as the target", 2)


def choose_backup_destination(
    backups: Path,
    version: str,
    target: Path,
    *,
    create: bool,
) -> tuple[Path, Path | None]:
    validate_backup_root(backups, target, create=create)
    entries = backup_entries(backups)
    occupied = {int(path.name.split("-", 1)[0]) for path in entries}
    for slot in range(10):
        if slot not in occupied:
            return backups / backup_version_name(version, slot), None
    oldest = min(entries, key=lambda path: path.stat().st_mtime_ns)
    slot = int(oldest.name.split("-", 1)[0])
    return backups / backup_version_name(version, slot), oldest


def rename_noreplace(source: Path, destination: Path, expected: FileIdentity | None = None) -> None:
    if expected is not None and lstat_identity(source) != expected:
        fail(f"source identity changed before rename: {source}")
    if path_exists(destination):
        fail(f"exclusive rename destination already exists: {destination}")
    os.rename(str(source), str(destination))
    if expected is not None:
        current = lstat_identity(destination)
        if identity_tuple(current) != identity_tuple(expected):
            fail(f"exclusive rename postcondition failed: {destination}")
    fsync_dir(source.parent)
    fsync_dir(destination.parent)


def remove_tree_identity(path: Path, expected: FileIdentity | None = None) -> None:
    if expected is not None and lstat_identity(path) != expected:
        fail(f"cleanup object identity changed: {path}", 2)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(str(path))
    else:
        path.unlink()
    fsync_dir(path.parent)


def object_digest(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_tree(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path_exists(root):
        return records
    base = root
    for current, dirs, files in os.walk(str(root), topdown=True, followlinks=False):
        current_path = Path(current)
        rel = "." if current_path == base else current_path.relative_to(base).as_posix()
        identity = lstat_identity(current_path)
        if identity.kind != "directory":
            fail(f"cleanup graph root must be a directory: {root}", 2)
        records.append(
            {
                "relative": rel,
                "kind": "directory",
                "mode": identity.mode,
                "uid": identity.uid,
                "dev": identity.dev,
                "ino": identity.ino,
                "nlink": identity.nlink,
                "size": identity.size,
                "mtime_ns": identity.mtime_ns,
                "children": sorted(dirs + files),
            }
        )
        for name in files:
            child = current_path / name
            item = lstat_identity(child)
            if item.kind != "file":
                fail(f"cleanup graph contains unsafe non-file: {child}", 2)
            records.append(
                {
                    "relative": child.relative_to(base).as_posix(),
                    "kind": "file",
                    "mode": item.mode,
                    "uid": item.uid,
                    "dev": item.dev,
                    "ino": item.ino,
                    "nlink": item.nlink,
                    "size": item.size,
                    "mtime_ns": item.mtime_ns,
                    "sha256": object_digest(child),
                }
            )
    return sorted(records, key=lambda entry: entry["relative"])


def cleanup_payload(target: Path, tombstone: Path) -> dict[str, Any]:
    records = snapshot_tree(tombstone)
    payload = {
        "schema": CLEANUP_SCHEMA,
        "product": PRODUCT,
        "target": str(target),
        "target_digest": target_digest_for(target),
        "entries": [
            {
                "kind": "directory",
                "relative": tombstone.name,
                "graph": records,
            }
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_CLEANUP_BYTES:
        fail("cleanup journal exceeds serialized byte bound before cleanup promotion", 2)
    return payload


def write_cleanup_prepare(target: Path, source: Path, tombstone: Path) -> None:
    root = cleanup_root_for(target)
    ensure_dir(root)
    payload = {
        "schema": CLEANUP_SCHEMA,
        "product": PRODUCT,
        "target": str(target),
        "target_digest": target_digest_for(target),
        "operation": "retire-backup-slot",
        "source": {"anchor": "backup-root", "relative": source.name, "kind": "directory"},
        "tombstone": {"anchor": "cleanup-root", "relative": tombstone.name, "kind": "directory"},
        "source_graph": snapshot_tree(source),
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(data) > MAX_CLEANUP_BYTES:
        fail("cleanup prepare intent exceeds serialized byte bound", 2)
    atomic_write(cleanup_prepare_path(target), data, 0o600)


def read_cleanup_prepare(target: Path) -> dict[str, Any]:
    raw = read_file_no_follow(cleanup_prepare_path(target), MAX_CLEANUP_BYTES, "cleanup prepare intent")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cleanup prepare intent is malformed: {exc}", 2)
    if not isinstance(payload, dict) or payload.get("schema") != CLEANUP_SCHEMA or payload.get("product") != PRODUCT:
        fail("cleanup prepare intent schema/product mismatch", 2)
    if payload.get("target") != str(target) or payload.get("target_digest") != target_digest_for(target):
        fail("cleanup prepare intent target binding mismatch", 2)
    return payload


def read_cleanup_journal(target: Path, *, recover_aliases: bool) -> dict[str, Any]:
    path = cleanup_journal_path(target)
    identity = require_private_file_identity(path, "cleanup journal")
    if identity.nlink != 1:
        if recover_aliases:
            recover_cleanup_journal_alias(path, identity_tuple(identity))
        else:
            fail("cleanup journal must not have hard-link aliases", 2)
    raw = read_file_no_follow(path, MAX_CLEANUP_BYTES, "cleanup journal")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cleanup journal is malformed: {exc}", 2)
    validate_cleanup_journal_payload(target, payload)
    return payload


def validate_cleanup_journal_payload(target: Path, payload: Any) -> None:
    if not isinstance(payload, dict):
        fail("cleanup journal must contain an object", 2)
    if payload.get("schema") != CLEANUP_SCHEMA or payload.get("product") != PRODUCT:
        fail("cleanup journal schema/product mismatch", 2)
    if payload.get("target") != str(target) or payload.get("target_digest") != target_digest_for(target):
        fail("cleanup journal target binding mismatch", 2)
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        fail("cleanup journal entries must be a non-empty list", 2)
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"kind", "relative", "graph"}:
            fail("cleanup journal entry shape is invalid", 2)
        relative = entry.get("relative")
        if not isinstance(relative, str) or "/" in relative or relative in {"", ".", ".."}:
            fail("cleanup journal relative path is invalid", 2)
        if relative in seen:
            fail("cleanup journal contains duplicate tombstones", 2)
        seen.add(relative)
        if entry.get("kind") != "directory":
            fail("cleanup journal entry kind is invalid", 2)
        if not isinstance(entry.get("graph"), list) or not entry["graph"]:
            fail("cleanup journal graph is missing", 2)


def recover_cleanup_journal_alias(path: Path, identity: tuple[int, int]) -> None:
    root = path.parent
    matches: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.name == path.name:
            continue
        if not child.name.startswith(".journal.") or not child.name.endswith(".tmp"):
            fail("cleanup journal parent contains unknown publication state", 2)
        item = require_private_file_identity(child, "cleanup journal alias")
        if identity_tuple(item) == identity:
            matches.append(child)
    if len(matches) != 1:
        fail("cleanup journal has unexpected hard-link aliases", 2)
    matches[0].unlink()
    fsync_dir(root)


def publish_cleanup_journal(target: Path, payload: dict[str, Any]) -> None:
    root = cleanup_root_for(target)
    ensure_dir(root)
    final = cleanup_journal_path(target)
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(data) > MAX_CLEANUP_BYTES:
        fail("cleanup journal exceeds serialized byte bound", 2)
    fd, temp_name = tempfile.mkstemp(prefix=".journal.", suffix=".tmp", dir=str(root))
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, data)
        os.fsync(fd)
        try:
            os.link(str(temp), str(final))
        except FileExistsError:
            fail("cleanup journal already exists", 2)
        temp.unlink()
        fsync_dir(root)
        validate_cleanup_journal_payload(target, read_cleanup_journal(target, recover_aliases=True))
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            if path_exists(temp):
                temp.unlink()
                fsync_dir(root)


def recover_prepare_if_needed(target: Path, backups: Path) -> None:
    prepare = cleanup_prepare_path(target)
    journal = cleanup_journal_path(target)
    if not path_exists(prepare):
        return
    if path_exists(journal):
        # Valid pending cleanup owns the tombstone now.
        read_cleanup_prepare(target)
        return
    payload = read_cleanup_prepare(target)
    source = backups / payload["source"]["relative"]
    tombstone = cleanup_root_for(target) / payload["tombstone"]["relative"]
    if path_exists(tombstone) and not path_exists(source):
        rename_noreplace(tombstone, source)
    elif path_exists(source) and not path_exists(tombstone):
        pass
    else:
        fail("cleanup preparation state is incoherent", 2)
    prepare.unlink()
    fsync_dir(prepare.parent)


def drain_cleanup_pending(target: Path) -> bool:
    journal = cleanup_journal_path(target)
    if not path_exists(journal):
        return False
    payload = read_cleanup_journal(target, recover_aliases=True)
    root = cleanup_root_for(target)
    for entry in payload["entries"]:
        tombstone = root / entry["relative"]
        if not path_exists(tombstone):
            continue
        if tombstone.is_symlink() or not tombstone.is_dir():
            fail("cleanup tombstone is unsafe", 2)
        # Validate the immutable graph once before destructive work.
        current_graph = snapshot_tree(tombstone)
        if current_graph != entry["graph"]:
            fail("cleanup tombstone object graph changed", 2)
        shutil.rmtree(str(tombstone))
        fsync_dir(root)
    if path_exists(journal):
        journal.unlink()
        fsync_dir(root)
    prepare = cleanup_prepare_path(target)
    if path_exists(prepare):
        prepare.unlink()
        fsync_dir(root)
    with contextlib.suppress(OSError):
        root.rmdir()
        fsync_dir(root.parent)
    cleanup_parent = root.parent
    with contextlib.suppress(OSError):
        cleanup_parent.rmdir()
        fsync_dir(cleanup_parent.parent)
    return True


def create_cleanup_for_retired_backup(target: Path, backups: Path, retired: Path) -> tuple[Path, Path] | None:
    if retired is None:
        return None
    root = cleanup_root_for(target)
    ensure_dir(root)
    tombstone = root / f"retired-{int(time.time() * 1000000)}-{retired.name}"
    write_cleanup_prepare(target, retired, tombstone)
    rename_noreplace(retired, tombstone)
    payload = cleanup_payload(target, tombstone)
    publish_cleanup_journal(target, payload)
    return tombstone, payload


def finish_cleanup(target: Path, payload: dict[str, Any] | None) -> bool:
    if payload is not None and not path_exists(cleanup_journal_path(target)):
        publish_cleanup_journal(target, payload)
    elif payload is None and not path_exists(cleanup_journal_path(target)):
        return False
    try:
        drain_cleanup_pending(target)
        return False
    except ManagerError:
        log("warn", "cleanup_pending=true")
        return True


def restore_runtime_from_backup(source: Path, target: Path, *, allow_unmanaged: bool) -> None:
    copy_runtime_state(source, target, unmanaged=allow_unmanaged)


def current_version(target: Path) -> str:
    if not path_exists(target):
        return "unmanaged"
    if not path_exists(target / "BUILD-VERSION"):
        return "unmanaged"
    return str(stamp_metadata(target)["build_version"])


def same_setup_noop(target: Path, setup: str, platform: str) -> bool:
    if not path_exists(target / "BUILD-VERSION"):
        return False
    try:
        stamp = stamp_metadata(target)
    except ManagerError:
        return False
    return (
        stamp.get("stamp_schema") == 2
        and stamp.get("setup_id") == setup
        and stamp.get("build_version") == build_version()
        and stamp.get("zcode_app_version") == pinned_app_version()
        and stamp.get("zcode_cli_version") == pinned_cli_version()
        and stamp.get("zcode_runtime") == zcode_runtime()
        and stamp.get("platform") == platform
        and not cleanup_pending_state(target, recover_aliases=False)["cleanup_pending"]
    )


def plan_install(options: Options, target: Path, backups: Path, platform: str, source: Path) -> None:
    log("info", f"profile: desktop ({'macOS' if platform == 'macos' else 'Ubuntu'})")
    log("info", f"target: {target}")
    parent = target.parent
    print(f"[DRY-RUN] acquire lock {parent / ('.' + target.name + '.nddev-lock')!s}")
    print(f"[DRY-RUN] acquire lock {backups / '.nddev-backups-lock'!s}")
    print(f"[DRY-RUN] create same-filesystem staging directory {parent / ('.' + target.name + '.stage.PLAN')} (0700)")
    check_runtime_version(plan=True)
    section("Build isolated staging tree")
    for rel in ("", "cli", "v2", "cli/agents", "cli/artifacts", "cli/db", "cli/log", "cli/plugins/cache", "cli/plugins/data", "v2/logs", "v2/crash"):
        path = parent / (f".{target.name}.stage.PLAN") / rel
        print(f"[DRY-RUN] mkdir -p -m 700 {path}")
    section(f"Copy source tree (marketplace: {source.name})")
    print(f"[DRY-RUN] cp -R {source / 'AGENTS.md'} {parent / ('.' + target.name + '.stage.PLAN') / 'AGENTS.md'}")
    section("Render config templates")
    validate_plan_configs(source, parse_env_file())
    log("info", "no build/.env - runtime tools must receive secrets from the environment")
    print(f"[DRY-RUN] write BUILD-VERSION -> {parent / ('.' + target.name + '.stage.PLAN') / 'BUILD-VERSION'}")
    section("Verify staged build")
    log("ok", "all checks passed (planned staged verification)")
    section("Commit transaction")
    print(f"[DRY-RUN] atomic rename {parent / ('.' + target.name + '.stage.PLAN')} {target}")
    print(f"[DRY-RUN] release lock {backups / '.nddev-backups-lock'}")
    print(f"[DRY-RUN] release lock {parent / ('.' + target.name + '.nddev-lock')}")


def validate_plan_configs(source: Path, env: dict[str, str]) -> None:
    stage = tempfile.mkdtemp(prefix="nddev-zcode-plan-render-")
    try:
        root = Path(stage)
        ensure_dir(root / "cli")
        ensure_dir(root / "v2")
        render_configs(source, root, env)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    log("ok", "plan config render, merge, and active-placeholder contracts passed")


def apply_install(options: Options, target: Path, backups: Path, platform: str, source: Path) -> bool:
    recover_live_prepare_if_needed(target)
    cleanup_drained = drain_cleanup_pending(target)
    recover_prepare_if_needed(target, backups)
    log("info", f"profile: desktop ({'macOS' if platform == 'macos' else 'Ubuntu'})")
    log("info", f"target: {target}")
    had_target = path_exists(target)
    adoption_mode = False
    old_version = "unmanaged"
    original_identity: FileIdentity | None = None
    if had_target:
        identity = lstat_identity(target)
        if identity.kind != "directory":
            fail("install target must be a directory")
        original_identity = identity
        old_version = current_version(target)
        if old_version == "unmanaged":
            if not options.adopt_unmanaged:
                fail("refusing to replace an unstamped target; use --adopt-unmanaged with an explicit --target")
            adoption_mode = True
        elif options.adopt_unmanaged:
            fail("--adopt-unmanaged is only valid for an existing unstamped target", 2)
        runtime_quiescent(target, plan=False)
    elif options.adopt_unmanaged:
        fail("--adopt-unmanaged requires an existing unstamped target", 2)
    parent = target.parent
    ensure_dir(parent)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage.", dir=str(parent)))
    os.chmod(stage, 0o700)
    fsync_dir(parent)
    stage_identity = lstat_identity(stage)
    backup_path: Path | None = None
    retired_payload: dict[str, Any] | None = None
    rollback_source: Path | None = None
    rollback_identity: FileIdentity | None = None
    try:
        check_runtime_version(plan=False)
        build_stage(source, stage, parse_env_file(), platform, source.name)
        if had_target:
            copy_runtime_state(target, stage, unmanaged=adoption_mode)
            verify_managed_tree(stage, setup=source.name)
            normalize_tree(stage)
            fsync_tree(stage)
        stage_identity = lstat_identity(stage)
        section("Commit transaction")
        destination: Path | None = None
        if had_target:
            destination, retired = choose_backup_destination(backups, old_version, target, create=True)
            if retired is not None:
                cleanup = create_cleanup_for_retired_backup(target, backups, retired)
                retired_payload = cleanup[1] if cleanup is not None else None
            log("info", f"backup target: {destination}")
            if adoption_mode:
                rollback_source = destination / "payload"
                write_live_prepare(
                    target,
                    backups,
                    operation="install",
                    stage=stage,
                    stage_identity=stage_identity,
                    source_identity=original_identity,
                    destination=rollback_source,
                )
                ensure_dir(destination)
                rename_noreplace(target, rollback_source, original_identity)
                write_adoption_envelope(destination, target)
                rollback_identity = original_identity
                normalize_tree(destination)
                fsync_tree(destination)
            else:
                backup_path = destination
                rollback_source = backup_path
                write_live_prepare(
                    target,
                    backups,
                    operation="install",
                    stage=stage,
                    stage_identity=stage_identity,
                    source_identity=original_identity,
                    destination=destination,
                )
                rename_noreplace(target, backup_path, original_identity)
                rollback_identity = original_identity
                normalize_tree(backup_path)
                fsync_tree(backup_path)
        else:
            write_live_prepare(
                target,
                backups,
                operation="install",
                stage=stage,
                stage_identity=stage_identity,
                source_identity=None,
                destination=None,
            )
        rename_noreplace(stage, target, stage_identity)
        stage = Path()
        unlink_live_prepare(target)
        cleanup_pending = finish_cleanup(target, retired_payload)
        return cleanup_drained or cleanup_pending
    except BaseException:
        if path_exists(target) and path_exists(rollback_source or Path("__missing__")):
            with contextlib.suppress(BaseException):
                failed = Path(tempfile.mkdtemp(prefix=f".{target.name}.failed.", dir=str(parent)))
                failed.rmdir()
                rename_noreplace(target, failed)
                rename_noreplace(rollback_source, target, rollback_identity)
                remove_tree_identity(failed)
        elif rollback_source is not None and path_exists(rollback_source) and not path_exists(target):
            with contextlib.suppress(BaseException):
                rename_noreplace(rollback_source, target, rollback_identity)
        if stage and path_exists(stage):
            with contextlib.suppress(BaseException):
                remove_tree_identity(stage, stage_identity)
        with contextlib.suppress(BaseException):
            recover_live_prepare_if_needed(target)
        raise


def write_adoption_envelope(envelope: Path, original_target: Path) -> None:
    payload = {
        "schema": 1,
        "type": "adopted-unmanaged",
        "original_target": str(original_target),
        "created_at": utc_now(),
        "installer_build": build_version(),
        "payload": "payload",
    }
    write_json(envelope / "NDDEV-BACKUP.json", payload)


def install_command(options: Options, target_text: str, backups_text: str) -> int:
    platform = detect_platform() if options.platform == "auto" else options.platform
    if platform not in {"macos", "ubuntu"}:
        fail("unsupported platform (expected macos|ubuntu)", 2)
    source = select_marketplace(options.setup)
    section("nddev-zcode-app installer")
    log("info", f"mode: {'APPLY' if options.apply else 'PLAN (dry-run)'}")
    log("info", f"platform: {platform}")
    log("info", f"repo root: {ROOT}")
    log("info", f"selected marketplace: {source.name} ({source})")
    if not options.apply:
        def body(locked: Path) -> None:
            backups = canonical_backups_from_text(backups_text)
            validate_backup_root(backups, locked, create=False)
            plan_install(options, locked, backups, platform, source)
        run_read_only(target_text, body)
        install_complete(source.name, platform, backup=None, cleanup_pending=False)
        return 0
    with target_coordination(target_text, create=True, shared=False) as target:
        backups = canonical_backups_from_text(backups_text)
        validate_backup_root(backups, target, create=False)
        cleanup_pending = apply_install(options, target, backups, platform, source)
        install_complete(source.name, platform, backup=None, cleanup_pending=cleanup_pending)
    return 0


def install_complete(setup: str, platform: str, *, backup: Path | None, cleanup_pending: bool) -> None:
    section("Install complete")
    log("ok", f"marketplace: {setup}")
    log("ok", f"build version: {build_version()}")
    log("ok", f"platform: {platform} ({'desktop' if platform == 'macos' else 'desktop/server'})")
    if backup is not None:
        log("ok", f"backup: {backup}")
    if cleanup_pending:
        log("warn", "cleanup_pending=true")
    log("info", "next: open the ZCode desktop app. credentials.json restored from backup.")


def canonical_backups_from_text(value: str) -> Path:
    if "\x00" in value or not value:
        fail("backup root path is invalid", 2)
    expanded = Path(value).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    if path_exists(expanded) and lstat_identity(expanded).kind != "directory":
        fail("backup root must be a directory endpoint", 2)
    try:
        parent = expanded.parent.resolve(strict=True)
    except OSError as exc:
        fail(f"backup root parent cannot be resolved safely: {exc}", 2)
    return parent / expanded.name


def find_slot(backups: Path, slot: str) -> Path | None:
    for entry in backup_entries(backups):
        if entry.name.startswith(f"{slot}-"):
            return entry
    return None


def adoption_payload(envelope: Path, target: Path, allow_relocation: bool) -> Path:
    marker = load_json_file(envelope / "NDDEV-BACKUP.json", "adopted backup marker")
    if marker.get("schema") != 1 or marker.get("type") != "adopted-unmanaged":
        fail("unsupported adopted backup marker")
    if marker.get("payload") != "payload":
        fail("adopted backup payload name must be exactly 'payload'")
    original = marker.get("original_target")
    if not isinstance(original, str) or not os.path.isabs(original) or Path(original).resolve() == Path("/"):
        fail("adopted backup original_target is not canonical")
    if not allow_relocation and original != str(target):
        fail("adopted backup belongs to a different target; explicit relocation is required")
    payload = envelope / "payload"
    if not payload.is_dir() or payload.is_symlink():
        fail("adopted backup payload escapes its envelope or is unsafe")
    return payload


def restore_command(options: Options, target_text: str, backups_text: str) -> int:
    if not options.apply:
        def body(locked: Path) -> None:
            backups = canonical_backups_from_text(backups_text)
            validate_backup_root(backups, locked, create=False)
            source = find_slot(backups, options.slot)
            section(f"Restore from backup slot {options.slot}")
            if source is None:
                fail(f"no safe backup found in slot {options.slot}")
            log("info", f"backup: {source}")
            log("info", f"target: {locked}")
            log("info", "mode: PLAN (dry-run)")
            print(f"[DRY-RUN] copy managed payload {source} -> {locked.parent / ('.' + locked.name + '.stage.PLAN')}")
        run_read_only(target_text, body)
        section("Restore complete")
        return 0
    with target_coordination(target_text, create=True, shared=False) as target:
        backups = canonical_backups_from_text(backups_text)
        recover_live_prepare_if_needed(target)
        validate_backup_root(backups, target, create=False)
        drain_cleanup_pending(target)
        recover_prepare_if_needed(target, backups)
        source = find_slot(backups, options.slot)
        if source is None:
            fail(f"no safe backup found in slot {options.slot}")
        payload = source
        restore_kind = "managed"
        if path_exists(source / "BUILD-VERSION"):
            verify_managed_tree(payload)
        else:
            restore_kind = "adopted-unmanaged"
            payload = adoption_payload(source, target, options.allow_target_relocation)
            safe_tree(payload)
            if path_exists(payload / "BUILD-VERSION"):
                fail("adopted-state payload must remain unstamped")
        had_target = path_exists(target)
        old_version = current_version(target) if had_target else "unmanaged"
        original_identity = lstat_identity(target) if had_target else None
        if had_target:
            if old_version == "unmanaged":
                fail("refusing to restore over an unstamped target", 2)
            safe_tree(target)
            runtime_quiescent(target, plan=False)
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage.", dir=str(target.parent)))
        stage_identity = lstat_identity(stage)
        rollback_source: Path | None = None
        rollback_identity: FileIdentity | None = None
        retired_payload: dict[str, Any] | None = None
        try:
            section(f"Restore from backup slot {options.slot}")
            log("info", f"backup: {source}")
            log("info", f"target: {target}")
            log("info", "mode: APPLY")
            safe_copytree(payload, stage / payload.name)
            copied_root = stage / payload.name
            for child in copied_root.iterdir():
                shutil.move(str(child), str(stage / child.name))
            copied_root.rmdir()
            normalize_tree(stage)
            fsync_tree(stage)
            if restore_kind == "managed":
                verify_managed_tree(stage)
            stage_identity = lstat_identity(stage)
            if had_target:
                destination, retired = choose_backup_destination(backups, old_version, target, create=True)
                if retired is not None:
                    cleanup = create_cleanup_for_retired_backup(target, backups, retired)
                    retired_payload = cleanup[1] if cleanup is not None else None
                rollback_source = destination
                write_live_prepare(
                    target,
                    backups,
                    operation="restore",
                    stage=stage,
                    stage_identity=stage_identity,
                    source_identity=original_identity,
                    destination=destination,
                )
                rename_noreplace(target, destination, original_identity)
                rollback_identity = original_identity
            else:
                write_live_prepare(
                    target,
                    backups,
                    operation="restore",
                    stage=stage,
                    stage_identity=stage_identity,
                    source_identity=None,
                    destination=None,
                )
            rename_noreplace(stage, target, stage_identity)
            stage = Path()
            unlink_live_prepare(target)
            cleanup_pending = finish_cleanup(target, retired_payload)
            section("Restore complete")
            if cleanup_pending:
                log("warn", "cleanup_pending=true")
            return 0
        except BaseException:
            if rollback_source is not None and path_exists(rollback_source) and not path_exists(target):
                with contextlib.suppress(BaseException):
                    rename_noreplace(rollback_source, target, rollback_identity)
            if stage and path_exists(stage):
                with contextlib.suppress(BaseException):
                    remove_tree_identity(stage, stage_identity)
            with contextlib.suppress(BaseException):
                recover_live_prepare_if_needed(target)
            raise


def remove_command(options: Options, target_text: str, backups_text: str) -> int:
    if not options.apply:
        def body(locked: Path) -> None:
            backups = canonical_backups_from_text(backups_text)
            section("nddev-zcode-app - remove")
            log("info", "mode: PLAN (dry-run)")
            log("info", f"target: {locked}")
            if not path_exists(locked):
                log("info", f"nothing to remove: {locked} does not exist")
            else:
                version = current_version(locked)
                destination, _ = choose_backup_destination(backups, version, locked, create=False)
                print(f"[DRY-RUN] atomic move {locked} {destination}")
        run_read_only(target_text, body)
        return 0
    with target_coordination(target_text, create=True, shared=False) as target:
        backups = canonical_backups_from_text(backups_text)
        recover_live_prepare_if_needed(target)
        validate_backup_root(backups, target, create=False)
        drain_cleanup_pending(target)
        recover_prepare_if_needed(target, backups)
        section("nddev-zcode-app - remove")
        log("info", "mode: APPLY")
        log("info", f"target: {target}")
        if not path_exists(target):
            log("info", f"nothing to remove: {target} does not exist")
            return 0
        version = current_version(target)
        if version == "unmanaged":
            fail("refusing to remove: target has no valid managed BUILD-VERSION")
        safe_tree(target)
        runtime_quiescent(target, plan=False)
        identity = lstat_identity(target)
        destination, retired = choose_backup_destination(backups, version, target, create=True)
        retired_payload = None
        if retired is not None:
            cleanup = create_cleanup_for_retired_backup(target, backups, retired)
            retired_payload = cleanup[1] if cleanup is not None else None
        write_live_prepare(
            target,
            backups,
            operation="remove",
            stage=None,
            stage_identity=None,
            source_identity=identity,
            destination=destination,
        )
        rename_noreplace(target, destination, identity)
        normalize_tree(destination)
        fsync_tree(destination)
        unlink_live_prepare(target)
        cleanup_pending = finish_cleanup(target, retired_payload)
        if cleanup_pending:
            log("warn", "cleanup_pending=true")
        log("ok", f"removed target into backup: {destination}")
        return 0


def list_backups(options: Options, backups_text: str) -> int:
    backups = canonical_backups_from_text(backups_text)
    section(f"Backups ({backups})")
    if not backups.is_dir():
        log("info", "no backups directory")
        return 0
    found = False
    for entry in backup_entries(backups):
        found = True
        if path_exists(entry / "BUILD-VERSION"):
            try:
                stamp = stamp_metadata(entry)
                print(
                    f"  {entry.name}  type=managed  build={stamp['build_version']}  installed={stamp['installed_at']}"
                )
            except ManagerError:
                print(f"  {entry.name}  type=invalid-managed-stamp")
        elif path_exists(entry / "NDDEV-BACKUP.json"):
            try:
                marker = load_json_file(entry / "NDDEV-BACKUP.json", "adoption envelope")
                print(
                    f"  {entry.name}  type=adopted-unmanaged build={marker['installer_build']} "
                    f"created={marker['created_at']} target={marker['original_target']}"
                )
            except ManagerError:
                print(f"  {entry.name}  type=invalid-adoption-envelope")
        else:
            print(f"  {entry.name}  type=invalid-or-unmanaged")
    if not found:
        log("info", "no backups found")
    return 0


def run_bootstrap(options: Options) -> int:
    if not BOOTSTRAP.is_file() or not os.access(str(BOOTSTRAP), os.X_OK):
        fail(f"Missing bootstrap script: {BOOTSTRAP}", 2)
    args = [str(BOOTSTRAP), "--platform", options.platform]
    args.append("--apply" if options.apply else "--plan")
    if options.allow_pinned_unnotarized:
        args.append("--allow-pinned-unnotarized")
    os.execv(str(BOOTSTRAP), args)
    return 127


def reject_option(errors: list[str], seen: dict[str, bool], key: str, label: str) -> None:
    if seen.get(key):
        errors.append(label)


def require_value(argv: list[str], index: int, option: str) -> str:
    if index + 1 >= len(argv) or argv[index + 1] == "" or argv[index + 1].startswith("-"):
        fail(f"{option} requires a non-empty value", 2)
    return argv[index + 1]


def parse_args(argv: list[str]) -> Options:
    options = Options()
    seen: dict[str, bool] = {}
    command_explicit = False
    if argv and not argv[0].startswith("-"):
        if argv[0] not in {"bootstrap", "install", "remove", "restore", "list", "status"}:
            print("Unknown command or argument", file=sys.stderr)
            print(usage(), file=sys.stderr)
            raise SystemExit(2)
        options.command = argv.pop(0)
        command_explicit = True
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in {"--setup", "--marketplace"}:
            if seen.get("setup"):
                fail("duplicate option is not allowed: --setup/--marketplace", 2)
            options.setup = require_value(argv, index, item)
            seen["setup"] = True
            index += 2
        elif item == "--target":
            if seen.get("target"):
                fail("duplicate option is not allowed: --target", 2)
            options.target = require_value(argv, index, item)
            seen["target"] = True
            index += 2
        elif item == "--platform":
            if seen.get("platform"):
                fail("duplicate option is not allowed: --platform", 2)
            options.platform = require_value(argv, index, item)
            seen["platform"] = True
            index += 2
        elif item == "--apply":
            if seen.get("apply"):
                fail("duplicate option is not allowed: --apply", 2)
            options.apply = True
            seen["apply"] = True
            index += 1
        elif item in {"--plan", "--dry-run"}:
            if seen.get("plan"):
                fail("duplicate option is not allowed: --plan/--dry-run", 2)
            options.apply = False
            seen["plan"] = True
            index += 1
        elif item == "--keep-backup":
            if seen.get("keep_backup"):
                fail("duplicate option is not allowed: --keep-backup", 2)
            options.keep_backup = require_value(argv, index, item)
            seen["keep_backup"] = True
            index += 2
        elif item == "--slot":
            if seen.get("slot"):
                fail("duplicate option is not allowed: --slot", 2)
            options.slot = require_value(argv, index, item)
            seen["slot"] = True
            index += 2
        elif item == "--adopt-unmanaged":
            options.adopt_unmanaged = True
            seen["adopt"] = True
            index += 1
        elif item == "--allow-target-relocation":
            options.allow_target_relocation = True
            seen["relocation"] = True
            index += 1
        elif item == "--allow-pinned-unnotarized":
            options.allow_pinned_unnotarized = True
            seen["allow_unnotarized"] = True
            index += 1
        elif item == "--backups":
            options.list_backups = True
            seen["backups"] = True
            index += 1
        elif item == "--json":
            options.json_output = True
            seen["json"] = True
            index += 1
        elif item in {"-l", "--list"}:
            if command_explicit and options.command != "list":
                fail(f"{item} cannot replace the explicit '{options.command}' command", 2)
            options.command = "list"
            command_explicit = True
            seen["list"] = True
            index += 1
        elif item in {"-h", "--help"}:
            print(usage(), end="")
            raise SystemExit(0)
        else:
            print("Unknown argument", file=sys.stderr)
            print(usage(), file=sys.stderr)
            raise SystemExit(2)
    if seen.get("apply") and seen.get("plan"):
        fail("--apply and --plan/--dry-run are mutually exclusive", 2)
    invalid: list[str] = []
    if options.command == "bootstrap":
        for key, label in (
            ("setup", "--setup/--marketplace"),
            ("target", "--target"),
            ("keep_backup", "--keep-backup"),
            ("slot", "--slot"),
            ("adopt", "--adopt-unmanaged"),
            ("relocation", "--allow-target-relocation"),
            ("backups", "--backups"),
            ("json", "--json"),
        ):
            reject_option(invalid, seen, key, label)
    elif options.command == "install":
        for key, label in (
            ("slot", "--slot"),
            ("relocation", "--allow-target-relocation"),
            ("allow_unnotarized", "--allow-pinned-unnotarized"),
            ("backups", "--backups"),
            ("json", "--json"),
        ):
            reject_option(invalid, seen, key, label)
    elif options.command == "remove":
        for key, label in (
            ("setup", "--setup/--marketplace"),
            ("platform", "--platform"),
            ("slot", "--slot"),
            ("adopt", "--adopt-unmanaged"),
            ("relocation", "--allow-target-relocation"),
            ("allow_unnotarized", "--allow-pinned-unnotarized"),
            ("backups", "--backups"),
            ("json", "--json"),
        ):
            reject_option(invalid, seen, key, label)
    elif options.command == "restore":
        for key, label in (
            ("setup", "--setup/--marketplace"),
            ("platform", "--platform"),
            ("adopt", "--adopt-unmanaged"),
            ("allow_unnotarized", "--allow-pinned-unnotarized"),
            ("backups", "--backups"),
            ("json", "--json"),
        ):
            reject_option(invalid, seen, key, label)
    elif options.command == "list":
        for key, label in (
            ("setup", "--setup/--marketplace"),
            ("target", "--target"),
            ("platform", "--platform"),
            ("apply", "--apply"),
            ("plan", "--plan/--dry-run"),
            ("keep_backup", "--keep-backup"),
            ("slot", "--slot"),
            ("adopt", "--adopt-unmanaged"),
            ("relocation", "--allow-target-relocation"),
            ("allow_unnotarized", "--allow-pinned-unnotarized"),
        ):
            reject_option(invalid, seen, key, label)
    elif options.command == "status":
        for key, label in (
            ("setup", "--setup/--marketplace"),
            ("platform", "--platform"),
            ("apply", "--apply"),
            ("plan", "--plan/--dry-run"),
            ("keep_backup", "--keep-backup"),
            ("slot", "--slot"),
            ("adopt", "--adopt-unmanaged"),
            ("relocation", "--allow-target-relocation"),
            ("allow_unnotarized", "--allow-pinned-unnotarized"),
            ("backups", "--backups"),
        ):
            reject_option(invalid, seen, key, label)
    if invalid:
        fail(f"option(s) not valid for '{options.command}': {', '.join(invalid)}", 2)
    if options.command == "list" and options.list_backups:
        if options.json_output:
            fail("--json is not valid with list --backups", 2)
        options.command = "list-backups"
    if options.command == "install":
        if not options.setup:
            fail("install requires --setup <id> (use 'list' to see options)", 2)
        if SETUP_RE.fullmatch(options.setup) is None:
            fail("invalid setup id", 2)
        if options.platform not in {"auto", "macos", "ubuntu"}:
            fail("unsupported platform (expected macos|ubuntu)", 2)
    if options.command == "restore":
        if not options.slot:
            fail("restore requires --slot <N> (0-9). Use 'list --backups' to see options.", 2)
        if not re.fullmatch(r"[0-9]", options.slot):
            fail("--slot must be a single digit 0-9", 2)
    if options.allow_target_relocation and (options.command != "restore" or not options.target):
        fail("--allow-target-relocation requires restore with an explicit --target", 2)
    return options


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        options = parse_args(list(argv))
        if not options.json_output:
            log("ok", "python3 on PATH")
        if options.command == "bootstrap":
            return run_bootstrap(options)
        if options.command == "list":
            return list_setups(options.json_output)
        env_values = parse_env_file()
        target_text = resolve_target_option(options, env_values)
        backups_text = resolve_backups_option(options, env_values)
        if options.command == "status":
            return show_status(options, target_text)
        if options.command == "list-backups":
            return list_backups(options, backups_text)
        if options.command == "install":
            return install_command(options, target_text, backups_text)
        if options.command == "restore":
            return restore_command(options, target_text, backups_text)
        if options.command == "remove":
            return remove_command(options, target_text, backups_text)
        fail(f"unsupported command: {options.command}", 2)
    except ManagerError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
