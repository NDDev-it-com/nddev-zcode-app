# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.5] - 2026-07-19

### Added

- The `nddev-builder` `core` toolkit gains three workflow skills (and matching
  slash commands) on top of the `add-*` set: `scaffold-plugin` composes a whole
  plugin from an intent, `devtest-plugin` runs an isolated install-and-verify
  loop in throwaway `HOME`/`ZCODE_HOME`, and `release-review` gates a whole
  marketplace for release readiness. These stay within the ZCode 3.3.6 surface
  (flatten-to-user-scope; no `plugin add`, cache, or dev-mode), so no publish,
  managed-requirements, or remote-marketplace-source features were added. The
  toolkit is now 19 skills / 19 slash commands.

## [2.1.4] - 2026-07-16

### Changed

- Advanced the verified runtime to official ZCode 3.3.6 (build 3.3.6.3198,
  released 2026-07-15). All six native artifacts were independently re-pinned
  by filename, byte size, and SHA-512; macOS signature, Team ID, bundle
  identity, and notarization were re-verified; Debian package identity is
  3.3.6-3198; the embedded CLI remains byte-identical 0.15.2 across all six
  distributions.
- Corrected the README build/runtime summary and made the public contract
  validator enforce exact README parity with the canonical version metadata.

## [2.1.3] - 2026-07-14

### Changed

- Verified ZCode runtime advanced to the official app 3.3.5 (build 3.3.5.3027,
  released 2026-07-13): all six download artifacts re-pinned by independently
  derived filename, byte size, and SHA-512; macOS bundle identity, Developer ID
  signature, and notarization re-verified; Debian package version 3.3.5-3027;
  embedded CLI remains 0.15.2 (rebuilt bundle, byte-identical across all six
  artifacts).
- `build/release-evidence.json` upgraded to execution-bound schema version 2:
  promotion starts as `pending` and becomes `approved` only from real per-lane
  CI result records plus a vendor-currentness observation; approval is never a
  default.

### Added

- `cli-tools/validate_public_contracts.py`: repository-owned public fast
  verification (version lockstep, artifact identity shape, baseline
  cross-references, marketplace/plugin catalog integrity) declared in
  `.gds/repository.yaml` as the required test command.
- GDS generated projections (`AGENTS.md`, `.claude/CLAUDE.md`,
  `.gds/bundle.lock.yaml`, `.gds/compiled-policy.json`) refreshed from bundle
  source 7120d79.

### Added

- Machine-readable per-platform support tiers in
  `references/zcode-baseline.json:platform_support`: macOS is a vendor
  general-availability download and Ubuntu is NDDev-supported on top of the
  vendor Linux beta channel, each with an explicit verified/expiry freshness
  window.
- A tracked `build/release-evidence.json` bundle binding a release to the
  validated harness commit and a content digest of the exact module setup; the
  release workflow refuses to publish without a present, consistent bundle.
- A declared minimal `runtime_bundle` path set in `build/manifest.json`: the
  install-required tracked paths (installer, catalogs, build and runtime
  metadata, license) excluding governance, CI, and source-level documentation.

### Changed

- The release workflow now publishes the minimal `runtime_bundle` as a second,
  attested release asset (`runtime_paths`) alongside the full source archive,
  and pins the shared supply-chain workflow to `0.7.0`.

## [2.1.2] - 2026-07-10

### Fixed

- Added the explicit `provider/model` bootstrap and matching secret-free
  provider definition required by ZCode CLI 0.15.2, so every rendered setup can
  create a desktop agent session before ZCode mounts the restored OAuth
  credential.
- Moved optional API-key providers to distinct `custom:*` identities instead
  of shadowing ZCode-owned `builtin:*` providers. Restored Z.ai OAuth state can
  now reactivate its app-managed coding-plan provider without inheriting a
  template-level `enabled: false` override.
- Made plan and apply fail closed when a setup omits its main model reference,
  the referenced provider/base URL/model declaration, or assigns a custom
  provider a reserved `builtin:*` identity.

### Changed

- Bumped the public build and `nddev-builder/core` component to 2.1.2. The
  verified ZCode 3.3.4 application, CLI 0.15.2, runtime model, and native
  artifact identity pins are unchanged.

## [2.1.1] - 2026-07-10

### Changed

- Updated the verified runtime baseline to ZCode 3.3.4 (build 3.3.4.2877) and
  CLI 0.15.2. Repinned all six macOS and Linux artifacts by exact filename,
  byte size, SHA-512 digest, native architecture, package identity, bundle
  identity, Developer ID team, and notarization evidence.
- Bumped the public build and `nddev-builder/core` component to 2.1.1 without
  changing the product-contract or installed-stamp schema.

