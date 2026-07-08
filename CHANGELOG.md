# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`bootstrap` command — install ZCode from zero.** Downloads and installs the
  ZCode desktop app + CLI at the pinned version (macOS `.dmg` → `/Applications/`,
  Ubuntu `.deb` → `dpkg`), then wires the `zcode` CLI launcher into `~/.local/bin`.
  Uses the official CDN (`cdn-zcode.z.ai`) with per-platform/per-arch artifacts
  recorded in `build/version.json`. Skips the download if the pinned version is
  already installed. Full from-zero flow: `bootstrap` → `install`.
- **ZCode runtime version pinning.** `build/version.json` now pins the exact
  ZCode desktop app (`3.3.3`) and CLI (`0.15.0`) versions this build was verified
  against. The installer detects the running ZCode and warns if it differs from
  the pin (advisory, non-blocking). `BUILD-VERSION` stamps both versions.
- **hooks.json / mcp.json are now functional.** The installer merges per-event
  hook arrays from `hooks.json` into `cli/config.json.hooks`, and MCP servers
  from `mcp.json` into `cli/config.json.mcp.servers`. Previously these files
  were documented as merged but never read.
- **Full installer lifecycle: install, update, switch, remove.** New `remove`
  command backs up then deletes the target (refuses directories without
  `BUILD-VERSION` as a safety check). Re-running `install` with the same
  marketplace = update; with a different one = switch.
- **Custom install directory.** `--target <dir>` flag and `ZCODE_TARGET` /
  `ZCODE_BACKUPS_DIR` in `build/.env` let you install anywhere, not just `~/.zcode`.
  Resolution: `--target` > `ZCODE_TARGET` (.env) > `~/.zcode`.
- **`build/.env` now loaded by the installer** (`nddev::load_env`) for both the
  target directory and secrets — one file configures everything.
- **Free OSS CI suite** from `nddev-ci-workflows@0.3.0`: `codeql`,
  `dependency-review`, `secret-scan`, `scorecard`, and `cross-platform-smoke`,
  all pinned by full SHA. Repo flipped to PUBLIC to enable the free tier.

### Changed
- **Each marketplace is now a self-contained `~/.zcode` setup.** AGENTS.md, config
  templates (cli-config/v2-config/v2-setting), mcp/hooks, and user-scope
  skills/commands/agents moved *inside* each marketplace directory
  (`zcode_tools/marketplaces/<name>/`). The `zcode_tools/` root no longer holds
  shared system files.
- Installer refactored: `--marketplace <name>` (required) selects ONE setup and
  builds a clean `~/.zcode` entirely from it. `--list` shows available setups.
  Switching setups = rebuild from a different marketplace (old `~/.zcode` backed up).
- The selected marketplace is installed both as the source of `~/.zcode/AGENTS.md`
  and config, AND as `~/.zcode/marketplaces/<name>/` so ZCode Plugin Management
  can discover its plugins.
- Updated `repo-orientation` skill, `AGENTS.md`, `architecture.md`, `install.md`,
  `manifest.json`, and CI workflows to the self-contained marketplace model.
- Renamed the marketplace from `nddev` to `nddev-developer`; the developer toolkit
  is the `core` plugin inside it.

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
