# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.4] - 2026-07-09

### Fixed
- **CI codeql workflow: permissions corrected.** Added `actions: read` to the
  top-level permissions (the reusable workflow needs it alongside
  `security-events: write` and `contents: read`).
- **CI scorecard workflow: permissions corrected.** Added `actions: read` and
  `id-token: write` (required by the reusable scorecard workflow for OIDC).
- **CI security-static: grep no longer matches its own command line.** Changed
  the action-pin checker grep from bare `uses:` to `^\s*uses:\s` (YAML key
  pattern), preventing the checker from matching its own grep command inside
  the shell script body.
- **CI validate: ShellCheck SC2034 false positives silenced.** Added
  `# shellcheck disable=SC2034` for `platform` (passed but unused inside
  `install_sequence`) and `NDDEV_BACKUP_PATH` (set in function, read by
  platform runners as a cross-function global).
- **CI codeql: languages corrected.** Removed `python` from the CodeQL scan
  languages — this is a shell/JSON/Markdown project with no Python source
  files (only `pyproject.toml` metadata and Python one-liners inside shell
  scripts). CodeQL now scans `actions` only.

## [1.0.3] - 2026-07-09

### Fixed
- **CI workflows: all stale action SHAs corrected.** 9 action references across 8
  workflows had SHAs that GitHub Actions could no longer resolve (force-pushed tags,
  annotated-tag vs commit-SHA mismatches, or nonexistent version tags):
  - `nddev-ci-workflows` (5 workflows): pinned annotated-tag SHA → dereferenced to
    commit SHA `1acba68` (the actual 0.3.0 commit).
  - `actions/setup-python` v6: stale SHA `a26af69` → `ece7cb0`.
  - `actions/labeler` v6: stale SHA `8c99a5e` → `b8dd2d9`.
  - `ludeeus/action-shellcheck`: pinned "2.2.0" (never existed) → corrected to
    2.0.0 commit SHA `00cae50`.
  - `softprops/action-gh-release` v2.3.2: fixed in 1.0.1 (SHA `5ac8` → `5cd8`).
  All CI workflows (validate, security-static, codeql, cross-platform, secret-scan,
  scorecard, dependency-review, labeler) now resolve correctly.

## [1.0.2] - 2026-07-09

### Added
- **6 new builder skills** for the `nddev-builder/core` plugin (9 → 15 skills):
  - `list-components` — list all plugins/skills/commands/agents/hooks/MCP/providers
    in a marketplace (read-only inventory).
  - `remove-component` — safely remove a component (checks references first,
    updates marketplace.json, validates).
  - `enable-plugin` — populate `enabledPlugins` in cli-config template
    (key format: `plugin-name@marketplace-name`).
  - `add-provider` — add a model provider (LLM endpoint) to v2-config, with
    `${VAR}` secret handling and anthropic/openai-style provider support.
  - `add-reference` — add a reference doc to a plugin bundle
    (`plugins/<name>/references/<doc>.md`).
  - `add-tool` — add a CLI tool (non-MCP) with executable script + README +
    optional companion skill (the CLI+skill pattern as an MCP alternative).
- **6 new slash commands**: `/nddev-list`, `/nddev-remove`, `/nddev-enable`,
  `/nddev-add-provider`, `/nddev-add-reference`, `/nddev-add-tool`.

### Changed
- **Doctor Step 7 no longer hardcodes `nddev-builder`** — now loops over ALL
  marketplaces (`zcode_tools/marketplaces/*/`) on both platforms. A broken
  template in any marketplace (builder, designer, developer) is now caught.
- **Core plugin version bumped 1.0.0 → 1.1.0** (minor: 6 new backward-compatible
  capabilities). `marketplace.json` and `plugin.json` updated in sync.

## [1.0.1] - 2026-07-09

### Added
- **`nddev-developer` marketplace** — a developer-oriented ZCode setup for
  full-stack engineering and writing any code. Currently a placeholder scaffold
  (empty `skills/`/`commands/`/`agents/`/`plugins/`); to be filled with
  full-stack development plugins. Distinct from `nddev-builder` (meta-tooling
  for creating marketplaces/plugins).
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

### Fixed
- **`restore` command data-loss bug (critical).** When all 10 backup slots were
  full, the pre-restore `backup_current` call could reuse the oldest slot and
  delete the exact backup being restored from, then `rm -rf` the target, then
  fail on `cp` — leaving the user with neither source nor target. The restore
  source is now staged to a temp directory before any destructive operation,
  and re-validated after the pre-restore backup.
- **`restore` now requires a `BUILD-VERSION` guard** on the existing target
  (same as `remove`), preventing accidental destruction of a non-nddev directory
  via `--target`.
- **Pre-restore `backup_current` failure no longer silenced.** Previously
  `2>/dev/null || true` swallowed all errors; a failed backup now aborts the
  restore before any destructive operation.
- **Selective restore replaces stale dirs instead of merging.** `restore.sh`
  now uses `replace` mode for authoritative paths (`cli/agents`, `cli/artifacts`,
  `v2/certs`) — stale files from the fresh build no longer survive. `cli/db`
  keeps `merge` mode to preserve partial database state.
- **`restore.sh` type-mismatch handling.** If a backup entry is a dir but the
  target is a file (or vice versa), the target is normalized before copy instead
  of failing or nesting.
- **`cli/artifacts` now pre-created** by `create_runtime_dirs` (was restored but
  never created, causing an asymmetry on fresh installs).
- **`load_env` key validation.** Malformed env keys (e.g. containing spaces) are
  now skipped with a warning instead of crashing `export` under `set -e`.
- **`detect_cli_version` empty-result fallback.** A non-numeric `zcode --version`
  first line no longer produces an empty string (now defaults to `unknown`),
  preventing a spurious mismatch warning.
- **Bootstrap `app_entry` is now platform-aware.** When the ZCode app is already
  installed (skip-download path), the entry point is chosen based on `$PLATFORM`
  instead of defaulting to the macOS path and correcting on Linux.

### Changed
- **Doctor stale-path rule updated.** `nddev-developer` is now a valid active
  marketplace name (removed from the stale-path list in the `doctor` skill).
  Only the bare `nddev` name remains flagged as stale.
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
- Renamed the marketplace from `nddev` to `nddev-builder`; the developer toolkit
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