### Fixed

- Preserved `v2/tasks-index.sqlite` together with `cli/db/` during setup
  installation and switching, preventing the desktop task index from becoming
  detached from the restored CLI session database.
- Preserved legacy `v2/sessions/` snapshots when present so ZCode's supported
  session-migration path remains available after setup changes.
- Preserved current and legacy bot definition state while continuing to omit
  derived bot-model, coding-plan, telemetry, log, crash, rollout, and execution
  caches from newly rendered setups.
- Refused apply-mode install, switch, remove, and restore operations while the
  task/session databases are open or SQLite recovery sidecars are present,
  preventing inconsistent cross-store snapshots of a running ZCode instance.

## [2.1.0] - 2026-07-10

### Added

- Added `--setup <id>` as the canonical setup selector while preserving
  `--marketplace <id>` as a backward-compatible native-format alias.
- Added stable `list --json` setup discovery and `status [--target] [--json]`
  inspection for missing, unmanaged, legacy-managed, and setup-aware managed
  installations.
- Added `BUILD-VERSION` schema 2 with a required `setup_id`, so installed and
  backed-up trees retain the exact setup identity used to build them.

### Changed

- Upgraded the public product contract to version 3 and documented the setup
  catalog, setup-selection aliases, machine-readable interfaces, and stamp
  compatibility policy.
- Made staged-build verification fail closed unless the schema-2 stamp setup
  identity matches the selected setup. Legacy schema 0 and 1 stamps remain
  readable for safe recovery operations and report an unknown setup identity.
- Bumped the public build and `nddev-builder/core` component to 2.1.0. ZCode
  application, CLI, runtime, and artifact identity pins are unchanged.

## [2.0.2] - 2026-07-10

### Security

- Upgraded every reusable workflow caller to the immutable
  `nddev-ci-workflows` 0.5.1 commit. Numeric releases now publish canonical
  `release-notes.md` inside the exact manifest and checksum closure, preserving
  note integrity independently of GitHub's editable release body.

### Changed

- Bumped the public build and `nddev-builder/core` component to 2.0.2. Runtime
  behavior, supported ZCode versions, and native artifact identity pins are
  unchanged from 2.0.1.

## [2.0.1] - 2026-07-10

### Security

- Required verified signatures and linear history on `main`, protected SemVer
  tags from update or deletion, and enabled immutable releases for future
  publications.
- Pinned every ZCode 3.3.3 distribution artifact by exact filename, byte size,
  and SHA-512, with macOS signing identity and Debian package identity recorded
  for platform-native verification.
- Verified HTTPS-only download redirects, DMG/Gatekeeper/code-signing identity,
  exact DEB control metadata and package-owned CLI paths, and strict app/CLI
  postconditions before bootstrap can report success.
- Restricted bootstrap to the exact canonical ZCode CDN base and the verified
  DEB CLI path `/opt/ZCode/resources/glm/zcode.cjs`; DEB apply now requires a
  successful privileged `dpkg --dry-run -i` before the real transaction.
- Added private pre-install DEB payload extraction: the exact CLI path, safe
  file shape, and pinned CLI version must pass before dpkg runs. The installed
  dpkg-owned CLI must then be byte-identical by SHA-512 to that verified entry.
- Added deterministic app/launcher bootstrap locks and rollback-protected swaps.
  Exact postconditions define the commit point; incomplete post-commit cleanup
  reports failure without discarding verified committed state.
- Revalidated the 2.0.1 artifact pins against repeated current CDN downloads.
  Bootstrap now fails closed on digest drift even when byte size is unchanged;
  a pin is accepted only after SHA-512 and native identity are reconciled.
- Replaced the release publisher with the SHA-pinned shared supply-chain
  workflow: 2.0.1 publishes an immutable source archive, SHA256 manifest, SPDX
  SBOM, build-provenance attestation, and SBOM attestation after local version
  parity succeeds.
- Required strict SemVer equality across the tag, all module build-version
  sources, and both core-plugin version sources; the tagged commit must be an
  ancestor of freshly fetched `origin/main` before publication.
- Hardened the privileged pull-request labeler before any action runs, removed
  source checkout, allowlisted only required egress, and isolated cancellation
  by pull-request number.
- Added always-on actionlint and fork-safe pedantic zizmor gates through the
  exact shared CI release, with low-or-higher workflow-security findings fatal.
- Replaced live-tree mutation with private same-filesystem staging, full
  pre-commit verification, exclusive target and backup-pool locks, held rotation
  slots, fsync, atomic rename, and rollback of both the target and displaced
  slot.
