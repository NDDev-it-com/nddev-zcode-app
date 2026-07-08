# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- `development/` — meta-skills directory for workflows that develop this repo.
- `docs/` — install, architecture, and secrets documentation.
- OSS scaffolding: `LICENSE` (AGPL-3.0-or-later), `NOTICE`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and minimal GitHub CI.
