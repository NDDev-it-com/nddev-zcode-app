#!/usr/bin/env python3
"""Validate the public NDDev ZCode module contracts without private inputs.

This is the repository-owned fast verification entry point declared in
`.gds/repository.yaml`. It checks only tracked public contract files and
never reads private harness material, user state, or the network.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_KEYS = (
    "macos-arm64",
    "macos-x64",
    "linux-x64-appimage",
    "linux-x64-deb",
    "linux-arm64-appimage",
    "linux-arm64-deb",
)
MACOS_GATEKEEPER_SOURCES = {
    "macos-arm64": "Notarized Developer ID",
    "macos-x64": "Notarized Developer ID",
}
DEFAULT_SETUP = "nddev-builder"
_SHA512 = re.compile(r"[0-9a-f]{128}")


def load_json(relative: str, errors: list[str]) -> dict | None:
    path = ROOT / relative
    if not path.is_file():
        errors.append(f"missing required contract file: {relative}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{relative}: unreadable or invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{relative}: top-level value must be an object")
        return None
    return data


def parse_utc(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_readme(version: dict, errors: list[str]) -> None:
    path = ROOT / "README.md"
    if not path.is_file():
        errors.append("missing README.md")
        return
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"README.md: unreadable: {exc}")
        return
    expected_lines = (
        f"- **Build version:** {version.get('build_version')}",
        "- **Verified ZCode runtime:** "
        f"app {version.get('zcode_app_version')}, "
        f"CLI {version.get('zcode_cli_version')}, "
        f"model {version.get('zcode_runtime')}",
    )
    for expected in expected_lines:
        if content.count(expected) != 1:
            errors.append(f"README.md: expected exactly one metadata line: {expected}")


def check_artifacts(version: dict, errors: list[str]) -> None:
    app = str(version.get("zcode_app_version", ""))
    artifacts = version.get("zcode_download_artifacts")
    if not isinstance(artifacts, dict):
        errors.append("build/version.json: zcode_download_artifacts must be an object")
        return
    if sorted(artifacts) != sorted(ARTIFACT_KEYS):
        errors.append(
            "build/version.json: artifact set must be exactly "
            f"{sorted(ARTIFACT_KEYS)}, found {sorted(artifacts)}"
        )
    bundle_versions: set[str] = set()
    package_versions: set[str] = set()
    for key, entry in artifacts.items():
        context = f"build/version.json:zcode_download_artifacts.{key}"
        if not isinstance(entry, dict):
            errors.append(f"{context}: must be an object")
            continue
        filename = str(entry.get("filename", ""))
        if f"-{app}-" not in f"-{filename}-".replace("ZCode-", "-", 1):
            if app not in filename:
                errors.append(f"{context}: filename does not embed app version {app}")
        size = entry.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            errors.append(f"{context}: size_bytes must be a positive integer")
        digest = str(entry.get("sha512", ""))
        if _SHA512.fullmatch(digest) is None:
            errors.append(f"{context}: sha512 must be 128 hex characters")
        # The CDN serves each file under a per-artifact directory segment between
        # the version and the filename. macOS uses the platform-arch key; the two
        # Linux formats share one linux-<arch> directory. Pin the exact expected
        # segment so a wrong path (the 404 this field exists to prevent) fails
        # closed instead of only surfacing at download time.
        expected_subpath = key[: -len("-appimage")] if key.endswith("-appimage") else key
        expected_subpath = (
            expected_subpath[: -len("-deb")]
            if expected_subpath.endswith("-deb")
            else expected_subpath
        )
        if entry.get("cdn_subpath") != expected_subpath:
            errors.append(f"{context}: cdn_subpath must be {expected_subpath!r}")
        if key.startswith("macos"):
            if not filename.endswith(".zip"):
                errors.append(f"{context}: macOS artifact must be the official ZIP update artifact")
            if entry.get("app_version") != app:
                errors.append(f"{context}: app_version must equal zcode_app_version")
            bundle = str(entry.get("bundle_version", ""))
            if not bundle.startswith(f"{app}."):
                errors.append(f"{context}: bundle_version must extend app version {app}")
            bundle_versions.add(bundle)
            for field in ("team_id", "bundle_id"):
                if not str(entry.get(field, "")).strip():
                    errors.append(f"{context}: {field} must be a non-empty string")
            if entry.get("gatekeeper_source") != MACOS_GATEKEEPER_SOURCES.get(key):
                errors.append(
                    f"{context}: gatekeeper_source must be "
                    f"{MACOS_GATEKEEPER_SOURCES.get(key)!r}"
                )
        if key.endswith("deb"):
            package = str(entry.get("package_version", ""))
            if not package.startswith(f"{app}-"):
                errors.append(f"{context}: package_version must extend app version {app}")
            package_versions.add(package)
            if entry.get("package_name") != "zcode":
                errors.append(f"{context}: package_name must be zcode")
    if len(bundle_versions) > 1:
        errors.append("build/version.json: macOS bundle_version values disagree")
    if len(package_versions) > 1:
        errors.append("build/version.json: Debian package_version values disagree")


def check_baseline(version: dict, baseline: dict, errors: list[str]) -> None:
    zcode = baseline.get("zcode")
    if not isinstance(zcode, dict):
        errors.append("references/zcode-baseline.json: zcode must be an object")
        return
    pairs = (
        ("app_version", "zcode_app_version"),
        ("cli_version", "zcode_cli_version"),
        ("runtime_model", "zcode_runtime"),
    )
    for baseline_key, version_key in pairs:
        if zcode.get(baseline_key) != version.get(version_key):
            errors.append(
                f"references/zcode-baseline.json: zcode.{baseline_key} disagrees with "
                f"build/version.json:{version_key}"
            )
    app = str(version.get("zcode_app_version", ""))
    if not str(zcode.get("app_build", "")).startswith(f"{app}."):
        errors.append("references/zcode-baseline.json: zcode.app_build must extend app_version")
    if not str(zcode.get("linux_deb_package_version", "")).startswith(f"{app}-"):
        errors.append(
            "references/zcode-baseline.json: zcode.linux_deb_package_version must extend app_version"
        )
    support = baseline.get("platform_support")
    if not isinstance(support, dict):
        errors.append("references/zcode-baseline.json: platform_support must be an object")
        return
    platforms = support.get("platforms")
    if not isinstance(platforms, dict) or sorted(platforms) != ["macos", "ubuntu"]:
        errors.append(
            "references/zcode-baseline.json: platform_support.platforms must define macos and ubuntu"
        )
    verified = parse_utc(support.get("verified_at_utc"))
    expires = parse_utc(support.get("expires_at_utc"))
    if verified is None or expires is None or verified >= expires:
        errors.append(
            "references/zcode-baseline.json: platform_support verified/expiry window is invalid"
        )


def check_manifest(manifest: dict, errors: list[str]) -> None:
    command_policy = manifest.get("command_option_policy")
    if not isinstance(command_policy, dict):
        errors.append("build/manifest.json: command_option_policy must be an object")
        return
    bootstrap_options = command_policy.get("bootstrap")
    bootstrap_option_names = (
        {str(option) for option in bootstrap_options}
        if isinstance(bootstrap_options, list)
        else set()
    )
    if "--allow-pinned-unnotarized" not in bootstrap_option_names:
        errors.append(
            "build/manifest.json: command_option_policy.bootstrap must include "
            "--allow-pinned-unnotarized"
        )
    artifact_policy = manifest.get("artifact_integrity_policy")
    macos_identity = (
        artifact_policy.get("macos_identity", "")
        if isinstance(artifact_policy, dict)
        else ""
    )
    if "--allow-pinned-unnotarized" not in str(macos_identity):
        errors.append(
            "build/manifest.json: artifact_integrity_policy.macos_identity must document "
            "--allow-pinned-unnotarized"
        )
    install_options = command_policy.get("install")
    install_option_names = (
        {str(option) for option in install_options}
        if isinstance(install_options, list)
        else set()
    )
    if "--posture" not in install_option_names:
        errors.append("build/manifest.json: command_option_policy.install must include --posture")
    setup_policy = manifest.get("setup_state_policy")
    if not isinstance(setup_policy, dict):
        errors.append("build/manifest.json: setup_state_policy must be an object")
    else:
        if setup_policy.get("default_setup") != DEFAULT_SETUP:
            errors.append("build/manifest.json: setup_state_policy.default_setup must be nddev-builder")
        if setup_policy.get("posture_option") != "--posture full-auto|safe, default full-auto":
            errors.append("build/manifest.json: setup_state_policy.posture_option is invalid")
    transaction_policy = manifest.get("transaction_policy")
    if not isinstance(transaction_policy, dict):
        errors.append("build/manifest.json: transaction_policy must be an object")
    else:
        path_boundaries = str(transaction_policy.get("path_boundaries", ""))
        locking = str(transaction_policy.get("locking", ""))
        commit = str(transaction_policy.get("commit", ""))
        rollback = str(transaction_policy.get("rollback", ""))
        if (
            "reject ASCII C0 controls (U+0000-U+001F) and DEL (U+007F)" not in path_boundaries
            or "before coordination or filesystem mutation" not in path_boundaries
            or "preserving spaces, Unicode, and relative-path resolution" not in path_boundaries
        ):
            errors.append(
                "build/manifest.json: transaction_policy.path_boundaries must declare "
                "pre-coordination C0/DEL rejection and preserved path semantics"
            )
        required_locking = (
            "role-independent canonical-path digest",
            "legacy-byte-compatible target marker",
            "product EX through the complete lifecycle",
            "quiesce every bounded existing path anchor",
            "deterministic sorted target, requested-backup",
            "without anchor creation or repair",
            "without cleanup deletion paths",
        )
        if any(marker not in locking for marker in required_locking):
            errors.append(
                "build/manifest.json: transaction_policy.locking must declare "
                "mixed-version multi-resource coordination and no-create reads"
            )
        if (
            "actual commit decision" not in commit
            or "complete graphs" not in commit
            or "parent identities" not in commit
        ):
            errors.append(
                "build/manifest.json: transaction_policy.commit must declare final "
                "identity/graph/parent revalidation"
            )
        if "fd-bound no-follow cleanup namespace authority" not in rollback:
            errors.append("build/manifest.json: transaction_policy.rollback must declare cleanup namespace authority")
        backup_policy = manifest.get("backup_policy")
        inventory = (
            str(backup_policy.get("inventory", ""))
            if isinstance(backup_policy, dict)
            else ""
        )
        if (
            "no-create backup-resource read" not in inventory
            or "fixed redacted classifications" not in inventory
            or "valid historical SemVer/timestamps" not in inventory
        ):
            errors.append(
                "build/manifest.json: backup_policy.inventory must declare safe no-create listing"
            )
    adoption_policy = manifest.get("adoption_policy")
    if not isinstance(adoption_policy, dict):
        errors.append("build/manifest.json: adoption_policy must be an object")
    else:
        marker_policy = adoption_policy.get("marker")
        expected_marker_policy = {
            "schema": 1,
            "exact_keys": [
                "schema",
                "type",
                "original_target",
                "created_at",
                "installer_build",
                "payload",
            ],
            "installer_build": "canonical SemVer 2.0.0; restore accepts valid historical builds",
            "created_at": "canonical UTC YYYY-MM-DDTHH:MM:SSZ with second precision",
            "original_target": "ASCII C0/DEL-free canonical absolute non-root path",
            "validation_order": (
                "the complete marker is validated before target binding or relocation authorization"
            ),
        }
        if marker_policy != expected_marker_policy:
            errors.append("build/manifest.json: adoption_policy.marker is invalid")
        restore = str(adoption_policy.get("restore", ""))
        if (
            "validated original target is enforced" not in restore
            or "explicit absolute --target" not in restore
            or "--allow-target-relocation" not in restore
        ):
            errors.append(
                "build/manifest.json: adoption_policy.restore must declare validated "
                "target binding and explicit absolute relocation"
            )


def check_lifecycle_source(errors: list[str]) -> None:
    manager_path = ROOT / "cli-tools" / "nddev_zcode.py"
    bootstrap_path = ROOT / "cli-tools" / "scripts" / "bootstrap.sh"
    common_path = ROOT / "cli-tools" / "scripts" / "lib" / "common.sh"
    try:
        manager = manager_path.read_text(encoding="utf-8")
        bootstrap = bootstrap_path.read_text(encoding="utf-8")
        common = common_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"public lifecycle source is unreadable: {exc}")
        return
    required_manager_markers = (
        "class DirectoryAuthority:",
        "class CleanupAuthority:",
        "def cleanup_authority(",
        "def cleanup_root_authority(",
        "open_child_directory_authority(",
        "dir_fd=authority.root.fd",
        "native_rename_child_noreplace(",
        "def native_rename_noreplace(",
        "source_parent.fd",
        "destination_parent.fd",
        "expected_graph=",
        '"gid"',
        "O_DIRECTORY",
        "O_NOFOLLOW",
        '"coordination"',
        '"cleanup"',
        '"entry_count"',
        '"target_digest"',
        "def reject_transaction_path_controls(",
        "def print_plan_coordination(",
        "class CanonicalResource:",
        "class PendingCoordinationSnapshot:",
        "def transaction_coordination(",
        "def run_read_only_resources(",
        "def run_transaction_plan(",
        "def run_backup_read_only(",
        "def existing_resource_digests(",
        "def pending_coordination_snapshot(",
        "if after != before:",
        "validate_live_commit_decision(target)",
        "validate_retired_cleanup_authority(target, backups)",
        "def backup_inventory_entries(",
        "original = validate_adoption_marker_payload(marker)",
        '"[redacted-invalid-name]"',
        "cleanup_pending_state(target, recover_aliases=False)",
        "recover_empty_cleanup_root_before_mutation(target)",
        "def canonical_adoption_original_target(",
        "def validate_adoption_timestamp(",
        "original = validate_adoption_marker_payload(marker)",
        "expected_build=build_version()",
        "--allow-target-relocation requires an absolute --target",
    )
    for marker in required_manager_markers:
        if marker not in manager:
            errors.append(f"cli-tools/nddev_zcode.py: missing lifecycle marker {marker!r}")
    for marker in (
        'reject_transaction_path_controls(value, "target")',
        'reject_transaction_path_controls(value, "backup root")',
    ):
        if manager.count(marker) != 2:
            errors.append(
                "cli-tools/nddev_zcode.py: transaction path control policy must guard "
                f"the resolver and canonicalizer exactly once for {marker!r}"
            )
    if "cleanup_pending=true" not in bootstrap or "command reports success with pending cleanup" not in bootstrap:
        errors.append("cli-tools/scripts/bootstrap.sh: post-commit cleanup must report success with cleanup_pending=true")
    if "shutil.rmtree(str(tombstone))" in manager:
        errors.append("cli-tools/nddev_zcode.py: cleanup journal drain must not use path-based rmtree")
    if "os.rename(str(source), str(destination))" in manager:
        errors.append(
            "cli-tools/nddev_zcode.py: lifecycle rename must use native fd-bound no-replace"
        )
    if '"root": str(cleanup_root_for(target))' in manager:
        errors.append("cli-tools/nddev_zcode.py: status cleanup metadata must not expose cleanup deletion paths")
    if "rm -rf --" in common or "rm -f --" in common:
        errors.append("cli-tools/scripts/lib/common.sh: cleanup must use identity-bound fd-safe deletion, not rm fallback")


def check_marketplaces(errors: list[str]) -> None:
    marketplaces_root = ROOT / "zcode_tools" / "marketplaces"
    catalog = (
        sorted(p for p in marketplaces_root.iterdir() if p.is_dir())
        if marketplaces_root.is_dir()
        else []
    )
    names = [path.name for path in catalog]
    if names != [DEFAULT_SETUP]:
        errors.append(
            "zcode_tools/marketplaces/: managed public catalog must contain only "
            f"{DEFAULT_SETUP}, found {names}"
        )
    for marketplace_dir in catalog:
        relative = marketplace_dir.relative_to(ROOT).as_posix()
        manifest = load_json(f"{relative}/marketplace.json", errors)
        if manifest is None:
            continue
        if manifest.get("name") != marketplace_dir.name:
            errors.append(f"{relative}/marketplace.json: name must equal directory name")
        plugins = manifest.get("plugins")
        if not isinstance(plugins, list):
            errors.append(f"{relative}/marketplace.json: plugins must be an array")
            continue
        for entry in plugins:
            if not isinstance(entry, dict):
                errors.append(f"{relative}/marketplace.json: plugin entries must be objects")
                continue
            source = str(entry.get("source", ""))
            if not source.startswith("./"):
                errors.append(
                    f"{relative}/marketplace.json: plugin source must be relative: {source}"
                )
                continue
            plugin_dir = marketplace_dir / source[2:]
            if not plugin_dir.is_dir():
                errors.append(f"{relative}/marketplace.json: plugin source missing: {source}")
                continue
            plugin_manifest = plugin_dir / ".zcode-plugin" / "plugin.json"
            if plugin_manifest.is_file():
                plugin_relative = plugin_manifest.relative_to(ROOT).as_posix()
                plugin = load_json(plugin_relative, errors)
                if plugin is not None and not str(plugin.get("name", "")).strip():
                    errors.append(f"{plugin_relative}: name must be a non-empty string")


def main() -> int:
    errors: list[str] = []

    version = load_json("build/version.json", errors)
    baseline = load_json("references/zcode-baseline.json", errors)
    manifest = load_json("build/manifest.json", errors)
    if (ROOT / "build" / "release-evidence.json").exists():
        errors.append("build/release-evidence.json: release evidence belongs in private validation")

    version_file = ROOT / "VERSION"
    declared = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None
    if declared is None:
        errors.append("missing VERSION file")

    if version is not None:
        if declared is not None and version.get("build_version") != declared:
            errors.append(
                "VERSION and build/version.json:build_version disagree: "
                f"{declared!r} != {version.get('build_version')!r}"
            )
        check_readme(version, errors)
        check_artifacts(version, errors)
        if baseline is not None:
            check_baseline(version, baseline, errors)
        builder = load_json(
            "zcode_tools/marketplaces/nddev-builder/plugins/core/.zcode-plugin/plugin.json", errors
        )
        if builder is not None and builder.get("version") != version.get("build_version"):
            errors.append(
                "nddev-builder core plugin version disagrees with build/version.json:build_version"
            )
        marketplace = load_json(
            "zcode_tools/marketplaces/nddev-builder/marketplace.json", errors
        )
        if marketplace is not None:
            core_entries = [
                entry
                for entry in marketplace.get("plugins", [])
                if isinstance(entry, dict) and entry.get("name") == "core"
            ]
            if len(core_entries) == 1 and core_entries[0].get("version") != version.get(
                "build_version"
            ):
                errors.append(
                    "nddev-builder marketplace core plugin version disagrees with "
                    "build/version.json:build_version"
                )

    if manifest is not None and version is not None:
        if manifest.get("build_version") != version.get("build_version"):
            errors.append("build/manifest.json:build_version disagrees with build/version.json")
        check_manifest(manifest, errors)

    check_marketplaces(errors)
    check_lifecycle_source(errors)

    if errors:
        print(f"validate_public_contracts.py: FAIL ({len(errors)} error(s))")
        for item in errors:
            print(f"  - {item}")
        return 1
    print("validate_public_contracts.py: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
