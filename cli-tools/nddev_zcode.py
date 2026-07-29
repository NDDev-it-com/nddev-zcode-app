#!/usr/bin/env python3
"""Dependency-free ZCode setup manager.

The shell entrypoint preserves the public CLI surface; this module owns the
filesystem transaction, monotonic coordination anchors, and machine-readable
state.  Keep this file Python 3.9-compatible.
"""

from __future__ import annotations

import contextlib
import ctypes
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform as platform_module
import re
import secrets
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
DEFAULT_SETUP = "nddev-builder"
POSTURES = {"full-auto", "safe"}
ANCHOR_SCHEMA = 1
CLEANUP_SCHEMA = 1
LIVE_PREPARE_SCHEMA = 2
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
CLEANUP_PARENT_NAME = ".nddev-zcode-cleanup"
ANCHOR_TEMP_RE = re.compile(r"\.nddev-zcode-anchor\.[0-9]+\.[0-9a-f]{16}\.tmp")
JOURNAL_TEMP_RE = re.compile(r"\.journal\.[0-9]+\.[0-9a-f]{16}\.tmp")
TARGET_ANCHOR_RE = re.compile(r"[0-9a-f]{64}\.lock")
TARGET_DIGEST_RE = re.compile(r"[0-9a-f]{64}")

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
    posture: str = "full-auto"
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
    gid: int
    nlink: int
    size: int
    mtime_ns: int
    kind: str


@dataclass
class DirectoryAuthority:
    path: Path
    fd: int
    identity: FileIdentity
    label: str
    private: bool = False

    def close(self) -> None:
        os.close(self.fd)

    def current(self) -> FileIdentity:
        opened = os.fstat(self.fd)
        current = os.lstat(str(self.path))
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            fail(f"{self.label} changed while authority was held: {self.path}", 2)
        identity = identity_from_stat(opened)
        if identity.kind != "directory":
            fail(f"{self.label} must remain a directory: {self.path}", 2)
        if identity.uid != current_uid():
            fail(f"{self.label} must remain owned by the current user: {self.path}", 2)
        if self.private and identity.mode & 0o077:
            fail(f"{self.label} must remain private: {self.path}", 2)
        if (identity.dev, identity.ino, identity.kind, identity.uid, identity.gid, identity.mode) != (
            self.identity.dev,
            self.identity.ino,
            self.identity.kind,
            self.identity.uid,
            self.identity.gid,
            self.identity.mode,
        ):
            fail(f"{self.label} authority binding changed: {self.path}", 2)
        return identity

    def refresh_after_manager_child_mutation(self) -> None:
        current = self.current()
        self.identity = current


@dataclass
class CleanupAuthority:
    target: Path
    parent: DirectoryAuthority
    root: DirectoryAuthority

    def close(self) -> None:
        errors: list[str] = []
        for authority in (self.root, self.parent):
            try:
                authority.close()
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            raise ManagerError(f"cannot release cleanup authority safely: {errors[0]}", 2)


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


@dataclass(frozen=True)
class CanonicalResource:
    path: Path
    digest: str

    @property
    def anchor_path(self) -> Path:
        return resource_anchor_path(self.digest)


@dataclass(frozen=True)
class PendingCoordinationSnapshot:
    root_identity: FileIdentity | None
    entries: tuple[tuple[str, FileIdentity], ...]
    live_prepare: bytes | None
    cleanup_prepare: bytes | None


@dataclass(frozen=True)
class DurableFileBinding:
    identity: FileIdentity
    data: bytes


@dataclass(frozen=True)
class TransactionResources:
    target: Path
    backups: Path
    pending_backups: tuple[Path, ...]