- Replaced the marker-only guard with a validated `BUILD-VERSION` schema,
  canonical/disjoint path containment, rejection of symlinks/special
  files/hardlink aliases, and explicit typed envelopes for reversible adoption
  of an unstamped target.
- Corrected the source/runtime secret boundary: rendered `.env`, provider and
  MCP configs, `v2/credentials.json`, certificates, and backups are explicitly
  classified as sensitive and owner-only.
- Required `build/.env` to be a current-user-owned regular non-symlink with mode
  `0600` or stricter. Parsing remains non-evaluating, with narrow HOME-prefix
  expansion limited to target and backup path keys.
- Made plan and apply reject missing or empty placeholders in keys or values
  across active config, setting, provider, MCP, and hook branches; only
  explicitly disabled provider/MCP nodes may remain dormant.
- Replaced extension-authoring guidance to shell-source `.env` files with an
  approved process-environment contract and non-evaluating, allowlisted parsing.

### Changed

- Bumped the public build and `nddev-builder/core` component to 2.0.1;
  upgraded the artifact metadata contract to schema 2.
- Standardized module, managed-stamp, adoption-envelope, and backup-name version
  parsing on SemVer 2.0.0 rules instead of permissive SemVer-like patterns.
- Upgraded the public product contract to version 2 and distinguished plugin
  `mcpServers` inputs from the installed `mcp.servers` configuration path.
- Made `nddev-designer` and `nddev-developer` production-ready minimal profiles
  with substantive role-specific instructions. Their empty global extension
  surfaces are intentional: project tools and policy come from the active
  workspace.
- Kept Z.ai account OAuth as the verified ZCode 3.3.3 preference while defining
  explicit Z.ai API-key access as a separate, disabled-by-default custom
  provider at `https://api.z.ai/api/anthropic`. BigModel remains a separate,
  disabled-by-default provider on `https://open.bigmodel.cn/api/anthropic`.
- Hardened repository governance to squash-only merges using pull-request
  titles, branch-update support, automatic deletion of merged branches, and
  disabled wiki/projects surfaces.

### Fixed

- Enabled `core@nddev-builder` by default so the advertised builder toolkit is
  active after installation.
- Started `recentProjects` as an empty portable list instead of shipping a
  workstation-specific repository path.
- Repaired the malformed Markdown fence in the `add-mcp-server` skill and
  aligned provider/tool authoring guidance with the runtime secret contract.
- Removed unsourced, volatile numeric token-cost claims and replaced absolute
  zero-cost language with the durable routing-metadata/on-demand context model.
- Used a verified, locally extracted AppImage on Ubuntu only when the complete
  dpkg toolchain is absent; DEB installation failures now remain fatal instead
  of producing a false-success dependency-repair path.
- Preferred current `diskutil image attach`/`eject` operations on macOS while
  retaining deprecated `hdiutil` mount operations only as a compatibility
  fallback; DMG checksum verification still requires `hdiutil verify`.
- Required explicit `--adopt-unmanaged` plus an explicit existing `--target`
  before replacing unstamped state; adopted backups are target-bound and
  relocation requires a second explicit flag.
- Rejected recognized but command-inapplicable installer flags and mutually
  exclusive apply/plan modes instead of silently ignoring user intent.
- Bounded live CLI version probing to one canonical executable, 3 seconds, and
  64 KiB. Probe failure is nonfatal advisory `unknown` for normal install and a
  strict postcondition failure for bootstrap.

### Removed

- Removed unused tracked `.gitkeep` files for the dead `build/system` and
  `cli-tools/templates` platform scaffolds.

## [2.0.0] - 2026-07-10

### Changed

- **Public implementation boundary.** This repository now contains only the
  reusable ZCode setup sources, installer, build contract, public references,
  documentation, and public security/release automation. Development agent
  context, validation, tests, and benchmarks moved to the private
  `nddev-harnesses` control plane, where this repository is pinned as a
  submodule.
- **Build version contract reduced to three authoritative files:** `VERSION`,
  `build/version.json`, and `build/manifest.json`.
- **`nddev-builder/core` 2.0.0 is a focused reusable component toolkit** with
  13 skills, 13 matching commands, and one reviewer agent.

### Removed

- Removed the five development-only plugin capabilities `add-test`,
  `run-tests`, `run-benchmarks`, `doctor`, and `release-build`, together with
  their slash commands. These workflows now belong to `nddev-harnesses`.
- Removed repository-local agent configuration, Serena state, placeholder test
  files, Python development metadata, and functional validation workflows from
  the public module.

### Fixed

- Installer and bootstrap plan modes no longer invoke the live `zcode` binary,
  create temporary download files, or report a false runtime match; runtime
  discovery is explicitly logged as skipped.
