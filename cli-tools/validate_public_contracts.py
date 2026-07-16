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
        if key.startswith("macos"):
            if entry.get("app_version") != app:
                errors.append(f"{context}: app_version must equal zcode_app_version")
            bundle = str(entry.get("bundle_version", ""))
            if not bundle.startswith(f"{app}."):
                errors.append(f"{context}: bundle_version must extend app version {app}")
            bundle_versions.add(bundle)
            for field in ("team_id", "bundle_id"):
                if not str(entry.get(field, "")).strip():
                    errors.append(f"{context}: {field} must be a non-empty string")
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


def check_marketplaces(errors: list[str]) -> None:
    marketplaces_root = ROOT / "zcode_tools" / "marketplaces"
    catalog = (
        sorted(p for p in marketplaces_root.iterdir() if p.is_dir())
        if marketplaces_root.is_dir()
        else []
    )
    if not catalog:
        errors.append("zcode_tools/marketplaces/: no marketplace setups found")
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
    evidence = load_json("build/release-evidence.json", errors)

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

    if manifest is not None and version is not None:
        if manifest.get("build_version") != version.get("build_version"):
            errors.append("build/manifest.json:build_version disagrees with build/version.json")

    if evidence is not None:
        if evidence.get("schema_version") != 2:
            errors.append("build/release-evidence.json: schema_version must be 2")
        decision = evidence.get("promotion", {})
        if not isinstance(decision, dict) or decision.get("decision") not in {
            "approved",
            "pending",
        }:
            errors.append(
                "build/release-evidence.json: promotion.decision must be approved or pending"
            )

    check_marketplaces(errors)

    if errors:
        print(f"validate_public_contracts.py: FAIL ({len(errors)} error(s))")
        for item in errors:
            print(f"  - {item}")
        return 1
    print("validate_public_contracts.py: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