def usage() -> str:
    return """Usage: cli-tools/scripts/install.sh [bootstrap|install|remove|restore|list|status] [options]

Commands:
  bootstrap             Download and install the ZCode desktop app + CLI (from zero).
  install (default)     Build ~/.zcode from the managed setup.
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
  --setup <id>              Managed setup to build from (default: nddev-builder).
  --marketplace <id>        Backward-compatible alias for --setup.
  --posture full-auto|safe  Interaction posture (default: full-auto).
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


def reject_transaction_path_controls(value: str, role: str) -> str:
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        fail(f"{role} path contains a forbidden control character", 2)
    return value


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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        fail(f"cannot open directory safely for fsync: {path}: {exc}", 2)
    try:
        opened = os.fstat(fd)
        current = os.lstat(str(path))
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            fail(f"directory changed while opening for fsync: {path}", 2)
        if not stat.S_ISDIR(opened.st_mode):
            fail(f"fsync target must be a directory: {path}", 2)
        os.fsync(fd)
    finally:
        os.close(fd)


def lstat_identity(path: Path) -> FileIdentity:
    try:
        info = os.lstat(str(path))
    except OSError as exc:
        fail(f"cannot inspect path safely: {path}: {exc}", 2)
    return identity_from_stat(info)


def identity_from_stat(info: os.stat_result) -> FileIdentity:
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
        gid=info.st_gid,
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
        "gid": identity.gid,
        "nlink": identity.nlink,
        "size": identity.size,
        "mtime_ns": identity.mtime_ns,
        "kind": identity.kind,
    }


def restore_parent_metadata(path: Path, identity: FileIdentity) -> None:
    current = lstat_identity(path)
    if current.kind != "directory" or identity.kind != "directory":
        fail(f"parent metadata restore requires directories: {path}", 2)
    if identity_tuple(current) != identity_tuple(identity) or current.uid != identity.uid or current.gid != identity.gid:
        fail(f"parent directory identity changed during rollback: {path}", 2)
    if current.mode != identity.mode:
        os.chmod(path, identity.mode)
    os.utime(path, ns=(identity.mtime_ns, identity.mtime_ns), follow_symlinks=False)
    fsync_dir(path)


def identity_from_payload(value: Any, label: str) -> FileIdentity:
    keys = {"dev", "ino", "mode", "uid", "gid", "nlink", "size", "mtime_ns", "kind"}
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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        fail(f"{label} must be a real non-symlink directory: {path}: {exc}", 2)
    try:
        opened = os.fstat(fd)
        current = os.lstat(str(path))
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            fail(f"{label} changed while opening: {path}", 2)
        if not stat.S_ISDIR(opened.st_mode):
            fail(f"{label} must be a real non-symlink directory: {path}", 2)
        if opened.st_uid != current_uid():
            fail(f"{label} must be owned by the current user: {path}", 2)
        mode = stat.S_IMODE(opened.st_mode)
        if mode & 0o077:
            fail(f"{label} must not grant group/world permissions: {path}", 2)
        return identity_from_stat(opened)
    finally:
        os.close(fd)


def validate_directory_identity(identity: FileIdentity, label: str, *, private: bool) -> None:
    if identity.kind != "directory":
        fail(f"{label} must be a real non-symlink directory", 2)
    if identity.uid != current_uid():
        fail(f"{label} must be owned by the current user", 2)
    if private and identity.mode & 0o077:
        fail(f"{label} must not grant group/world permissions", 2)


def open_directory_authority(path: Path, label: str, *, private: bool) -> DirectoryAuthority:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        fail(f"{label} must be a real non-symlink directory: {path}: {exc}", 2)
    try:
        opened = os.fstat(fd)
        current = os.lstat(str(path))
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            fail(f"{label} changed while opening: {path}", 2)
        identity = identity_from_stat(opened)
        validate_directory_identity(identity, label, private=private)
        return DirectoryAuthority(path=path, fd=fd, identity=identity, label=label, private=private)
    except BaseException:
        os.close(fd)
        raise


def open_child_directory_authority(
    parent: DirectoryAuthority,
    name: str,
    label: str,
    *,
    private: bool,
) -> DirectoryAuthority:
    if "/" in name or name in {"", ".", ".."}:
        fail(f"{label} child name is invalid", 2)
    parent.current()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent.fd)
    except OSError as exc:
        fail(f"{label} must be a real non-symlink directory: {parent.path / name}: {exc}", 2)
    try:
        opened = os.fstat(fd)
        current = os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            fail(f"{label} changed while opening: {parent.path / name}", 2)
        identity = identity_from_stat(opened)
        validate_directory_identity(identity, label, private=private)
        return DirectoryAuthority(path=parent.path / name, fd=fd, identity=identity, label=label, private=private)
    except BaseException:
        os.close(fd)
        raise


def fsync_authority(authority: DirectoryAuthority) -> None:
    authority.current()
    os.fsync(authority.fd)
    authority.refresh_after_manager_child_mutation()


def restore_authority_metadata(authority: DirectoryAuthority, identity: FileIdentity) -> None:
    current = authority.current()
    if identity_tuple(current) != identity_tuple(identity) or current.uid != identity.uid or current.gid != identity.gid:
        fail(f"directory identity changed during rollback: {authority.path}", 2)
    if current.mode != identity.mode:
        os.fchmod(authority.fd, identity.mode)
    os.utime(authority.path, ns=(identity.mtime_ns, identity.mtime_ns), follow_symlinks=False)
    fsync_authority(authority)
    authority.identity = identity


def ensure_private_child_directory(
    parent: DirectoryAuthority,
    name: str,
    label: str,
) -> DirectoryAuthority:
    if "/" in name or name in {"", ".", ".."}:
        fail(f"{label} child name is invalid", 2)
    try:
        return open_child_directory_authority(parent, name, label, private=True)
    except ManagerError:
        if path_exists(parent.path / name):
            raise
    parent_before = parent.current()
    created_identity: FileIdentity | None = None
    child: DirectoryAuthority | None = None
    try:
        os.mkdir(name, 0o700, dir_fd=parent.fd)
        child = open_child_directory_authority(parent, name, label, private=True)
        os.fchmod(child.fd, 0o700)
        child.identity = identity_from_stat(os.fstat(child.fd))
        created_identity = child.identity
        fsync_authority(parent)
        return child
    except BaseException:
        if child is not None:
            with contextlib.suppress(BaseException):
                current = child.current()
                if created_identity is not None and identity_tuple(current) == identity_tuple(created_identity):
                    child.close()
                    child = None
                    os.rmdir(name, dir_fd=parent.fd)
                    fsync_authority(parent)
        if child is not None:
            with contextlib.suppress(OSError):
                child.close()
        restore_authority_metadata(parent, parent_before)
        raise


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
    parent_before = lstat_identity(parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(parent))
    temp = Path(temp_name)
    replaced = False
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp), str(path))
        replaced = True
        fsync_dir(parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        removed_temp = False
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()
            removed_temp = True
        if removed_temp and not replaced:
            with contextlib.suppress(ManagerError):
                restore_parent_metadata(parent, parent_before)
        raise


def json_pretty_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def json_compact_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def coordination_root() -> Path:
    return Path("/tmp") / f"nddev-zcode-app-bootstrap-locks-{current_uid()}"


def product_anchor_path() -> Path:
    return coordination_root() / "global.lock"


def resource_digest_for(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def resource_anchor_path(digest: str) -> Path:
    return coordination_root() / f"{digest}.lock"


def canonical_resource(path: Path) -> CanonicalResource:
    return CanonicalResource(path=path, digest=resource_digest_for(path))


def target_digest_for(path: Path) -> str:
    return resource_digest_for(path)


def target_anchor_path(digest: str) -> Path:
    return resource_anchor_path(digest)


def anchor_payload(anchor: str, digest: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": ANCHOR_SCHEMA,
        "product": PRODUCT,
        "anchor": anchor,
    }
    if digest is not None:
        # Keep the exact legacy marker so old managers can validate anchors
        # published for either path role during a rolling upgrade.
        payload["target_digest"] = digest
    return payload


def anchor_bytes(anchor: str, digest: str | None) -> bytes:
    return json.dumps(anchor_payload(anchor, digest), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    ) + b"\n"


def write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        offset += os.write(fd, data[offset:])


def is_known_anchor_name(name: str) -> bool:
    return name == "global.lock" or TARGET_ANCHOR_RE.fullmatch(name) is not None


def ensure_coordination_root() -> None:
    root = coordination_root()
    if path_exists(root):
        require_private_directory(root, "product coordination namespace")
        return
    parent = open_directory_authority(root.parent, "product coordination namespace parent", private=False)
    created: DirectoryAuthority | None = None
    parent_before = parent.current()
    try:
        os.mkdir(root.name, 0o700, dir_fd=parent.fd)
    except FileExistsError:
        parent.close()
        require_private_directory(root, "product coordination namespace")
        return
    try:
        created = open_child_directory_authority(parent, root.name, "product coordination namespace", private=True)
        os.fchmod(created.fd, 0o700)
        fsync_authority(parent)
        require_private_directory(root, "product coordination namespace")
    except BaseException:
        if created is not None:
            with contextlib.suppress(BaseException):
                current = created.current()
                if identity_tuple(current) == identity_tuple(created.identity):
                    created.close()
                    created = None
                    os.rmdir(root.name, dir_fd=parent.fd)
                    fsync_authority(parent)
        if created is not None:
            with contextlib.suppress(OSError):
                created.close()
        restore_authority_metadata(parent, parent_before)
        raise
    finally:
        if created is not None:
            created.close()
        parent.close()


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
            if path_exists(child) and not is_known_anchor_name(name):
                fail(f"anchor parent contains unknown entry: {name}", 2)
            continue
        child_identity = require_private_file_identity(child, f"anchor temporary alias {name}")
        if identity_tuple(child_identity) == identity:
            matches.append(child)
    if len(matches) != 1:
        fail("anchor file has unexpected hard-link aliases", 2)
    matches[0].unlink()
    fsync_dir(root)


def validate_anchor_temp(path: Path, *, anchor: str, digest: str | None) -> FileIdentity:
    if not ANCHOR_TEMP_RE.fullmatch(path.name):
        fail(f"anchor temporary file has an invalid name: {path.name}", 2)
    identity = require_private_file_identity(path, "anchor temporary file")
    if identity.mode != 0o600:
        fail(f"anchor temporary file must have mode 0600: {path}", 2)
    if identity.nlink != 1:
        fail(f"anchor temporary file must not have hard-link aliases before publication: {path}", 2)
    raw = read_file_no_follow(path, MAX_ANCHOR_BYTES, "anchor temporary file")
    if raw != anchor_bytes(anchor, digest):
        fail(f"anchor temporary file binding mismatch: {path}", 2)
    return identity


def anchor_temp_binding(path: Path) -> tuple[str, str | None]:
    raw = read_file_no_follow(path, MAX_ANCHOR_BYTES, "anchor temporary file")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"anchor temporary file is malformed: {path}: {exc}", 2)
    if payload == anchor_payload("product", None):
        return "product", None
    if (
        isinstance(payload, dict)
        and payload.get("schema") == ANCHOR_SCHEMA
        and payload.get("product") == PRODUCT
        and payload.get("anchor") == "target"
        and set(payload) == {"schema", "product", "anchor", "target_digest"}
        and isinstance(payload["target_digest"], str)
        and TARGET_DIGEST_RE.fullmatch(payload["target_digest"]) is not None
    ):
        return "target", payload["target_digest"]
    fail(f"anchor temporary file binding mismatch: {path}", 2)


def open_private_temp_file(root: Path, *, prefix: str, mode: int) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(64):
        path = root / f"{prefix}{os.getpid()}.{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(str(path), flags, mode)
        except FileExistsError:
            continue
        os.fchmod(fd, mode)
        return fd, path
    fail(f"cannot allocate bounded temporary file in {root}", 2)


def recover_staged_anchor_before_publish(path: Path, *, anchor: str, digest: str | None) -> bool:
    root = path.parent
    matches: list[Path] = []
    try:
        names = sorted(os.listdir(str(root)))
    except OSError as exc:
        fail(f"cannot scan anchor namespace before publication: {exc}", 2)
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("anchor namespace exceeds bounded entry count", 2)
    for name in names:
        child = root / name
        if ANCHOR_TEMP_RE.fullmatch(name):
            binding = anchor_temp_binding(child)
            if binding == (anchor, digest):
                validate_anchor_temp(child, anchor=anchor, digest=digest)
                matches.append(child)
            continue
        if not is_known_anchor_name(name):
            fail(f"anchor namespace contains unknown entry before publication: {name}", 2)
    if not matches:
        return False
    if len(matches) != 1:
        fail("anchor namespace contains duplicate staged publications", 2)
    temp = matches[0]
    if path_exists(path):
        handle = open_anchor(
            path,
            anchor=anchor,
            digest=digest,
            create=False,
            shared=False,
            recover_aliases=True,
        )
        if handle is None:
            raise ConcurrentNamespaceChange("anchor winner disappeared during staged recovery")
        try:
            if path_exists(temp):
                validate_anchor_temp(temp, anchor=anchor, digest=digest)
                temp.unlink()
                fsync_dir(root)
        finally:
            handle.close()
        return True
    validate_anchor_temp(temp, anchor=anchor, digest=digest)
    try:
        os.link(str(temp), str(path))
    except FileExistsError:
        handle = open_anchor(
            path,
            anchor=anchor,
            digest=digest,
            create=False,
            shared=False,
            recover_aliases=True,
        )
        if handle is None:
            raise ConcurrentNamespaceChange("anchor winner disappeared before validation")
        try:
            validate_anchor_temp(temp, anchor=anchor, digest=digest)
            temp.unlink()
            fsync_dir(root)
        finally:
            handle.close()
        return False
    fsync_dir(root)
    handle = open_anchor(
        path,
        anchor=anchor,
        digest=digest,
        create=False,
        shared=False,
        recover_aliases=True,
    )
    if handle is None:
        raise ConcurrentNamespaceChange("published staged anchor disappeared before validation")
    try:
        if path_exists(temp):
            validate_anchor_temp(temp, anchor=anchor, digest=digest)
            temp.unlink()
            fsync_dir(root)
    finally:
        handle.close()
    return True


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
    identity = identity_from_stat(opened)
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
            identity = identity_from_stat(reopened)
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
        root = path.parent
        if path_exists(root):
            try:
                names = sorted(os.listdir(str(root)))
            except OSError as exc:
                fail(f"cannot scan anchor namespace safely: {exc}", 2)
            if len(names) > MAX_NAMESPACE_ENTRIES:
                fail("anchor namespace exceeds bounded entry count", 2)
            for name in names:
                if ANCHOR_TEMP_RE.fullmatch(name):
                    fail("anchor publication is incomplete", 2)
                if not is_known_anchor_name(name):
                    fail(f"anchor namespace contains unknown entry: {name}", 2)
        return None
    else:
        require_private_directory(path.parent, "product coordination namespace")

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
    if recover_staged_anchor_before_publish(path, anchor=anchor, digest=digest):
        handle = open_anchor(
            path,
            anchor=anchor,
            digest=digest,
            create=False,
            shared=shared,
            recover_aliases=True,
        )
        if handle is None:
            raise ConcurrentNamespaceChange("recovered anchor disappeared before open")
        return handle
    payload = anchor_bytes(anchor, digest)
    parent_before = lstat_identity(root)
    fd, temp = open_private_temp_file(root, prefix=".nddev-zcode-anchor.", mode=0o600)
    final_visible = False
    try:
        write_all(fd, payload)
        os.fsync(fd)
        validate_anchor_temp(temp, anchor=anchor, digest=digest)
        try:
            os.link(str(temp), str(path))
            final_visible = True
        except FileExistsError:
            os.close(fd)
            fd = -1
            handle = open_anchor(
                path,
                anchor=anchor,
                digest=digest,
                create=False,
                shared=shared,
                recover_aliases=True,
            )
            if handle is None:
                raise ConcurrentNamespaceChange("anchor winner disappeared before open")
            try:
                validate_anchor_temp(temp, anchor=anchor, digest=digest)
                temp.unlink()
                fsync_dir(root)
            except BaseException:
                pass
            return handle
        except OSError as exc:
            fail(f"cannot publish anchor safely: {path}: {exc}", 2)
        os.close(fd)
        fd = -1
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
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
        if path_exists(temp):
            if final_visible:
                pass
            else:
                removed_temp = False
                with contextlib.suppress(FileNotFoundError):
                    temp.unlink()
                    removed_temp = True
                if removed_temp:
                    restore_parent_metadata(root, parent_before)
        raise


def close_lock_handles(handles: list[LockHandle]) -> None:
    first_error: BaseException | None = None
    for handle in reversed(handles):
        try:
            handle.close()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def existing_resource_digests(*, recover_staged: bool) -> list[str]:
    root = coordination_root()
    require_private_directory(root, "product coordination namespace")
    names = sorted(os.listdir(str(root)))
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("anchor namespace exceeds bounded entry count", 2)
    staged: set[str] = set()
    for name in names:
        if name == "global.lock":
            continue
        if TARGET_ANCHOR_RE.fullmatch(name):
            continue
        if ANCHOR_TEMP_RE.fullmatch(name):
            anchor, digest = anchor_temp_binding(root / name)
            if anchor == "target" and digest is not None:
                staged.add(digest)
                continue
        fail(f"anchor namespace contains unknown entry: {name}", 2)
    if recover_staged:
        for digest in sorted(staged):
            handle = publish_anchor(
                resource_anchor_path(digest),
                anchor="target",
                digest=digest,
                shared=False,
            )
            handle.close()
        names = sorted(os.listdir(str(root)))
    elif staged:
        fail("anchor publication is incomplete", 2)
    return sorted(
        name[:-5]
        for name in names
        if TARGET_ANCHOR_RE.fullmatch(name) is not None
    )


def acquire_resources(
    resources: list[CanonicalResource],
    *,
    create: bool,
    shared: bool,
) -> tuple[list[LockHandle], bool]:
    handles: list[LockHandle] = []
    missing = False
    unique = {resource.digest: resource for resource in resources}
    try:
        for resource in sorted(unique.values(), key=lambda item: (item.digest, str(item.path))):
            handle = open_anchor(
                resource.anchor_path,
                anchor="target",
                digest=resource.digest,
                create=create,
                shared=shared,
                recover_aliases=create,
            )
            if handle is None:
                missing = True
            else:
                handles.append(handle)
        return handles, missing
    except BaseException:
        close_lock_handles(handles)
        raise


def pending_coordination_snapshot(target: Path) -> PendingCoordinationSnapshot:
    root = cleanup_root_for(target)
    if not path_exists(root):
        return PendingCoordinationSnapshot(None, (), None, None)
    root_identity = require_private_directory(root, "cleanup state root")
    names = sorted(os.listdir(str(root)))
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("cleanup state root exceeds bounded entry count", 2)
    entries = tuple((name, lstat_identity(root / name)) for name in names)
    live_name = live_prepare_path(target).name
    cleanup_name = cleanup_prepare_path(target).name
    live = (
        read_file_no_follow(root / live_name, MAX_CLEANUP_BYTES, "live transaction prepare intent")
        if live_name in names
        else None
    )
    cleanup = (
        read_file_no_follow(root / cleanup_name, MAX_CLEANUP_BYTES, "cleanup prepare intent")
        if cleanup_name in names
        else None
    )
    return PendingCoordinationSnapshot(root_identity, entries, live, cleanup)


def pending_backup_paths(snapshot: PendingCoordinationSnapshot) -> tuple[Path, ...]:
    values: list[str] = []
    for raw, label, nested in (
        (snapshot.live_prepare, "live transaction prepare intent", False),
        (snapshot.cleanup_prepare, "cleanup prepare intent", True),
    ):
        if raw is None:
            continue
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(f"{label} is malformed: {exc}", 2)
        value = payload.get("backup_root") if isinstance(payload, dict) else None
        if nested:
            value = value.get("path") if isinstance(value, dict) else None
        if not isinstance(value, str):
            fail(f"{label} backup root binding is invalid", 2)
        reject_transaction_path_controls(value, f"{label} backup root")
        path = Path(value)
        if not path.is_absolute() or path == Path("/") or str(path) != value:
            fail(f"{label} backup root binding is not canonical", 2)
        values.append(value)
    return tuple(Path(value) for value in sorted(set(values)))


def validate_locked_resource_path(path: Path, label: str) -> None:
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        fail(f"{label} parent cannot be resolved safely: {exc}", 2)
    if parent / path.name != path:
        fail(f"{label} binding is not canonical", 2)
    if path_exists(path) and lstat_identity(path).kind != "directory":
        fail(f"{label} must be a directory endpoint", 2)


@contextlib.contextmanager
def transaction_coordination(
    target_text: str,
    backups_text: str,
) -> Iterator[TransactionResources]:
    product = open_anchor(
        product_anchor_path(),
        anchor="product",
        create=True,
        shared=False,
        recover_aliases=True,
    )
    if product is None:
        fail("product coordination anchor could not be published", 2)
    all_handles: list[LockHandle] = []
    required_handles: list[LockHandle] = []
    try:
        target = canonical_target_from_text(target_text, inspect_endpoint=False)
        backups = canonical_backups_from_text(backups_text, inspect_endpoint=False)
        validate_resource_disjoint(target, backups)

        # Product EX prevents new old binaries from starting. Locking every
        # existing path anchor waits out old binaries that already handed off.
        for digest in existing_resource_digests(recover_staged=True):
            handle = open_anchor(
                resource_anchor_path(digest),
                anchor="target",
                digest=digest,
                create=False,
                shared=False,
                recover_aliases=True,
            )
            if handle is None:
                raise ConcurrentNamespaceChange("resource anchor disappeared during quiescence")
            all_handles.append(handle)

        by_digest = {handle.path.name[:-5]: handle for handle in all_handles}
        target_resource = canonical_resource(target)
        if target_resource.digest not in by_digest:
            target_handles, _ = acquire_resources([target_resource], create=True, shared=False)
            all_handles.extend(target_handles)
            by_digest.update({handle.path.name[:-5]: handle for handle in target_handles})

        before = pending_coordination_snapshot(target)
        pending = pending_backup_paths(before)
        for pending_path in pending:
            validate_resource_disjoint(target, pending_path)
        required = [target_resource, canonical_resource(backups)]
        required.extend(canonical_resource(path) for path in pending)
        missing = [
            resource
            for resource in required
            if resource.digest not in by_digest
        ]
        new_handles, _ = acquire_resources(missing, create=True, shared=False)
        all_handles.extend(new_handles)
        by_digest.update({handle.path.name[:-5]: handle for handle in new_handles})
        required_handles = [by_digest[item.digest] for item in sorted(
            {resource.digest: resource for resource in required}.values(),
            key=lambda item: (item.digest, str(item.path)),
        )]

        after = pending_coordination_snapshot(target)
        if after != before:
            fail("pending transaction authority changed during resource acquisition", 2)
        validate_locked_resource_path(target, "target")
        validate_locked_resource_path(backups, "backup root")
        for path in pending:
            validate_locked_resource_path(path, "pending backup root")

        unrelated = [handle for handle in all_handles if handle not in required_handles]
        close_lock_handles(unrelated)
        all_handles = required_handles
        yield TransactionResources(target, backups, pending)
    finally:
        close_error: BaseException | None = None
        try:
            close_lock_handles(all_handles)
        except BaseException as exc:
            close_error = exc
        try:
            product.close()
        except BaseException as exc:
            if close_error is None:
                close_error = exc
        if close_error is not None:
            raise close_error


def run_read_only_resources(
    canonicalizers: tuple[Callable[[], Path], ...],
    callback: Callable[[tuple[Path, ...]], Any],
    *,
    include_pending_for_target: bool = False,
) -> Any:
    product_path = product_anchor_path()
    product = open_anchor(
        product_path,
        anchor="product",
        create=False,
        shared=True,
        recover_aliases=False,
    )
    if product is not None:
        handles: list[LockHandle] = []
        try:
            paths = tuple(canonicalize() for canonicalize in canonicalizers)
            handles, missing = acquire_resources(
                [canonical_resource(path) for path in paths],
                create=False,
                shared=True,
            )
            if include_pending_for_target:
                before = pending_coordination_snapshot(paths[0])
                pending = pending_backup_paths(before)
                pending_handles, pending_missing = acquire_resources(
                    [canonical_resource(path) for path in pending],
                    create=False,
                    shared=True,
                )
                handles.extend(pending_handles)
                missing = missing or pending_missing
                if pending_coordination_snapshot(paths[0]) != before:
                    fail("pending transaction authority changed during read coordination", 2)
                for pending_path in pending:
                    validate_resource_disjoint(paths[0], pending_path)
                    if path_exists(canonical_resource(pending_path).anchor_path):
                        validate_locked_resource_path(pending_path, "pending backup root")
            if not missing:
                product.close()
                product = None
            return callback(paths)
        finally:
            close_lock_handles(handles)
            if product is not None:
                product.close()

    before = validate_product_namespace_empty()
    paths = tuple(canonicalize() for canonicalize in canonicalizers)
    result = callback(paths)
    after = namespace_snapshot()
    if not same_namespace(before, after):
        return run_read_only_resources(
            canonicalizers,
            callback,
            include_pending_for_target=include_pending_for_target,
        )
    return result


def run_read_only(target_text: str, callback: Callable[[Path], Any]) -> Any:
    return run_read_only_resources(
        (lambda: canonical_target_from_text(target_text),),
        lambda paths: callback(paths[0]),
    )


def run_transaction_plan(
    target_text: str,
    backups_text: str,
    callback: Callable[[Path, Path], Any],
) -> Any:
    return run_read_only_resources(
        (
            lambda: canonical_target_from_text(target_text),
            lambda: canonical_backups_from_text(backups_text),
        ),
        lambda paths: callback(paths[0], paths[1]),
        include_pending_for_target=True,
    )


def run_backup_read_only(backups_text: str, callback: Callable[[Path], Any]) -> Any:
    return run_read_only_resources(
        (lambda: canonical_backups_from_text(backups_text),),
        lambda paths: callback(paths[0]),
    )


def canonical_target_from_text(value: str, *, inspect_endpoint: bool = True) -> Path:
    value = reject_transaction_path_controls(value, "target")
    if not value:
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
    if inspect_endpoint and path_exists(target):
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
        value = options.target
    elif env_file.get("ZCODE_TARGET"):
        value = env_file["ZCODE_TARGET"]
    else:
        value = str(Path.home() / ".zcode")
    return reject_transaction_path_controls(value, "target")


def resolve_backups_option(options: Options, env_file: dict[str, str]) -> str:
    if options.keep_backup:
        value = options.keep_backup
    elif env_file.get("ZCODE_BACKUPS_DIR"):
        value = env_file["ZCODE_BACKUPS_DIR"]
    else:
        value = str(Path.home() / ".zcode-backups")
    return reject_transaction_path_controls(value, "backup root")


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
                {
                    "id": entry.name,
                    "default": entry.name == DEFAULT_SETUP,
                    "postures": sorted(POSTURES),
                    "description": description,
                    "plugin_count": len(plugins),
                }
            )
    if json_output:
        print(json.dumps({"schema_version": 1, "setups": setups}, separators=(",", ":")))
    else:
        section("Available setups")
        if not setups:
            print("  no setups found")
        for setup in setups:
            suffix = " (default)" if setup.get("default") else ""
            print(f"  {setup['id']:<24} {setup['description']}{suffix}")
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
        posture = data.get("posture", "full-auto")
        if not isinstance(posture, str) or posture not in POSTURES:
            fail("BUILD-VERSION.posture is invalid")
        stamp_schema = 2
    else:
        setup = None
        posture = "full-auto"
        stamp_schema = 0 if "schema" not in data else 1
    return {
        "build_version": data["build_version"],
        "installed_at": data["installed_at"],
        "platform": data["platform"],
        "setup_id": setup,
        "posture": posture,
        "stamp_schema": stamp_schema,
        "zcode_app_version": data["zcode_app_version"],
        "zcode_cli_version": data["zcode_cli_version"],
        "zcode_runtime": data["zcode_runtime"],
    }


def cleanup_parent_for(target: Path) -> Path:
    return target.parent / CLEANUP_PARENT_NAME


def cleanup_root_for(target: Path) -> Path:
    return cleanup_parent_for(target) / target_digest_for(target)


def cleanup_journal_path(target: Path) -> Path:
    return cleanup_root_for(target) / "journal.json"


def cleanup_prepare_path(target: Path) -> Path:
    return cleanup_root_for(target) / "prepare.json"


def live_prepare_path(target: Path) -> Path:
    return cleanup_root_for(target) / "live-prepare.json"


def ensure_private_directory(path: Path, label: str) -> FileIdentity:
    if path_exists(path):
        return require_private_directory(path, label)
    parent = path.parent
    parent_before = lstat_identity(parent)
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
        os.chmod(path, 0o700)
        fsync_dir(parent)
        return require_private_directory(path, label)
    except BaseException:
        if created and path_exists(path):
            with contextlib.suppress(OSError):
                path.rmdir()
        restore_parent_metadata(parent, parent_before)
        raise


@contextlib.contextmanager
def cleanup_authority(target: Path, *, create: bool) -> Iterator[CleanupAuthority]:
    parent_path = cleanup_parent_for(target)
    root_path = cleanup_root_for(target)
    digest = target_digest_for(target)
    if parent_path.name != CLEANUP_PARENT_NAME or root_path.parent != parent_path or root_path.name != digest:
        fail("cleanup namespace binding is invalid", 2)
    if TARGET_DIGEST_RE.fullmatch(digest) is None:
        fail("cleanup target digest binding is invalid", 2)
    target_parent = open_directory_authority(target.parent, "target parent", private=False)
    cleanup_parent: DirectoryAuthority | None = None
    cleanup_root: DirectoryAuthority | None = None
    try:
        if create:
            cleanup_parent = ensure_private_child_directory(
                target_parent,
                CLEANUP_PARENT_NAME,
                "cleanup namespace parent",
            )
            cleanup_root = ensure_private_child_directory(cleanup_parent, digest, "cleanup state root")
        else:
            cleanup_parent = open_child_directory_authority(
                target_parent,
                CLEANUP_PARENT_NAME,
                "cleanup namespace parent",
                private=True,
            )
            cleanup_root = open_child_directory_authority(
                cleanup_parent,
                digest,
                "cleanup state root",
                private=True,
            )
        authority = CleanupAuthority(target=target, parent=cleanup_parent, root=cleanup_root)
        cleanup_parent = None
        cleanup_root = None
        try:
            yield authority
        finally:
            authority.close()
    finally:
        if cleanup_root is not None:
            cleanup_root.close()
        if cleanup_parent is not None:
            cleanup_parent.close()
        target_parent.close()


def cleanup_root_authority(target: Path, *, create: bool) -> Path:
    with cleanup_authority(target, create=create) as authority:
        authority.root.current()
        return authority.root.path


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
    adoption_marker: dict[str, Any] | None = None,
) -> None:
    with cleanup_authority(target, create=True) as authority:
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
            "target_graph": None if source_identity is None else snapshot_tree(target),
            "stage_graph": None if stage is None else snapshot_tree(stage),
            "adoption_marker": adoption_marker,
            "target_parent_identity": identity_payload(lstat_identity(target.parent)),
            "backup_parent_identity": identity_payload(lstat_identity(backups.parent)),
            "backup_root_identity": (
                identity_payload(lstat_identity(backups)) if path_exists(backups) else None
            ),
        }
        payload["schema"] = LIVE_PREPARE_SCHEMA
        data = json_compact_bytes(payload)
        if len(data) > MAX_CLEANUP_BYTES:
            fail("live transaction prepare intent exceeds serialized byte bound", 2)
        atomic_write_child(authority.root, live_prepare_path(target).name, data, 0o600)


def read_live_prepare(target: Path) -> dict[str, Any]:
    with cleanup_authority(target, create=False) as authority:
        raw = read_child_file(authority.root, live_prepare_path(target).name, MAX_CLEANUP_BYTES, "live transaction prepare intent")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(f"live transaction prepare intent is malformed: {exc}", 2)
    if not isinstance(payload, dict):
        fail("live transaction prepare intent must contain an object", 2)
    legacy_required = {
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
        "target_graph",
        "stage_graph",
        "adoption_marker",
    }
    current_required = legacy_required | {
        "target_parent_identity",
        "backup_parent_identity",
        "backup_root_identity",
    }
    if set(payload) != legacy_required and set(payload) != current_required:
        fail("live transaction prepare intent keys are invalid", 2)
    schema = payload["schema"]
    if (
        schema not in {CLEANUP_SCHEMA, LIVE_PREPARE_SCHEMA}
        or payload["product"] != PRODUCT
        or payload["type"] != "live-rename-prepare"
    ):
        fail("live transaction prepare intent schema/product mismatch", 2)
    if schema == CLEANUP_SCHEMA and set(payload) != legacy_required:
        fail("legacy live transaction prepare intent keys are invalid", 2)
    if schema == LIVE_PREPARE_SCHEMA and set(payload) != current_required:
        fail("live transaction prepare intent parent bindings are missing", 2)
    if payload["target"] != str(target) or payload["target_digest"] != target_digest_for(target):
        fail("live transaction prepare intent target binding mismatch", 2)
    if payload["operation"] not in {"install", "restore", "remove"}:
        fail("live transaction prepare operation is invalid", 2)
    if payload["target_name"] != target.name:
        fail("live transaction prepare target name mismatch", 2)
    backup_root_value = payload["backup_root"]
    if (
        not isinstance(backup_root_value, str)
        or any(ord(character) < 32 or ord(character) == 127 for character in backup_root_value)
        or not os.path.isabs(backup_root_value)
        or Path(backup_root_value) == Path("/")
        or str(Path(backup_root_value)) != backup_root_value
    ):
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
    if payload["target_graph"] is not None:
        validate_tree_graph_payload(payload["target_graph"], "live target graph")
    if payload["stage_graph"] is not None:
        validate_tree_graph_payload(payload["stage_graph"], "live stage graph")
    marker = payload["adoption_marker"]
    if marker is not None:
        validate_adoption_marker_payload(
            marker,
            expected_target=target,
            expected_build=build_version(),
        )
    if schema == LIVE_PREPARE_SCHEMA:
        identity_from_payload(payload["target_parent_identity"], "live target parent")
        identity_from_payload(payload["backup_parent_identity"], "live backup parent")
        if payload["backup_root_identity"] is not None:
            identity_from_payload(payload["backup_root_identity"], "live backup root")
    return payload


def validate_tree_graph_payload(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        fail(f"{label} must be a non-empty list", 2)
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            fail(f"{label} entries must be objects", 2)
        relative = entry.get("relative")
        kind = entry.get("kind")
        if not isinstance(relative, str) or relative in {"", ".."} or relative.startswith("/"):
            fail(f"{label} relative path is invalid", 2)
        if any(part in {"", ".."} for part in relative.split("/") if relative != "."):
            fail(f"{label} relative path is invalid", 2)
        if relative in seen:
            fail(f"{label} contains duplicate paths", 2)
        seen.add(relative)
        if kind == "directory":
            required = {"relative", "kind", "mode", "uid", "gid", "dev", "ino", "nlink", "size", "mtime_ns", "children"}
            if set(entry) != required or not isinstance(entry.get("children"), list):
                fail(f"{label} directory entry shape is invalid", 2)
        elif kind == "file":
            required = {"relative", "kind", "mode", "uid", "gid", "dev", "ino", "nlink", "size", "mtime_ns", "sha256"}
            if set(entry) != required or not isinstance(entry.get("sha256"), str):
                fail(f"{label} file entry shape is invalid", 2)
            if re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
                fail(f"{label} file digest is invalid", 2)
        else:
            fail(f"{label} contains unsupported kind", 2)
        for field in ("mode", "uid", "gid", "dev", "ino", "nlink", "size", "mtime_ns"):
            item = entry.get(field)
            if not isinstance(item, int) or item < 0:
                fail(f"{label} field is invalid: {field}", 2)


def identity_from_tree_entry(entry: dict[str, Any], label: str) -> FileIdentity:
    if entry["kind"] not in {"directory", "file"}:
        fail(f"{label} contains unsupported kind", 2)
    return FileIdentity(
        dev=entry["dev"],
        ino=entry["ino"],
        mode=entry["mode"],
        uid=entry["uid"],
        gid=entry["gid"],
        nlink=entry["nlink"],
        size=entry["size"],
        mtime_ns=entry["mtime_ns"],
        kind=entry["kind"],
    )


def adoption_envelope_payload(original_target: Path) -> dict[str, Any]:
    return {
        "schema": 1,
        "type": "adopted-unmanaged",
        "original_target": str(original_target),
        "created_at": utc_now(),
        "installer_build": build_version(),
        "payload": "payload",
    }


def canonical_adoption_original_target(value: Any) -> Path:
    if (
        not isinstance(value, str)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or not os.path.isabs(value)
    ):
        fail("adoption backup marker original_target is not canonical", 2)
    original = Path(value)
    if original == Path("/"):
        fail("adoption backup marker original_target is not canonical", 2)
    try:
        resolved = original.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        fail(f"adoption backup marker original_target cannot be resolved safely: {exc}", 2)
    if str(resolved) != value:
        fail("adoption backup marker original_target is not canonical", 2)
    return original


def validate_adoption_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        fail("adoption backup marker created_at is not canonical UTC", 2)
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        fail("adoption backup marker created_at is not canonical UTC", 2)
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if canonical != value:
        fail("adoption backup marker created_at is not canonical UTC", 2)
    return value


def validate_adoption_marker_payload(
    value: Any,
    *,
    expected_target: Path | None = None,
    expected_build: str | None = None,
) -> Path:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "type",
        "original_target",
        "created_at",
        "installer_build",
        "payload",
    }:
        fail("adoption backup marker is malformed", 2)
    if (
        value["schema"] != 1
        or value["type"] != "adopted-unmanaged"
        or value["payload"] != "payload"
    ):
        fail("adoption backup marker schema/type/payload is invalid", 2)
    installer_build = value["installer_build"]
    if not isinstance(installer_build, str) or SEMVER_RE.fullmatch(installer_build) is None:
        fail("adoption backup marker installer_build is not canonical SemVer", 2)
    validate_adoption_timestamp(value["created_at"])
    original = canonical_adoption_original_target(value["original_target"])
    if expected_target is not None and original != expected_target:
        fail("adoption backup marker target binding mismatch", 2)
    if expected_build is not None and installer_build != expected_build:
        fail("adoption backup marker build binding mismatch", 2)
    return original


def require_tree_graph(path: Path, expected: list[dict[str, Any]] | None, label: str) -> None:
    if expected is None:
        return
    validate_tree_graph_payload(expected, label)
    if snapshot_tree(path) != expected:
        fail(f"{label} changed before recovery", 2)


def durable_file_binding(path: Path, expected: bytes, label: str) -> DurableFileBinding:
    identity = require_private_file_identity(path, label)
    data = read_file_no_follow(path, MAX_CLEANUP_BYTES, label)
    if data != expected:
        fail(f"{label} bytes changed at the commit decision", 2)
    return DurableFileBinding(identity, data)


def require_durable_file_binding(path: Path, binding: DurableFileBinding, label: str) -> None:
    if require_private_file_identity(path, label) != binding.identity:
        fail(f"{label} identity changed at the commit decision", 2)
    if read_file_no_follow(path, MAX_CLEANUP_BYTES, label) != binding.data:
        fail(f"{label} bytes changed at the commit decision", 2)


def live_prepare_binding(target: Path, payload: dict[str, Any]) -> DurableFileBinding:
    return durable_file_binding(
        live_prepare_path(target),
        json_compact_bytes(payload),
        "live transaction prepare intent",
    )


def require_object_binding(
    path: Path,
    expected_identity: FileIdentity | None,
    expected_graph: list[dict[str, Any]] | None,
    label: str,
) -> None:
    if expected_identity is None or not path_exists(path):
        fail(f"{label} is absent at the commit decision", 2)
    if lstat_identity(path) != expected_identity:
        fail(f"{label} identity changed at the commit decision", 2)
    require_tree_graph(path, expected_graph, label)


def require_parent_binding(path: Path, expected: FileIdentity, label: str) -> None:
    current = lstat_identity(path)
    if (
        identity_tuple(current) != identity_tuple(expected)
        or current.kind != expected.kind
        or current.uid != expected.uid
        or current.gid != expected.gid
        or current.mode != expected.mode
    ):
        fail(f"{label} identity changed at the commit decision", 2)


def validate_live_parent_bindings(payload: dict[str, Any], target: Path, backups: Path) -> None:
    if payload["schema"] != LIVE_PREPARE_SCHEMA:
        require_safe_directory(target.parent, "live target parent")
        require_safe_directory(backups.parent, "live backup parent")
        return
    require_parent_binding(
        target.parent,
        identity_from_payload(payload["target_parent_identity"], "live target parent"),
        "live target parent",
    )
    require_parent_binding(
        backups.parent,
        identity_from_payload(payload["backup_parent_identity"], "live backup parent"),
        "live backup parent",
    )
    if payload["backup_root_identity"] is not None:
        require_parent_binding(
            backups,
            identity_from_payload(payload["backup_root_identity"], "live backup root"),
            "live backup root",
        )


def validate_retired_cleanup_authority(target: Path, backups: Path) -> None:
    if not path_exists(cleanup_prepare_path(target)):
        return
    prepare = read_cleanup_prepare(target)
    validate_prepare_backup_binding(prepare, backups)
    tombstone = cleanup_root_for(target) / prepare["tombstone"]["relative"]
    root_entries = [item for item in prepare["source_graph"] if item["relative"] == "."]
    if len(root_entries) != 1:
        fail("cleanup prepare source graph root is invalid", 2)
    require_object_binding(
        tombstone,
        identity_from_tree_entry(root_entries[0], "cleanup prepare source graph root"),
        prepare["source_graph"],
        "retired cleanup tombstone",
    )
    journal = read_cleanup_journal(target, recover_aliases=False)
    matches = [
        entry
        for entry in journal["entries"]
        if entry["relative"] == tombstone.name and entry["graph"] == prepare["source_graph"]
    ]
    if len(matches) != 1:
        fail("cleanup journal does not bind the retired tombstone", 2)


def validate_live_commit_decision(
    target: Path,
) -> tuple[dict[str, Any], DurableFileBinding]:
    payload = read_live_prepare(target)
    binding = live_prepare_binding(target, payload)
    backups = Path(payload["backup_root"])
    validate_live_parent_bindings(payload, target, backups)
    stage_identity = (
        None
        if payload["stage_identity"] is None
        else identity_from_payload(payload["stage_identity"], "live stage")
    )
    source_identity = (
        None
        if payload["target_identity"] is None
        else identity_from_payload(payload["target_identity"], "live target")
    )
    if payload["operation"] == "remove":
        if path_exists(target):
            fail("removed target reappeared before commit", 2)
    else:
        require_object_binding(target, stage_identity, payload["stage_graph"], "published live target")
    if source_identity is not None:
        backup_name = payload["backup_name"]
        if backup_name is None:
            fail("live rollback source binding is missing", 2)
        destination = backups / backup_name
        require_object_binding(
            destination,
            source_identity,
            payload["target_graph"],
            "live rollback source",
        )
    validate_retired_cleanup_authority(target, backups)
    require_durable_file_binding(
        live_prepare_path(target),
        binding,
        "live transaction prepare intent",
    )
    return payload, binding


def unlink_live_prepare(target: Path, binding: DurableFileBinding) -> None:
    with cleanup_authority(target, create=False) as authority:
        prepare = live_prepare_path(target)
        require_durable_file_binding(prepare, binding, "live transaction prepare intent")
        try:
            stat_child(authority.root, prepare.name, "live transaction prepare intent")
        except ManagerError:
            if not path_exists(prepare):
                return
            raise
        os.unlink(prepare.name, dir_fd=authority.root.fd)
        fsync_authority(authority.root)
        try:
            names = sorted(os.listdir(authority.root.fd))
        except OSError as exc:
            fail(f"cannot inspect cleanup state root after prepare removal: {exc}", 2)
        if not names:
            root = cleanup_root_for(target)
            os.rmdir(root.name, dir_fd=authority.parent.fd)
            fsync_authority(authority.parent)
            try:
                parent_names = sorted(os.listdir(authority.parent.fd))
            except OSError as exc:
                fail(f"cannot inspect cleanup namespace parent after prepare removal: {exc}", 2)
            if not parent_names:
                parent_identity = authority.parent.current()
                target_parent = open_directory_authority(target.parent, "target parent", private=False)
                try:
                    current = stat_child(target_parent, CLEANUP_PARENT_NAME, "cleanup namespace parent")
                    if identity_tuple(current) == identity_tuple(parent_identity):
                        os.rmdir(CLEANUP_PARENT_NAME, dir_fd=target_parent.fd)
                        fsync_authority(target_parent)
                finally:
                    target_parent.close()


def cleanup_empty_backup_container(
    destination: Path | None,
    backups: Path,
    adoption_marker: dict[str, Any] | None = None,
) -> None:
    if destination is None or destination.parent == backups:
        return
    container = destination.parent
    if not path_exists(container):
        return
    require_private_directory(container, "adoption backup envelope")
    try:
        children = sorted(os.listdir(str(container)))
    except OSError as exc:
        fail(f"cannot inspect adoption backup envelope: {exc}", 2)
    if not children:
        container.rmdir()
        fsync_dir(container.parent)
        return
    if adoption_marker is None:
        fail("adoption backup envelope contains unbound residue", 2)
    if children != ["NDDEV-BACKUP.json"]:
        fail("adoption backup envelope contains unexpected residue", 2)
    marker = container / "NDDEV-BACKUP.json"
    require_private_file_identity(marker, "adoption backup marker")
    if read_file_no_follow(marker, MAX_CLEANUP_BYTES, "adoption backup marker") != json_compact_bytes(adoption_marker):
        fail("adoption backup marker changed before rollback cleanup", 2)
    marker.unlink()
    fsync_dir(container)
    container.rmdir()
    fsync_dir(container.parent)


def recover_live_prepare_if_needed(target: Path) -> None:
    prepare = live_prepare_path(target)
    if not path_exists(prepare):
        return
    payload = read_live_prepare(target)
    prepare_binding = live_prepare_binding(target, payload)
    backups = Path(payload["backup_root"])
    validate_live_parent_bindings(payload, target, backups)
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
    target_graph = payload["target_graph"]
    stage_graph = payload["stage_graph"]
    adoption_marker = payload["adoption_marker"]
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
            require_object_binding(target, source_identity, target_graph, "live remove target")
            cleanup_empty_backup_container(destination, backups, adoption_marker)
            require_object_binding(target, source_identity, target_graph, "live remove target")
            unlink_live_prepare(target, prepare_binding)
            return
        if not path_exists(target) and destination_exists:
            require_object_binding(destination, source_identity, target_graph, "live remove backup")
            unlink_live_prepare(target, prepare_binding)
            return
        fail("live remove prepare state is incoherent", 2)

    if target_matches_stage and not stage_exists:
        require_object_binding(target, stage_identity, stage_graph, "live published stage")
        if source_identity is not None and destination is not None:
            require_object_binding(destination, source_identity, target_graph, "live rollback source")
        validate_retired_cleanup_authority(target, backups)
        unlink_live_prepare(target, prepare_binding)
        return
    if target_matches_source and not stage_exists and not destination_exists:
        require_object_binding(target, source_identity, target_graph, "live target")
        cleanup_empty_backup_container(destination, backups, adoption_marker)
        require_object_binding(target, source_identity, target_graph, "live target")
        unlink_live_prepare(target, prepare_binding)
        return
    if target_matches_source and stage_exists and not destination_exists:
        require_object_binding(target, source_identity, target_graph, "live target")
        if stage_identity is None:
            fail("live prepare stage identity is missing", 2)
        require_object_binding(stage, stage_identity, stage_graph, "live stage")
        remove_tree_identity(stage, stage_identity)
        cleanup_empty_backup_container(destination, backups, adoption_marker)
        require_object_binding(target, source_identity, target_graph, "live target")
        unlink_live_prepare(target, prepare_binding)
        return
    if not path_exists(target) and source_identity is not None and destination_exists:
        require_object_binding(destination, source_identity, target_graph, "live rollback source")
        if stage_exists:
            if stage_identity is None:
                fail("live prepare stage identity is missing", 2)
            require_object_binding(stage, stage_identity, stage_graph, "live stage")
            remove_tree_identity(stage, stage_identity)
        rename_noreplace(destination, target, source_identity)
        require_object_binding(target, source_identity, target_graph, "live restored target")
        cleanup_empty_backup_container(destination, backups, adoption_marker)
        require_object_binding(target, source_identity, target_graph, "live restored target")
        unlink_live_prepare(target, prepare_binding)
        return
    if not path_exists(target) and source_identity is None and stage_exists:
        if stage_identity is None:
            fail("live prepare stage identity is missing", 2)
        require_object_binding(stage, stage_identity, stage_graph, "live stage")
        remove_tree_identity(stage, stage_identity)
        unlink_live_prepare(target, prepare_binding)
        return
    if not path_exists(target) and source_identity is None and not stage_exists:
        unlink_live_prepare(target, prepare_binding)
        return
    fail("live transaction prepare state is incoherent", 2)


def cleanup_pending_state(target: Path, *, recover_aliases: bool = False) -> dict[str, Any]:
    parent = cleanup_parent_for(target)
    if path_exists(parent):
        require_private_directory(parent, "cleanup namespace parent")
    root = cleanup_root_for(target)
    if not path_exists(root):
        return {"cleanup_pending": False, "cleanup_pending_entries": []}
    with cleanup_authority(target, create=False) as authority:
        names = sorted(os.listdir(authority.root.fd))
        if live_prepare_path(target).name in names:
            fail("live transaction recovery is incomplete", 2)
        journal = cleanup_journal_path(target)
        if journal.name not in names:
            prepare = cleanup_prepare_path(target)
            if prepare.name in names:
                fail("cleanup preparation is incomplete", 2)
            if names:
                fail("cleanup state root contains incomplete publication state", 2)
            fail("cleanup state root is incomplete", 2)
            return {"cleanup_pending": False, "cleanup_pending_entries": []}
    payload = read_cleanup_journal(target, recover_aliases=recover_aliases)
    return {
        "cleanup_pending": True,
        "cleanup_pending_entries": [
            {"kind": entry["kind"], "relative": entry["relative"]} for entry in payload["entries"]
        ],
    }


def recover_empty_cleanup_root_before_mutation(target: Path) -> None:
    root = cleanup_root_for(target)
    if not path_exists(root) or path_exists(cleanup_journal_path(target)) or path_exists(cleanup_prepare_path(target)):
        return
    with cleanup_authority(target, create=False) as authority:
        try:
            names = sorted(os.listdir(authority.root.fd))
        except OSError as exc:
            fail(f"cannot inspect cleanup state root: {exc}", 2)
        if names:
            fail("cleanup state root contains incomplete publication state", 2)
        os.rmdir(root.name, dir_fd=authority.parent.fd)
        fsync_authority(authority.parent)
        try:
            parent_names = sorted(os.listdir(authority.parent.fd))
        except OSError as exc:
            fail(f"cannot inspect cleanup namespace parent: {exc}", 2)
        if not parent_names:
            parent_identity = authority.parent.current()
            target_parent = open_directory_authority(target.parent, "target parent", private=False)
            try:
                current = stat_child(target_parent, CLEANUP_PARENT_NAME, "cleanup namespace parent")
                if identity_tuple(current) == identity_tuple(parent_identity):
                    os.rmdir(CLEANUP_PARENT_NAME, dir_fd=target_parent.fd)
                    fsync_authority(target_parent)
            finally:
                target_parent.close()


def coordination_report(target: Path) -> dict[str, Any]:
    digest = target_digest_for(target)
    return {
        "root": str(coordination_root()),
        "product_anchor": {
            "path": str(product_anchor_path()),
            "state": "present" if path_exists(product_anchor_path()) else "absent",
        },
        "target_anchor": {
            "path": str(target_anchor_path(digest)),
            "state": "present" if path_exists(target_anchor_path(digest)) else "absent",
            "target_digest": digest,
        },
    }


def cleanup_report(target: Path, cleanup: dict[str, Any]) -> dict[str, Any]:
    entries = cleanup["cleanup_pending_entries"]
    return {
        "target_digest": target_digest_for(target),
        "pending": bool(cleanup["cleanup_pending"]),
        "entry_count": len(entries),
        "entries": entries,
    }


def print_plan_coordination(target: Path, cleanup: dict[str, Any]) -> None:
    coordination = coordination_report(target)
    cleanup_state = cleanup_report(target, cleanup)
    print(
        "[DRY-RUN] use product coordination anchor "
        f"{coordination['product_anchor']['path']} ({coordination['product_anchor']['state']})"
    )
    print(
        "[DRY-RUN] use canonical target coordination anchor "
        f"{coordination['target_anchor']['path']} ({coordination['target_anchor']['state']})"
    )
    print(
        "[DRY-RUN] inspect cleanup state "
        f"target_digest={cleanup_state['target_digest']} "
        f"entries={cleanup_state['entry_count']} "
        f"cleanup_pending={str(cleanup_state['pending']).lower()}"
    )


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
    payload["coordination"] = coordination_report(target)
    payload["cleanup"] = cleanup_report(target, cleanup)
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
        print(f"  posture: {payload.get('posture', 'full-auto')}")
        print(f"  build: {payload['build_version']}")
        print(f"  platform: {payload['platform']}")
        print(f"  installed: {payload['installed_at']}")
    coordination = payload["coordination"]
    print(f"  product_anchor: {coordination['product_anchor']['state']} {coordination['product_anchor']['path']}")
    print(f"  target_anchor: {coordination['target_anchor']['state']} {coordination['target_anchor']['path']}")
    cleanup = payload["cleanup"]
    print(f"  cleanup_pending: {str(cleanup['pending']).lower()} entries={cleanup['entry_count']}")
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
    atomic_write(path, json_pretty_bytes(value), mode)


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
                roots.append((plugin.name, plugin))
    for origin, root in roots:
        for component in ("skills", "commands", "agents"):
            directory = root / component
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir(), key=lambda item: item.name):
                if entry.name == ".gitkeep":
                    continue
                key = (component, entry.name)
                location = f"{origin}/{component}/{entry.name}"
                if key in seen:
                    fail(
                        f"user-scope {component} name collision: {entry.name} "
                        f"(from {seen[key]}; {location})"
                    )
                seen[key] = location


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
            fd = os.open(str(child), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(fd)
                current = os.lstat(str(child))
                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    fail(f"tree file changed while opening for fsync: {child}", 2)
                if not stat.S_ISREG(opened.st_mode):
                    fail(f"tree fsync target must be a regular file: {child}", 2)
                os.fsync(fd)
            finally:
                os.close(fd)
        fsync_dir(Path(root))


def apply_posture(target: Path, setup: str, posture: str) -> None:
    if posture not in POSTURES:
        fail("invalid posture", 2)
    agents = target / "AGENTS.md"
    if posture == "safe":
        with agents.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n### NDDev Safe Posture\n\n"
                "- Prefer read-only inspection and explicit plans before changing files.\n"
                "- Ask before destructive filesystem operations, live package installs, "
                "network publication, or credential-bearing commands.\n"
                "- Keep hooks disabled unless the user explicitly enables them after reviewing "
                "the rendered configuration.\n"
            )
        config_path = target / "cli/config.json"
        config = load_json_file(config_path, "cli config")
        hooks = config.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            fail("cli hooks config must be an object")
        hooks["enabled"] = False
        write_json(config_path, config)
    write_json(
        target / "NDDEV-POSTURE.json",
        {
            "schema": 1,
            "product": PRODUCT,
            "setup_id": setup,
            "posture": posture,
        },
    )


def write_stamp(target: Path, platform: str, setup: str, posture: str) -> None:
    payload = {
        "schema": 2,
        "setup_id": setup,
        "posture": posture,
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
        f"wrote BUILD-VERSION ({payload['build_version']}, setup {setup}, posture {posture}, {platform}, zcode {payload['zcode_app_version']})",
    )


def build_stage(
    source: Path,
    stage: Path,
    env_values: dict[str, str],
    platform: str,
    setup: str,
    posture: str,
) -> None:
    section("Build isolated staging tree")
    ensure_dir(stage)
    ensure_dir(stage / "cli")
    ensure_dir(stage / "v2")
    create_runtime_dirs(stage)
    section(f"Copy source tree (marketplace: {setup})")
    copy_source_tree(source, stage)
    section("Render config templates")
    render_configs(source, stage, env_values)
    apply_posture(stage, setup, posture)
    write_env_snapshot(stage, env_values)
    write_stamp(stage, platform, setup, posture)
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
    candidates = sorted(backups.iterdir(), key=lambda item: item.name)
    if len(candidates) > MAX_NAMESPACE_ENTRIES:
        fail("backup root exceeds bounded entry count", 2)
    for entry in candidates:
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


def backup_inventory_entries(backups: Path) -> list[tuple[str, Path | None, str | None]]:
    if not path_exists(backups):
        return []
    require_private_directory(backups, "backup root")
    candidates = sorted(backups.iterdir(), key=lambda item: item.name)
    if len(candidates) > MAX_NAMESPACE_ENTRIES:
        fail("backup inventory exceeds bounded entry count", 2)
    result: list[tuple[str, Path | None, str | None]] = []
    seen: set[str] = set()
    for entry in candidates:
        match = BACKUP_RE.fullmatch(entry.name)
        if match is None:
            if re.fullmatch(r"[0-9]-.*-old\.zcode", entry.name, flags=re.DOTALL):
                result.append(("[redacted-invalid-name]", None, "invalid-backup-name"))
            elif entry.name.startswith(".slot-") and ".hold." in entry.name:
                result.append(("[redacted-recovery-hold]", None, "stale-recovery-hold"))
            continue
        slot = match.group(1)
        if slot in seen:
            result.append((entry.name, None, "duplicate-backup-slot"))
            continue
        seen.add(slot)
        if entry.is_symlink() or not entry.is_dir():
            result.append((entry.name, None, "unsafe-backup-slot"))
            continue
        result.append((entry.name, entry, None))
    return result


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


def validate_resource_disjoint(target: Path, backups: Path) -> None:
    if backups == target or path_contains(backups, target) or path_contains(target, backups):
        fail("backup root must be disjoint from the target", 2)


def validate_backup_root(backups: Path, target: Path, *, create: bool) -> None:
    validate_resource_disjoint(target, backups)
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
    source_parent = open_directory_authority(source.parent, "rename source parent", private=False)
    destination_parent: DirectoryAuthority | None = None
    try:
        destination_parent = open_directory_authority(
            destination.parent,
            "rename destination parent",
            private=False,
        )
        source_name = child_name(source, source_parent.path, "rename source")
        destination_name = child_name(
            destination,
            destination_parent.path,
            "rename destination",
        )
        source_identity = stat_child(source_parent, source_name, "rename source")
        if expected is not None and source_identity != expected:
            fail(f"source identity changed before rename: {source}", 2)
        expected_identity = expected or source_identity
        native_rename_noreplace(
            source_parent.fd,
            source_name,
            destination_parent.fd,
            destination_name,
            "exclusive rename",
        )
        current = stat_child(destination_parent, destination_name, "rename destination")
        if current != expected_identity:
            fail(f"exclusive rename postcondition failed: {destination}", 2)
        fsync_authority(source_parent)
        if identity_tuple(destination_parent.identity) != identity_tuple(source_parent.identity):
            fsync_authority(destination_parent)
    finally:
        if destination_parent is not None:
            destination_parent.close()
        source_parent.close()


def native_rename_noreplace(
    source_parent_fd: int,
    source: str,
    destination_parent_fd: int,
    destination: str,
    label: str,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_b = os.fsencode(source)
    destination_b = os.fsencode(destination)
    if sys.platform.startswith("linux"):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(
            source_parent_fd,
            source_b,
            destination_parent_fd,
            destination_b,
            1,
        )
    elif sys.platform == "darwin":
        rename = libc.renameatx_np
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(
            source_parent_fd,
            source_b,
            destination_parent_fd,
            destination_b,
            0x00000004,
        )
    else:
        fail(f"{label} requires a native no-replace rename primitive", 2)
    if result != 0:
        err = ctypes.get_errno()
        fail(f"{label} no-replace rename failed: {os.strerror(err)}", 2)


def native_rename_child_noreplace(parent_fd: int, source: str, destination: str, label: str) -> None:
    native_rename_noreplace(parent_fd, source, parent_fd, destination, label)


def stat_child(authority: DirectoryAuthority, name: str, label: str) -> FileIdentity:
    if "/" in name or name in {"", ".", ".."}:
        fail(f"{label} child name is invalid", 2)
    authority.current()
    try:
        return identity_from_stat(os.stat(name, dir_fd=authority.fd, follow_symlinks=False))
    except OSError as exc:
        fail(f"cannot inspect {label}: {authority.path / name}: {exc}", 2)


def open_child_file(authority: DirectoryAuthority, name: str, label: str) -> tuple[int, FileIdentity]:
    if "/" in name or name in {"", ".", ".."}:
        fail(f"{label} child name is invalid", 2)
    authority.current()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=authority.fd)
    except OSError as exc:
        fail(f"cannot open {label} safely: {authority.path / name}: {exc}", 2)
    try:
        opened = identity_from_stat(os.fstat(fd))
        current = stat_child(authority, name, label)
        if identity_tuple(opened) != identity_tuple(current):
            fail(f"{label} changed while opening: {authority.path / name}", 2)
        if opened.kind != "file":
            fail(f"{label} must be a regular file: {authority.path / name}", 2)
        if opened.uid != current_uid() or opened.mode & 0o077:
            fail(f"{label} must be a private current-user file: {authority.path / name}", 2)
        return fd, opened
    except BaseException:
        os.close(fd)
        raise


def read_child_file(authority: DirectoryAuthority, name: str, limit: int, label: str) -> bytes:
    fd, _ = open_child_file(authority, name, label)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                fail(f"{label} exceeds the {limit} byte safety limit: {authority.path / name}", 2)
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def atomic_write_child(authority: DirectoryAuthority, name: str, data: bytes, mode: int) -> None:
    if "/" in name or name in {"", ".", ".."}:
        fail("atomic child write name is invalid", 2)
    parent_before = authority.current()
    temp_name = f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode, dir_fd=authority.fd)
    replaced = False
    try:
        os.fchmod(fd, mode)
        write_all(fd, data)
        os.fsync(fd)
        os.replace(temp_name, name, src_dir_fd=authority.fd, dst_dir_fd=authority.fd)
        replaced = True
        fsync_authority(authority)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=authority.fd)
            fsync_authority(authority)
        if not replaced:
            restore_authority_metadata(authority, parent_before)
        raise
    else:
        os.close(fd)


def delete_directory_contents_fd(fd: int, display: Path) -> None:
    try:
        names = sorted(os.listdir(fd))
    except OSError as exc:
        fail(f"cannot list cleanup quarantine: {display}: {exc}", 2)
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail(f"cleanup quarantine exceeds bounded entry count: {display}", 2)
    for name in names:
        if "/" in name or name in {"", ".", ".."}:
            fail(f"cleanup quarantine contains invalid child name: {display}", 2)
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except OSError as exc:
            fail(f"cannot inspect cleanup quarantine child: {display / name}: {exc}", 2)
        identity = identity_from_stat(info)
        if identity.kind == "directory":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            child_fd = os.open(name, flags, dir_fd=fd)
            try:
                opened = identity_from_stat(os.fstat(child_fd))
                if identity_tuple(opened) != identity_tuple(identity):
                    fail(f"cleanup quarantine child changed while opening: {display / name}", 2)
                delete_directory_contents_fd(child_fd, display / name)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=fd)
            os.fsync(fd)
        elif identity.kind == "file":
            child_fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
            try:
                opened = identity_from_stat(os.fstat(child_fd))
                if identity_tuple(opened) != identity_tuple(identity):
                    fail(f"cleanup quarantine file changed while opening: {display / name}", 2)
            finally:
                os.close(child_fd)
            os.unlink(name, dir_fd=fd)
            os.fsync(fd)
        else:
            fail(f"cleanup quarantine contains unsafe object: {display / name}", 2)


def remove_tree_identity(
    path: Path,
    expected: FileIdentity | None = None,
    expected_graph: list[dict[str, Any]] | None = None,
) -> None:
    parent = open_directory_authority(path.parent, "cleanup parent", private=False)
    try:
        name = child_name(path, parent.path, "cleanup object")
        current = stat_child(parent, name, "cleanup object")
        if expected is not None and current != expected:
            fail(f"cleanup object identity changed: {path}", 2)
        expected_identity = expected or current
        quarantine_name = ""
        for _ in range(64):
            candidate = f".nddev-delete.{os.getpid()}.{secrets.token_hex(8)}"
            try:
                os.stat(candidate, dir_fd=parent.fd, follow_symlinks=False)
            except FileNotFoundError:
                quarantine_name = candidate
                break
            except OSError as exc:
                fail(f"cannot probe cleanup quarantine name: {exc}", 2)
        if not quarantine_name:
            fail("cannot allocate bounded cleanup quarantine", 2)
        native_rename_child_noreplace(parent.fd, name, quarantine_name, "cleanup quarantine")
        fsync_authority(parent)
        quarantined = stat_child(parent, quarantine_name, "cleanup quarantine")
        if quarantined != expected_identity:
            fail(f"cleanup quarantine identity mismatch: {parent.path / quarantine_name}", 2)
        quarantine_path = parent.path / quarantine_name
        if expected_graph is not None:
            require_tree_graph(quarantine_path, expected_graph, "cleanup quarantine graph")
        if quarantined.kind == "directory":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            dir_fd = os.open(quarantine_name, flags, dir_fd=parent.fd)
            try:
                opened = identity_from_stat(os.fstat(dir_fd))
                if identity_tuple(opened) != identity_tuple(quarantined):
                    fail(f"cleanup quarantine changed while opening: {quarantine_path}", 2)
                delete_directory_contents_fd(dir_fd, quarantine_path)
            finally:
                os.close(dir_fd)
            os.rmdir(quarantine_name, dir_fd=parent.fd)
            fsync_authority(parent)
        elif quarantined.kind == "file":
            fd = os.open(quarantine_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent.fd)
            try:
                opened = identity_from_stat(os.fstat(fd))
                if identity_tuple(opened) != identity_tuple(quarantined):
                    fail(f"cleanup quarantine changed while opening: {quarantine_path}", 2)
            finally:
                os.close(fd)
            os.unlink(quarantine_name, dir_fd=parent.fd)
            fsync_authority(parent)
        else:
            fail(f"cleanup object is unsafe: {path}", 2)
    finally:
        parent.close()


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
                "gid": identity.gid,
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
                    "gid": item.gid,
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


def cleanup_journal_bytes(payload: dict[str, Any]) -> bytes:
    return json_compact_bytes(payload)


def validate_cleanup_tombstone_namespace_entry(path: Path) -> None:
    item = lstat_identity(path)
    if item.kind != "directory" or item.uid != current_uid() or item.mode & 0o077:
        fail("cleanup tombstone namespace entry is unsafe", 2)


def validate_cleanup_tombstone_child(authority: DirectoryAuthority, name: str) -> None:
    item = stat_child(authority, name, "cleanup tombstone namespace entry")
    if item.kind != "directory" or item.uid != current_uid() or item.mode & 0o077:
        fail("cleanup tombstone namespace entry is unsafe", 2)


def validate_cleanup_journal_temp(path: Path, data: bytes) -> FileIdentity:
    if not JOURNAL_TEMP_RE.fullmatch(path.name):
        fail("cleanup journal temporary file has an invalid name", 2)
    identity = require_private_file_identity(path, "cleanup journal temporary file")
    if identity.nlink != 1 or identity.mode != 0o600:
        fail("cleanup journal temporary file is unsafe", 2)
    if read_file_no_follow(path, MAX_CLEANUP_BYTES, "cleanup journal temporary file") != data:
        fail("cleanup journal temporary file changed before publication", 2)
    return identity


def validate_cleanup_journal_temp_child(authority: DirectoryAuthority, name: str, data: bytes) -> FileIdentity:
    if JOURNAL_TEMP_RE.fullmatch(name) is None:
        fail("cleanup journal temporary file has an invalid name", 2)
    fd, identity = open_child_file(authority, name, "cleanup journal temporary file")
    try:
        if identity.nlink != 1 or identity.mode != 0o600:
            fail("cleanup journal temporary file is unsafe", 2)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CLEANUP_BYTES:
                fail("cleanup journal temporary file exceeds serialized byte bound", 2)
            chunks.append(chunk)
        if b"".join(chunks) != data:
            fail("cleanup journal temporary file changed before publication", 2)
        return identity
    finally:
        os.close(fd)


def open_private_temp_file_child(authority: DirectoryAuthority, *, prefix: str, mode: int) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(64):
        name = f"{prefix}{os.getpid()}.{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(name, flags, mode, dir_fd=authority.fd)
        except FileExistsError:
            continue
        os.fchmod(fd, mode)
        return fd, name
    fail(f"cannot allocate bounded temporary file in {authority.path}", 2)


def recover_staged_cleanup_journal_before_publish(
    target: Path,
    payload: dict[str, Any],
    data: bytes,
    *,
    authority: CleanupAuthority,
) -> bool:
    final = cleanup_journal_path(target)
    if path_exists(final):
        read_cleanup_journal(target, recover_aliases=True)
        return True
    declared = {entry["relative"] for entry in payload["entries"]}
    matches: list[str] = []
    try:
        names = sorted(os.listdir(authority.root.fd))
    except OSError as exc:
        fail(f"cannot scan cleanup journal namespace before publication: {exc}", 2)
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("cleanup journal namespace exceeds bounded entry count", 2)
    for name in names:
        if name == cleanup_prepare_path(target).name:
            fd, _ = open_child_file(authority.root, name, "cleanup prepare intent")
            os.close(fd)
        elif name == live_prepare_path(target).name:
            read_live_prepare(target)
        elif name in declared:
            validate_cleanup_tombstone_child(authority.root, name)
        elif JOURNAL_TEMP_RE.fullmatch(name):
            validate_cleanup_journal_temp_child(authority.root, name, data)
            matches.append(name)
        else:
            fail("cleanup journal namespace contains unknown publication state", 2)
    if not matches:
        return False
    temp = matches[0]
    validate_cleanup_journal_temp_child(authority.root, temp, data)
    try:
        os.link(temp, final.name, src_dir_fd=authority.root.fd, dst_dir_fd=authority.root.fd)
    except FileExistsError:
        read_cleanup_journal(target, recover_aliases=True)
        validate_cleanup_journal_temp_child(authority.root, temp, data)
        os.unlink(temp, dir_fd=authority.root.fd)
        fsync_authority(authority.root)
        return True
    fsync_authority(authority.root)
    read_cleanup_journal(target, recover_aliases=True)
    return True


def cleanup_prepare_payload(
    target: Path,
    source: Path,
    tombstone: Path,
    *,
    authority: CleanupAuthority,
) -> dict[str, Any]:
    return {
        "schema": CLEANUP_SCHEMA,
        "product": PRODUCT,
        "target": str(target),
        "target_digest": target_digest_for(target),
        "operation": "retire-backup-slot",
        "backup_root": {
            "anchor": "backup-root",
            "path": str(source.parent),
            "identity": identity_payload(lstat_identity(source.parent)),
        },
        "cleanup_root": {
            "anchor": "cleanup-root",
            "relative": ".",
            "identity": identity_payload(authority.root.current()),
        },
        "source": {"anchor": "backup-root", "relative": source.name, "kind": "directory"},
        "tombstone": {"anchor": "cleanup-root", "relative": tombstone.name, "kind": "directory"},
        "source_graph": snapshot_tree(source),
    }


def write_cleanup_prepare_with_authority(
    target: Path,
    source: Path,
    tombstone: Path,
    *,
    authority: CleanupAuthority,
) -> dict[str, Any]:
    payload = cleanup_prepare_payload(target, source, tombstone, authority=authority)
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(data) > MAX_CLEANUP_BYTES:
        fail("cleanup prepare intent exceeds serialized byte bound", 2)
    atomic_write_child(authority.root, cleanup_prepare_path(target).name, data, 0o600)
    return payload


def write_cleanup_prepare(target: Path, source: Path, tombstone: Path) -> None:
    with cleanup_authority(target, create=True) as authority:
        write_cleanup_prepare_with_authority(target, source, tombstone, authority=authority)


def read_cleanup_prepare(target: Path) -> dict[str, Any]:
    with cleanup_authority(target, create=False) as authority:
        raw = read_child_file(authority.root, cleanup_prepare_path(target).name, MAX_CLEANUP_BYTES, "cleanup prepare intent")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(f"cleanup prepare intent is malformed: {exc}", 2)
        validate_cleanup_prepare_payload(target, payload, authority=authority)
        return payload


def validate_direct_relative_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or "/" in value or value in {"", ".", ".."}:
        fail(f"{label} relative name is invalid", 2)
    return value


def validate_cleanup_prepare_payload(
    target: Path,
    payload: Any,
    *,
    authority: CleanupAuthority,
) -> None:
    required = {
        "schema",
        "product",
        "target",
        "target_digest",
        "operation",
        "backup_root",
        "cleanup_root",
        "source",
        "tombstone",
        "source_graph",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        fail("cleanup prepare intent keys are invalid", 2)
    if payload["schema"] != CLEANUP_SCHEMA or payload["product"] != PRODUCT:
        fail("cleanup prepare intent schema/product mismatch", 2)
    if payload["target"] != str(target) or payload["target_digest"] != target_digest_for(target):
        fail("cleanup prepare intent target binding mismatch", 2)
    if payload["operation"] != "retire-backup-slot":
        fail("cleanup prepare operation is invalid", 2)
    backup_root = payload["backup_root"]
    cleanup_root = payload["cleanup_root"]
    if not isinstance(backup_root, dict) or set(backup_root) != {"anchor", "path", "identity"}:
        fail("cleanup prepare backup root binding is invalid", 2)
    backup_path_value = backup_root.get("path")
    if (
        backup_root["anchor"] != "backup-root"
        or not isinstance(backup_path_value, str)
        or any(ord(character) < 32 or ord(character) == 127 for character in backup_path_value)
        or not os.path.isabs(backup_path_value)
        or Path(backup_path_value) == Path("/")
        or str(Path(backup_path_value)) != backup_path_value
    ):
        fail("cleanup prepare backup root binding mismatch", 2)
    identity_from_payload(backup_root["identity"], "cleanup prepare backup root")
    if not isinstance(cleanup_root, dict) or set(cleanup_root) != {"anchor", "relative", "identity"}:
        fail("cleanup prepare cleanup root binding is invalid", 2)
    if cleanup_root["anchor"] != "cleanup-root" or cleanup_root["relative"] != ".":
        fail("cleanup prepare cleanup root binding mismatch", 2)
    cleanup_identity = identity_from_payload(cleanup_root["identity"], "cleanup prepare cleanup root")
    current_root = authority.root.current()
    if (
        identity_tuple(cleanup_identity) != identity_tuple(current_root)
        or cleanup_identity.kind != current_root.kind
        or cleanup_identity.uid != current_root.uid
        or cleanup_identity.gid != current_root.gid
        or cleanup_identity.mode != current_root.mode
    ):
        fail("cleanup prepare cleanup root identity mismatch", 2)
    source = payload["source"]
    tombstone = payload["tombstone"]
    if not isinstance(source, dict) or set(source) != {"anchor", "relative", "kind"}:
        fail("cleanup prepare source binding is invalid", 2)
    if source["anchor"] != "backup-root" or source["kind"] != "directory":
        fail("cleanup prepare source binding mismatch", 2)
    validate_direct_relative_name(source["relative"], "cleanup prepare source")
    if not isinstance(tombstone, dict) or set(tombstone) != {"anchor", "relative", "kind"}:
        fail("cleanup prepare tombstone binding is invalid", 2)
    if tombstone["anchor"] != "cleanup-root" or tombstone["kind"] != "directory":
        fail("cleanup prepare tombstone binding mismatch", 2)
    validate_direct_relative_name(tombstone["relative"], "cleanup prepare tombstone")
    validate_tree_graph_payload(payload["source_graph"], "cleanup prepare source graph")


def validate_prepare_backup_binding(payload: dict[str, Any], backups: Path) -> None:
    backup_root = payload["backup_root"]
    if backup_root["path"] != str(backups):
        fail("cleanup prepare backup root path mismatch", 2)
    validate_locked_resource_path(backups, "cleanup prepare backup root")
    expected = identity_from_payload(backup_root["identity"], "cleanup prepare backup root")
    current = lstat_identity(backups)
    if (
        identity_tuple(expected) != identity_tuple(current)
        or expected.kind != current.kind
        or expected.uid != current.uid
        or expected.gid != current.gid
        or expected.mode != current.mode
    ):
        fail("cleanup prepare backup root identity mismatch", 2)


def read_cleanup_journal(target: Path, *, recover_aliases: bool) -> dict[str, Any]:
    with cleanup_authority(target, create=False) as authority:
        path = cleanup_journal_path(target)
        fd, identity = open_child_file(authority.root, path.name, "cleanup journal")
        try:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_CLEANUP_BYTES:
                    fail("cleanup journal exceeds serialized byte bound", 2)
                chunks.append(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(fd)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(f"cleanup journal is malformed: {exc}", 2)
        validate_cleanup_journal_payload(target, payload)
        validate_cleanup_journal_namespace(
            target,
            payload,
            identity=identity,
            recover_aliases=recover_aliases,
            authority=authority,
        )
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
        validate_tree_graph_payload(entry["graph"], "cleanup journal graph")


def validate_cleanup_journal_namespace(
    target: Path,
    payload: dict[str, Any],
    *,
    identity: FileIdentity,
    recover_aliases: bool,
    authority: CleanupAuthority,
) -> None:
    path = cleanup_journal_path(target)
    declared = {entry["relative"] for entry in payload["entries"]}
    matches: list[str] = []
    names = sorted(os.listdir(authority.root.fd))
    if len(names) > MAX_NAMESPACE_ENTRIES:
        fail("cleanup journal namespace exceeds bounded entry count", 2)
    for name in names:
        if name == path.name:
            continue
        if name == cleanup_prepare_path(target).name:
            open_fd, _ = open_child_file(authority.root, name, "cleanup prepare intent")
            os.close(open_fd)
            continue
        if name == live_prepare_path(target).name:
            read_live_prepare(target)
            continue
        if name in declared:
            validate_cleanup_tombstone_child(authority.root, name)
            continue
        if JOURNAL_TEMP_RE.fullmatch(name):
            open_fd, item = open_child_file(authority.root, name, "cleanup journal alias")
            os.close(open_fd)
            if identity_tuple(item) == identity_tuple(identity):
                matches.append(name)
                continue
            fail("cleanup journal parent contains mismatched publication alias", 2)
        fail("cleanup journal parent contains unknown publication state", 2)
    if identity.nlink != 1:
        if not recover_aliases:
            fail("cleanup journal must not have hard-link aliases", 2)
        if len(matches) != 1:
            fail("cleanup journal has unexpected hard-link aliases", 2)
        os.unlink(matches[0], dir_fd=authority.root.fd)
        fsync_authority(authority.root)
        recovered_fd, recovered = open_child_file(authority.root, path.name, "cleanup journal")
        os.close(recovered_fd)
        if identity_tuple(recovered) != identity_tuple(identity) or recovered.nlink != 1:
            fail("cleanup journal alias recovery failed", 2)
    elif matches:
        fail("cleanup journal parent contains incomplete publication alias", 2)


def publish_cleanup_journal(target: Path, payload: dict[str, Any]) -> None:
    with cleanup_authority(target, create=True) as authority:
        final = cleanup_journal_path(target)
        data = cleanup_journal_bytes(payload)
        if len(data) > MAX_CLEANUP_BYTES:
            fail("cleanup journal exceeds serialized byte bound", 2)
        if recover_staged_cleanup_journal_before_publish(target, payload, data, authority=authority):
            return
        parent_before = authority.root.current()
        fd, temp = open_private_temp_file_child(authority.root, prefix=".journal.", mode=0o600)
        final_visible = False
        try:
            write_all(fd, data)
            os.fsync(fd)
            validate_cleanup_journal_temp_child(authority.root, temp, data)
            try:
                os.link(temp, final.name, src_dir_fd=authority.root.fd, dst_dir_fd=authority.root.fd)
                final_visible = True
            except FileExistsError:
                read_cleanup_journal(target, recover_aliases=True)
                post_publish_issue: BaseException | None = None
                try:
                    validate_cleanup_journal_temp_child(authority.root, temp, data)
                    os.unlink(temp, dir_fd=authority.root.fd)
                    fsync_authority(authority.root)
                except BaseException as exc:
                    post_publish_issue = exc
                if post_publish_issue is not None:
                    log("warn", "cleanup_pending=true")
                return
            post_publish_issue = None
            try:
                read_cleanup_journal(target, recover_aliases=True)
            except BaseException:
                # The final path is visible; leave the same-inode alias for the
                # next exclusive mutator rather than creating a split recovery.
                raise
            try:
                os.stat(temp, dir_fd=authority.root.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                try:
                    validate_cleanup_journal_temp_child(authority.root, temp, data)
                    os.unlink(temp, dir_fd=authority.root.fd)
                    fsync_authority(authority.root)
                except BaseException as exc:
                    post_publish_issue = exc
            read_cleanup_journal(target, recover_aliases=True)
            if post_publish_issue is not None:
                log("warn", "cleanup_pending=true")
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)
            if not final_visible:
                try:
                    os.unlink(temp, dir_fd=authority.root.fd)
                    fsync_authority(authority.root)
                    restore_authority_metadata(authority.root, parent_before)
                except FileNotFoundError:
                    pass


def recover_prepare_if_needed(target: Path, backups: Path) -> None:
    prepare = cleanup_prepare_path(target)
    journal = cleanup_journal_path(target)
    if not path_exists(prepare):
        return
    with cleanup_authority(target, create=False) as authority:
        payload = read_cleanup_prepare(target)
        prepare_binding = durable_file_binding(
            prepare,
            json_compact_bytes(payload),
            "cleanup prepare intent",
        )
        validate_prepare_backup_binding(payload, backups)
        if path_exists(journal):
            # Valid pending cleanup owns the tombstone now.
            return
        source_name = payload["source"]["relative"]
        tombstone_name = payload["tombstone"]["relative"]
        source = backups / source_name
        tombstone = cleanup_root_for(target) / tombstone_name
        source_exists = path_exists(source)
        tombstone_exists = path_exists(tombstone)
        if tombstone_exists and not source_exists:
            journal_payload = cleanup_payload(target, tombstone)
            journal_data = cleanup_journal_bytes(journal_payload)
            if recover_staged_cleanup_journal_before_publish(
                target,
                journal_payload,
                journal_data,
                authority=authority,
            ):
                return
            root_entries = [item for item in payload["source_graph"] if item["relative"] == "."]
            if len(root_entries) != 1:
                fail("cleanup prepare source graph root is invalid", 2)
            source_identity = identity_from_tree_entry(
                root_entries[0],
                "cleanup prepare source graph root",
            )
            rename_noreplace(tombstone, source, source_identity)
            require_object_binding(
                source,
                source_identity,
                payload["source_graph"],
                "recovered retired backup slot",
            )
        elif source_exists and not tombstone_exists:
            root_entries = [item for item in payload["source_graph"] if item["relative"] == "."]
            if len(root_entries) != 1:
                fail("cleanup prepare source graph root is invalid", 2)
            require_object_binding(
                source,
                identity_from_tree_entry(root_entries[0], "cleanup prepare source graph root"),
                payload["source_graph"],
                "recovered retired backup slot",
            )
        else:
            fail("cleanup preparation state is incoherent", 2)
        validate_prepare_backup_binding(payload, backups)
        require_durable_file_binding(prepare, prepare_binding, "cleanup prepare intent")
        os.unlink(prepare.name, dir_fd=authority.root.fd)
        fsync_authority(authority.root)


def drain_cleanup_pending(target: Path) -> bool:
    journal = cleanup_journal_path(target)
    if not path_exists(journal):
        return False
    cleanup_root_authority(target, create=False)
    payload = read_cleanup_journal(target, recover_aliases=True)
    journal_binding = durable_file_binding(
        journal,
        cleanup_journal_bytes(payload),
        "cleanup journal",
    )
    prepare = cleanup_prepare_path(target)
    prepare_binding: DurableFileBinding | None = None
    if path_exists(prepare):
        prepare_payload = read_cleanup_prepare(target)
        prepare_binding = durable_file_binding(
            prepare,
            json_compact_bytes(prepare_payload),
            "cleanup prepare intent",
        )
        backups = Path(prepare_payload["backup_root"]["path"])
        validate_prepare_backup_binding(prepare_payload, backups)
        tombstone_name = prepare_payload["tombstone"]["relative"]
        matches = [
            entry
            for entry in payload["entries"]
            if entry["relative"] == tombstone_name
            and entry["graph"] == prepare_payload["source_graph"]
        ]
        if len(matches) != 1:
            fail("cleanup prepare and journal bindings disagree", 2)
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
        root_entries = [item for item in entry["graph"] if item["relative"] == "."]
        if len(root_entries) != 1:
            fail("cleanup tombstone graph root is invalid", 2)
        remove_tree_identity(
            tombstone,
            identity_from_tree_entry(root_entries[0], "cleanup tombstone graph root"),
            expected_graph=entry["graph"],
        )
    with cleanup_authority(target, create=False) as authority:
        require_durable_file_binding(journal, journal_binding, "cleanup journal")
        try:
            stat_child(authority.root, journal.name, "cleanup journal")
        except ManagerError:
            pass
        else:
            os.unlink(journal.name, dir_fd=authority.root.fd)
            fsync_authority(authority.root)
        prepare = cleanup_prepare_path(target)
        try:
            stat_child(authority.root, prepare.name, "cleanup prepare intent")
        except ManagerError:
            pass
        else:
            if prepare_binding is None:
                fail("cleanup prepare appeared during journal drain", 2)
            require_durable_file_binding(prepare, prepare_binding, "cleanup prepare intent")
            os.unlink(prepare.name, dir_fd=authority.root.fd)
            fsync_authority(authority.root)
            try:
                names = sorted(os.listdir(authority.root.fd))
            except OSError as exc:
                fail(f"cannot inspect cleanup state root after prepare removal: {exc}", 2)
            if not names:
                root = cleanup_root_for(target)
                os.rmdir(root.name, dir_fd=authority.parent.fd)
                fsync_authority(authority.parent)
                try:
                    parent_names = sorted(os.listdir(authority.parent.fd))
                except OSError as exc:
                    fail(f"cannot inspect cleanup namespace parent after prepare removal: {exc}", 2)
                if not parent_names:
                    parent_identity = authority.parent.current()
                    target_parent = open_directory_authority(target.parent, "target parent", private=False)
                    try:
                        current = stat_child(target_parent, CLEANUP_PARENT_NAME, "cleanup namespace parent")
                        if identity_tuple(current) == identity_tuple(parent_identity):
                            os.rmdir(CLEANUP_PARENT_NAME, dir_fd=target_parent.fd)
                            fsync_authority(target_parent)
                    finally:
                        target_parent.close()
                return True
        try:
            names = sorted(os.listdir(authority.root.fd))
        except OSError as exc:
            fail(f"cannot inspect cleanup state root before retirement: {exc}", 2)
        if not names:
            os.rmdir(root.name, dir_fd=authority.parent.fd)
            fsync_authority(authority.parent)
            try:
                parent_names = sorted(os.listdir(authority.parent.fd))
            except OSError as exc:
                fail(f"cannot inspect cleanup namespace parent before retirement: {exc}", 2)
            if not parent_names:
                parent_identity = authority.parent.current()
                target_parent = open_directory_authority(target.parent, "target parent", private=False)
                try:
                    current = stat_child(target_parent, CLEANUP_PARENT_NAME, "cleanup namespace parent")
                    if identity_tuple(current) == identity_tuple(parent_identity):
                        os.rmdir(CLEANUP_PARENT_NAME, dir_fd=target_parent.fd)
                        fsync_authority(target_parent)
                finally:
                    target_parent.close()
    return True


def create_cleanup_for_retired_backup(target: Path, backups: Path, retired: Path) -> tuple[Path, Path] | None:
    if retired is None:
        return None
    with cleanup_authority(target, create=True) as authority:
        root = authority.root.path
        tombstone = root / f"retired-{int(time.time() * 1000000)}-{retired.name}"
        prepare_payload = write_cleanup_prepare_with_authority(target, retired, tombstone, authority=authority)
        root_entries = [item for item in prepare_payload["source_graph"] if item["relative"] == "."]
        if len(root_entries) != 1:
            fail("cleanup prepare source graph root is invalid", 2)
        retired_identity = identity_from_tree_entry(
            root_entries[0],
            "cleanup prepare source graph root",
        )
        rename_noreplace(retired, tombstone, retired_identity)
        require_object_binding(
            tombstone,
            retired_identity,
            prepare_payload["source_graph"],
            "retired cleanup tombstone",
        )
        payload = cleanup_payload(target, tombstone)
        publish_cleanup_journal(target, payload)
        validate_retired_cleanup_authority(target, backups)
        return tombstone, payload


def finish_cleanup(target: Path, payload: dict[str, Any] | None) -> bool:
    if payload is not None and not path_exists(cleanup_journal_path(target)):
        publish_cleanup_journal(target, payload)
    elif payload is None and not path_exists(cleanup_journal_path(target)):
        return False
    try:
        drain_cleanup_pending(target)
        return False
    except OSError:
        log("warn", "cleanup_pending=true")
        return True
    except ManagerError as exc:
        if exc.code == 2:
            raise
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


def same_setup_noop(target: Path, setup: str, posture: str, platform: str) -> bool:
    if not path_exists(target / "BUILD-VERSION"):
        return False
    try:
        stamp = stamp_metadata(target)
    except ManagerError:
        return False
    return (
        stamp.get("stamp_schema") == 2
        and stamp.get("setup_id") == setup
        and stamp.get("posture") == posture
        and stamp.get("build_version") == build_version()
        and stamp.get("zcode_app_version") == pinned_app_version()
        and stamp.get("zcode_cli_version") == pinned_cli_version()
        and stamp.get("zcode_runtime") == zcode_runtime()
        and stamp.get("platform") == platform
        and not cleanup_pending_state(target, recover_aliases=False)["cleanup_pending"]
    )


def plan_install(options: Options, target: Path, backups: Path, platform: str, source: Path) -> None:
    assert_component_graph(source)
    log("info", f"profile: desktop ({'macOS' if platform == 'macos' else 'Ubuntu'})")
    log("info", f"posture: {options.posture}")
    log("info", f"target: {target}")
    cleanup = cleanup_pending_state(target, recover_aliases=False)
    if cleanup["cleanup_pending"]:
        log("warn", "cleanup_pending=true")
    parent = target.parent
    print_plan_coordination(target, cleanup)
    print(f"[DRY-RUN] validate backup root {backups}")
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
    print("[DRY-RUN] release canonical target coordination anchor")


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


def recover_transaction_state(resources: TransactionResources) -> bool:
    target = resources.target
    recover_live_prepare_if_needed(target)
    cleanup_drained = drain_cleanup_pending(target)
    if path_exists(cleanup_prepare_path(target)):
        payload = read_cleanup_prepare(target)
        bound = Path(payload["backup_root"]["path"])
        if bound not in resources.pending_backups:
            fail("cleanup prepare backup root was not acquired", 2)
        recover_prepare_if_needed(target, bound)
    recover_empty_cleanup_root_before_mutation(target)
    return cleanup_drained


def apply_install(
    options: Options,
    resources: TransactionResources,
    platform: str,
    source: Path,
) -> bool:
    target = resources.target
    backups = resources.backups
    cleanup_drained = recover_transaction_state(resources)
    log("info", f"profile: desktop ({'macOS' if platform == 'macos' else 'Ubuntu'})")
    log("info", f"target: {target}")
    had_target = path_exists(target)
    adoption_mode = False
    old_version = "unmanaged"
    original_identity: FileIdentity | None = None
    original_graph: list[dict[str, Any]] | None = None
    stage_graph: list[dict[str, Any]] | None = None
    if had_target:
        identity = lstat_identity(target)
        if identity.kind != "directory":
            fail("install target must be a directory")
        original_identity = identity
        original_graph = snapshot_tree(target)
        old_version = current_version(target)
        if old_version == "unmanaged":
            if not options.adopt_unmanaged:
                fail("refusing to replace an unstamped target; use --adopt-unmanaged with an explicit --target")
            adoption_mode = True
        elif options.adopt_unmanaged:
            fail("--adopt-unmanaged is only valid for an existing unstamped target", 2)
        if not adoption_mode and same_setup_noop(target, source.name, options.posture, platform):
            log("ok", "managed setup already matches requested build, posture, platform, and runtime pins")
            return False
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
    adoption_marker: dict[str, Any] | None = None
    try:
        check_runtime_version(plan=False)
        build_stage(source, stage, parse_env_file(), platform, source.name, options.posture)
        if had_target:
            copy_runtime_state(target, stage, unmanaged=adoption_mode)
            verify_managed_tree(stage, setup=source.name)
            normalize_tree(stage)
            fsync_tree(stage)
        stage_identity = lstat_identity(stage)
        stage_graph = snapshot_tree(stage)
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
                adoption_marker = adoption_envelope_payload(target)
                write_live_prepare(
                    target,
                    backups,
                    operation="install",
                    stage=stage,
                    stage_identity=stage_identity,
                    source_identity=original_identity,
                    destination=rollback_source,
                    adoption_marker=adoption_marker,
                )
                ensure_dir(destination)
                rename_noreplace(target, rollback_source, original_identity)
                write_adoption_envelope(destination, target, adoption_marker)
                rollback_identity = original_identity
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
                    adoption_marker=None,
                )
                rename_noreplace(target, backup_path, original_identity)
                rollback_identity = original_identity
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
                adoption_marker=None,
            )
        rename_noreplace(stage, target, stage_identity)
        stage = Path()
        _, prepare_binding = validate_live_commit_decision(target)
        unlink_live_prepare(target, prepare_binding)
        cleanup_pending = finish_cleanup(target, retired_payload)
        return cleanup_drained or cleanup_pending
    except BaseException:
        if path_exists(target) and path_exists(rollback_source or Path("__missing__")):
            with contextlib.suppress(BaseException):
                failed = Path(tempfile.mkdtemp(prefix=f".{target.name}.failed.", dir=str(parent)))
                failed.rmdir()
                require_tree_graph(target, stage_graph, "failed live target graph")
                require_tree_graph(rollback_source, original_graph, "rollback source graph")
                rename_noreplace(target, failed, stage_identity)
                rename_noreplace(rollback_source, target, rollback_identity)
                remove_tree_identity(failed, stage_identity, expected_graph=stage_graph)
                cleanup_empty_backup_container(rollback_source, backups, adoption_marker if adoption_mode else None)
        elif rollback_source is not None and path_exists(rollback_source) and not path_exists(target):
            with contextlib.suppress(BaseException):
                require_tree_graph(rollback_source, original_graph, "rollback source graph")
                rename_noreplace(rollback_source, target, rollback_identity)
                cleanup_empty_backup_container(rollback_source, backups, adoption_marker if adoption_mode else None)
        if stage and path_exists(stage):
            with contextlib.suppress(BaseException):
                require_tree_graph(stage, stage_graph, "live stage graph")
                remove_tree_identity(stage, stage_identity)
        with contextlib.suppress(BaseException):
            recover_live_prepare_if_needed(target)
        raise


def write_adoption_envelope(
    envelope: Path,
    original_target: Path,
    payload: dict[str, Any] | None = None,
) -> None:
    if payload is None:
        payload = adoption_envelope_payload(original_target)
    validate_adoption_marker_payload(
        payload,
        expected_target=original_target,
        expected_build=build_version(),
    )
    atomic_write(envelope / "NDDEV-BACKUP.json", json_compact_bytes(payload), 0o600)


def install_command(options: Options, target_text: str, backups_text: str) -> int:
    platform = detect_platform() if options.platform == "auto" else options.platform
    if platform not in {"macos", "ubuntu"}:
        fail("unsupported platform (expected macos|ubuntu)", 2)
    if not options.setup:
        options.setup = DEFAULT_SETUP
    source = select_marketplace(options.setup)
    section("nddev-zcode-app installer")
    log("info", f"mode: {'APPLY' if options.apply else 'PLAN (dry-run)'}")
    log("info", f"platform: {platform}")
    log("info", f"repo root: {ROOT}")
    log("info", f"selected marketplace: {source.name} ({source})")
    log("info", f"posture: {options.posture}")
    if not options.apply:
        def body(locked: Path, backups: Path) -> None:
            cleanup = cleanup_pending_state(locked, recover_aliases=False)
            if cleanup["cleanup_pending"]:
                log("warn", "cleanup_pending=true")
            validate_backup_root(backups, locked, create=False)
            plan_install(options, locked, backups, platform, source)
        run_transaction_plan(target_text, backups_text, body)
        install_complete(source.name, platform, backup=None, cleanup_pending=False)
        return 0
    with transaction_coordination(target_text, backups_text) as resources:
        validate_backup_root(resources.backups, resources.target, create=False)
        cleanup_pending = apply_install(options, resources, platform, source)
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


def canonical_backups_from_text(value: str, *, inspect_endpoint: bool = True) -> Path:
    value = reject_transaction_path_controls(value, "backup root")
    if not value:
        fail("backup root path is invalid", 2)
    expanded = Path(value).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    if inspect_endpoint and path_exists(expanded) and lstat_identity(expanded).kind != "directory":
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
    original = validate_adoption_marker_payload(marker)
    if not allow_relocation and original != target:
        fail("adopted backup belongs to a different target; explicit relocation is required")
    payload = envelope / "payload"
    if not payload.is_dir() or payload.is_symlink():
        fail("adopted backup payload escapes its envelope or is unsafe")
    return payload


def restore_command(options: Options, target_text: str, backups_text: str) -> int:
    if not options.apply:
        def body(locked: Path, backups: Path) -> None:
            cleanup = cleanup_pending_state(locked, recover_aliases=False)
            if cleanup["cleanup_pending"]:
                log("warn", "cleanup_pending=true")
            print_plan_coordination(locked, cleanup)
            validate_backup_root(backups, locked, create=False)
            source = find_slot(backups, options.slot)
            section(f"Restore from backup slot {options.slot}")
            if source is None:
                fail(f"no safe backup found in slot {options.slot}")
            log("info", f"backup: {source}")
            log("info", f"target: {locked}")
            log("info", "mode: PLAN (dry-run)")
            print(f"[DRY-RUN] copy managed payload {source} -> {locked.parent / ('.' + locked.name + '.stage.PLAN')}")
        run_transaction_plan(target_text, backups_text, body)
        section("Restore complete")
        return 0
    with transaction_coordination(target_text, backups_text) as resources:
        target = resources.target
        backups = resources.backups
        recover_transaction_state(resources)
        validate_backup_root(backups, target, create=False)
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
        original_graph = snapshot_tree(target) if had_target else None
        if had_target:
            if old_version == "unmanaged":
                fail("refusing to restore over an unstamped target", 2)
            safe_tree(target)
            runtime_quiescent(target, plan=False)
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage.", dir=str(target.parent)))
        stage_identity = lstat_identity(stage)
        rollback_source: Path | None = None
        rollback_identity: FileIdentity | None = None
        stage_graph: list[dict[str, Any]] | None = None
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
            stage_graph = snapshot_tree(stage)
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
            _, prepare_binding = validate_live_commit_decision(target)
            unlink_live_prepare(target, prepare_binding)
            cleanup_pending = finish_cleanup(target, retired_payload)
            section("Restore complete")
            if cleanup_pending:
                log("warn", "cleanup_pending=true")
            return 0
        except BaseException:
            if rollback_source is not None and path_exists(rollback_source) and not path_exists(target):
                with contextlib.suppress(BaseException):
                    require_tree_graph(rollback_source, original_graph, "restore rollback source graph")
                    rename_noreplace(rollback_source, target, rollback_identity)
            if stage and path_exists(stage):
                with contextlib.suppress(BaseException):
                    require_tree_graph(stage, stage_graph, "restore stage graph")
                    remove_tree_identity(stage, stage_identity)
            with contextlib.suppress(BaseException):
                recover_live_prepare_if_needed(target)
            raise


def remove_command(options: Options, target_text: str, backups_text: str) -> int:
    if not options.apply:
        def body(locked: Path, backups: Path) -> None:
            cleanup = cleanup_pending_state(locked, recover_aliases=False)
            if cleanup["cleanup_pending"]:
                log("warn", "cleanup_pending=true")
            print_plan_coordination(locked, cleanup)
            section("nddev-zcode-app - remove")
            log("info", "mode: PLAN (dry-run)")
            log("info", f"target: {locked}")
            if not path_exists(locked):
                log("info", f"nothing to remove: {locked} does not exist")
            else:
                version = current_version(locked)
                destination, _ = choose_backup_destination(backups, version, locked, create=False)
                print(f"[DRY-RUN] atomic move {locked} {destination}")
        run_transaction_plan(target_text, backups_text, body)
        return 0
    with transaction_coordination(target_text, backups_text) as resources:
        target = resources.target
        backups = resources.backups
        recover_transaction_state(resources)
        validate_backup_root(backups, target, create=False)
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
        try:
            rename_noreplace(target, destination, identity)
            fsync_tree(destination)
            _, prepare_binding = validate_live_commit_decision(target)
            unlink_live_prepare(target, prepare_binding)
            cleanup_pending = finish_cleanup(target, retired_payload)
            if cleanup_pending:
                log("warn", "cleanup_pending=true")
            log("ok", f"removed target into backup: {destination}")
            return 0
        except BaseException:
            with contextlib.suppress(BaseException):
                recover_live_prepare_if_needed(target)
            raise


def list_backups(options: Options, backups_text: str) -> int:
    return run_backup_read_only(
        backups_text,
        lambda backups: list_backups_locked(options, backups),
    )


def list_backups_locked(options: Options, backups: Path) -> int:
    section(f"Backups ({backups})")
    if not backups.is_dir():
        log("info", "no backups directory")
        return 0
    found = False
    for display_name, entry, invalid_kind in backup_inventory_entries(backups):
        found = True
        if invalid_kind is not None or entry is None:
            print(f"  {display_name}  type={invalid_kind}")
            continue
        if path_exists(entry / "BUILD-VERSION"):
            try:
                stamp = stamp_metadata(entry)
                print(
                    f"  {display_name}  type=managed  build={stamp['build_version']}  installed={stamp['installed_at']}"
                )
            except ManagerError:
                print(f"  {display_name}  type=invalid-managed-stamp")
        elif path_exists(entry / "NDDEV-BACKUP.json"):
            try:
                marker = load_json_file(entry / "NDDEV-BACKUP.json", "adoption envelope")
                original = validate_adoption_marker_payload(marker)
                print(
                    f"  {display_name}  type=adopted-unmanaged build={marker['installer_build']} "
                    f"created={marker['created_at']} target={original}"
                )
            except ManagerError:
                print(f"  {display_name}  type=invalid-adoption-envelope")
        else:
            print(f"  {display_name}  type=invalid-or-unmanaged")
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
        elif item == "--posture":
            if seen.get("posture"):
                fail("duplicate option is not allowed: --posture", 2)
            options.posture = require_value(argv, index, item)
            seen["posture"] = True
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
            ("posture", "--posture"),
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
            ("posture", "--posture"),
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
            ("posture", "--posture"),
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
            ("posture", "--posture"),
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
            ("posture", "--posture"),
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
            options.setup = DEFAULT_SETUP
        if SETUP_RE.fullmatch(options.setup) is None:
            fail("invalid setup id", 2)
        if options.posture not in POSTURES:
            fail("invalid posture (expected full-auto|safe)", 2)
        if options.platform not in {"auto", "macos", "ubuntu"}:
            fail("unsupported platform (expected macos|ubuntu)", 2)
    if options.command == "restore":
        if not options.slot:
            fail("restore requires --slot <N> (0-9). Use 'list --backups' to see options.", 2)
        if not re.fullmatch(r"[0-9]", options.slot):
            fail("--slot must be a single digit 0-9", 2)
    if options.allow_target_relocation and (options.command != "restore" or not options.target):
        fail("--allow-target-relocation requires restore with an explicit --target", 2)
    if options.allow_target_relocation and not os.path.isabs(options.target):
        fail("--allow-target-relocation requires an absolute --target", 2)
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
        if options.command == "status":
            return show_status(options, resolve_target_option(options, env_values))
        if options.command == "list-backups":
            return list_backups(options, resolve_backups_option(options, env_values))
        target_text = resolve_target_option(options, env_values)
        backups_text = resolve_backups_option(options, env_values)
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