- Restore and remove errors no longer suggest that `--target` bypasses the
  mandatory `BUILD-VERSION` safety guard.
- `BUILD-VERSION.platform` now records the explicitly selected installer
  platform instead of the host returned by `uname`, so cross-platform builds
  retain the correct target provenance.
- Bootstrap now rejects unsupported explicit platform values instead of
  continuing with an incomplete platform branch.

## [1.0.9] - 2026-07-09

### Fixed
- **release-build skill: now documents all 4 build-version files.** The
  release instructions now match the version-parity test and include
  `build/manifest.json`.
- **Test-suite metadata updated to 31 tests.** The parent validation suite now
  includes a regression test for `validate_fast.sh`, covering the prior
  `pipefail`/SIGPIPE false negative.
- **Release history repaired for 1.0.3.** The missing `1.0.3` tag and GitHub
  Release now exist for commit `35077ae`.

## [1.0.8] - 2026-07-09

### Changed
- **repo-orientation skill: fully rewritten for current state.** Now documents
  the 3 marketplaces, the 18-skill nddev-builder toolkit, the 4 version files,
  the test suite location (parent repo), and the restore hardening. This is the
  skill a new agent reads FIRST — it was stale (described only 2 marketplaces
  and 0 of the builder skills).
- **AGENTS.md: rewritten for current state.** Added marketplace table, builder
  toolkit overview, test suite reference, and the 4-file version sync rule.
- **.serena/memories/INDEX-01-OVERVIEW.md: updated** with 3 marketplaces,
  18-skill toolkit, 4 version files, restore hardening facts, and test suite
  location.

## [1.0.7] - 2026-07-09

### Fixed
- **dev-workflow skill: updated to reflect current 18-skill toolkit.** Added
  test suite step (Step 3b), added pyproject.toml + manifest.json to version
  bump list, expanded "How to add new things" table from 9 to 18 entries.
- **test_version_parity.py: now checks 4 build-version files** (was 3).
  Added `build/manifest.json` build_version to the parity assertion.
- **add-agent, add-hook, add-skill, add-test skills: added validation reminders.**
  Each now ends with "validate with install --plan + run doctor + bump version".
- **doctor skill: added Step 9 (test suite reference).** Doctor is structural
  (8 axes); the test suite is behavioral (30 tests). Step 9 recommends running
  both for full quality coverage.

## [1.0.6] - 2026-07-09

### Fixed
- **release-build skill: now mentions all 3 version files.** Previously omitted
  `pyproject.toml`, which would cause a version-parity test failure on release.
- **enable-plugin skill: added worked example and empty-map note.** Clarified
  that templates ship `enabledPlugins: {}` (empty by design) and showed a
  concrete `core@nddev-builder` example.
- **add-marketplace skill: corrected validate_marketplace requirements.** The
  function requires only 5 files (AGENTS.md, marketplace.json, 3 templates);
  mcp.json and hooks.json are recommended but optional.
- **add-provider skill: corrected .env.example section heading reference.** The
  heading uses Unicode box-drawing characters; also added optional model fields
  (`limit.output`, `name`, `reasoning`).
- **nddev-native-reviewer agent: hardened review checklist.** Fixed marketplace
  version wording (per-entry, not top-level); added `version` field check;
  added 1024-char description limit check; added command filename regex check.

### Changed
- **doctor Step 1: now checks `build/manifest.json` build_version** (was stale
  at 1.0.0 while other files were at 1.0.5).
- `build/manifest.json` build_version synced to current.

## [1.0.5] - 2026-07-09

### Added
- **3 new builder skills** for test/benchmark management (15 → 18 skills):
  - `run-tests` — run the 30-test pytest suite + fast validation lane.
  - `add-test` — scaffold a new test file using established fixtures.
  - `run-benchmarks` — run installer lifecycle performance benchmarks.
- **3 new slash commands**: `/nddev-run-tests`, `/nddev-add-test`,
  `/nddev-run-benchmarks`.
- **Test suite** (30 tests) in the parent control-plane repo
  (`validation/nddev-zcode-app/`): marketplace structure (8), installer
  lifecycle (6), restore safety C1/C2/C3 (5), backup rotation (4), config
  rendering (4), version parity (3).
- **Benchmark suite** measuring install/restore/remove/plan timing.
- **Validation scripts**: `validate_fast.sh` (JSON + plan + ShellCheck, <60s),
  `validate_release.sh` (full pytest + fast lane, <300s).

### Changed
- Core plugin version 1.1.0 → 1.2.0 (minor: 3 new test/benchmark capabilities).
- Tests live in the parent repo (rldyour-ai-cli-tools/validation/), NOT inside
  the module — keeps the implementation clean and hides test internals.

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
