# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Restructured `zcode_tools/` to support **multiple marketplaces**: each lives in
  its own directory under `zcode_tools/marketplaces/<name>/` (root `marketplace.json`
  + `plugins/`), instead of a single root `marketplace.json` + flat `plugins/`.
- Renamed the marketplace from `nddev` to **`nddev-developer`** (it is its own
  marketplace, not a plugin inside `nddev`). The developer toolkit is now the
  `core` plugin inside the `nddev-developer` marketplace.
- Installer (`cli-tools/scripts/lib/build.sh`) now copies the whole `marketplaces/`
  tree into `~/.zcode/marketplaces/` and validates every marketplace manifest.
- CI workflows (`validate.yml`, `cross-platform.yml`) now glob all marketplace and
  plugin manifests dynamically instead of a hardcoded `marketplace.json` path.
- Updated `repo-orientation` skill, `architecture.md`, `manifest.json`, and the
  `zcode-native-format.md` reference to the multi-marketplace layout.

## [1.0.0] - 2026-07-09

### Added
- Initial scaffold of `nddev-zcode-app`, a build system + installer that
  recreates a complete, version-stamped `~/.zcode` from source on macOS
  (desktop) and Ubuntu (desktop/server).
- `zcode_tools/` — the source of a complete `~/.zcode`: `AGENTS.md`,
  `skills/`, `commands/`, `agents/`, `marketplace.json` (name `nddev`,
  empty plugins list), `plugins/` skeleton, and `cli-config`/`v2-config`/
  `v2-setting` templates with `${VAR}` secret placeholders.
- `cli-tools/` — the installer: `install.sh` entry point (`--platform`,
  `--apply`/`--plan`), shared `lib/` (common, version, build), macOS and
  Ubuntu runners, and `restore.sh` for selective runtime-state restore.
- `build/` — `version.json`, `manifest.json`, per-OS `system/` dirs, and
  `.env.example` (committed secret template; real `.env` gitignored).
- `config/nddev-contract.json` — product contract: native format, secrets
  policy, backup/restore references.
- `references/zcode-baseline.json` — verified ZCode runtime baseline.
- `.serena/` — Serena project config (`project.yml`), `.gitignore`, and
  durable project memory (`memories/INDEX-01-OVERVIEW.md`).
- `.agents/skills/repo-orientation/` — repository map skill (read first when
  working in this repo), with `.claude/skills/` symlink and `.claude/CLAUDE.md`
  bridge.
- `development/` — meta-skills directory for workflows that develop this repo.
- `docs/` — install, architecture, and secrets documentation.
- OSS scaffolding: `LICENSE` (AGPL-3.0-or-later), `NOTICE`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and minimal GitHub CI.
- GitHub CI: `validate`, `security-static`, `cross-platform`, `labeler`,
  `codeql`, `dependency-review`, `scorecard`, and tag-driven `release`;
  `FUNDING.yml` and `branch-protection/main.json`.
