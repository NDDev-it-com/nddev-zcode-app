---
name: repo-orientation
description: Map of the nddev-zcode-app repository — read it FIRST when starting a new session or working anywhere inside this repo. Explains the three-layer architecture, the self-contained marketplace model, the full installer lifecycle, the nddev-builder toolkit (18 skills for building marketplaces/plugins/components), where every kind of file lives, where tests live (parent repo), and the rules that keep the repo consistent. Use when unsure what a directory is for, where to add something, or how the system fits together.
---

# nddev-zcode-app — repository map

This is a **build system + installer** for ZCode, not a runtime. It recreates a
complete, version-stamped `~/.zcode` from source on macOS and Ubuntu.

**Read this skill first**, then `AGENTS.md` for the rules, then `dev-workflow`
for the daily process.

## What this repo does (in one paragraph)

The repo holds one or more **marketplaces** — each is a self-contained `~/.zcode`
setup (AGENTS.md, config templates, skills, plugins). The installer selects ONE
marketplace and builds a clean `~/.zcode` from it. It can also download and
install the ZCode app itself (bootstrap), back up and restore versions, and
switch between different setups.

## Current marketplaces (3)

| Marketplace | Purpose | Status |
|---|---|---|
| **nddev-builder** | Meta-tooling for building marketplaces, plugins, and components. Contains the `core` plugin with **18 skills, 18 commands, 1 agent** covering the full development lifecycle (create, list, modify, remove, validate, test, benchmark, release). | Complete |
| **nddev-designer** | Designer-oriented setup (placeholder scaffold). | Placeholder |
| **nddev-developer** | Developer-oriented setup for full-stack engineering (placeholder scaffold). | Placeholder |

## Repository structure

```
zcode_tools/marketplaces/<name>/   SOURCE: each marketplace = one complete ~/.zcode setup
cli-tools/                         INSTALLER: bootstrap + install + remove + restore
build/                             ARTIFACTS: version pins, secrets, manifest (shared)
.agents/skills/                    WORKSPACE SKILLS: repo-orientation + dev-workflow
config/                            CONTRACT: nddev-contract.json
references/                        BASELINE: zcode-baseline.json
docs/                              DOCS: install, architecture, secrets
.serena/                           SERENA: project config + memory
.github/                           CI: workflows, templates, branch protection
```

## What lives where (inside a marketplace)

```
zcode_tools/marketplaces/<name>/
  AGENTS.md                        → ~/.zcode/AGENTS.md
  marketplace.json                 → ~/.zcode/marketplaces/<name>/
  cli-config.template.json         → ~/.zcode/cli/config.json  (rendered: hooks.events, mcp.servers, plugins)
  v2-config.template.json          → ~/.zcode/v2/config.json   (rendered: provider defs, ${API_KEY})
  v2-setting.template.json         → ~/.zcode/v2/setting.json  (rendered: prefs, ${HOME})
  mcp.json                         → merged into cli/config.json (mcp.servers)
  hooks.json                       → merged into cli/config.json (hooks.events)
  skills/  commands/  agents/      → ~/.zcode/{skills,commands,agents}/  (user-scope)
  plugins/<plugin>/                → plugin bundles (convention-discovered)
    .zcode-plugin/plugin.json      ← metadata only (no component arrays)
    skills/<skill>/SKILL.md
    commands/<cmd>.md
    agents/<agent>.md
    references/<doc>.md
    tools/<name>/                  ← CLI tools for the CLI+skill pattern
```

## The nddev-builder toolkit (18 skills)

The `nddev-builder` marketplace's `core` plugin is the **development toolkit**.
Use these skills (via slash commands like `/nddev-add-skill`) to build and
maintain any marketplace:

| Category | Skills |
|---|---|
| **CREATE** | add-marketplace, add-plugin, add-skill, add-command, add-agent, add-hook, add-mcp-server, add-provider, add-reference, add-tool |
| **LIST** | list-components |
| **MODIFY** | enable-plugin |
| **REMOVE** | remove-component |
| **TEST** | run-tests, add-test, run-benchmarks |
| **VALIDATE** | doctor (8 structural axes + Step 9 test suite) |
| **RELEASE** | release-build |

All skills are in `zcode_tools/marketplaces/nddev-builder/plugins/core/skills/`.

## The full installer lifecycle

```bash
# 0. Download + install the ZCode app itself (from official CDN, pinned version):
cli-tools/scripts/install.sh bootstrap --apply

# 1. List available setups:
cli-tools/scripts/install.sh list

# 2. Build ~/.zcode from a marketplace:
cli-tools/scripts/install.sh install --marketplace <name> --plan
cli-tools/scripts/install.sh install --marketplace <name> --apply

# 3. Update (re-run install with same marketplace — old is backed up, state restored):
cli-tools/scripts/install.sh install --marketplace <name> --apply

# 4. Switch to a different marketplace:
cli-tools/scripts/install.sh install --marketplace <other> --apply

# 5. List backups:
cli-tools/scripts/install.sh list --backups

# 6. Restore from a backup slot:
cli-tools/scripts/install.sh restore --slot <0-9> --apply

# 7. Remove (back up + delete):
cli-tools/scripts/install.sh remove --apply
```

Target directory: `--target <dir>` or `ZCODE_TARGET` in `build/.env` (default `~/.zcode`).
Mode: `--plan` (dry-run, default) or `--apply`.

### Backup convention

- 10 slots (`0-9`), named `<N>-<VERSION>-old.zcode`.
- When all 10 are full, the oldest (by mtime) is overwritten.
- Each install/update/switch/remove backs up the current target first.

### Restore policy

- **Always restored**: `v2/credentials.json`, `v2/certs/`, `cli/agents/`, `cli/db/`, `cli/artifacts/`.
- **Never restored**: logs, crash dumps, plugin cache (regenerated by ZCode).

## Version files (keep in sync — 4 files)

The build version is tracked in **4 files** that must always agree:

- `VERSION` (root, single line)
- `build/version.json` → `build_version`
- `build/manifest.json` → `build_version`
- `pyproject.toml` → `[project]` → `version`

The core plugin version (in `marketplace.json` plugins[] entry and `plugin.json`)
is independent — it bumps only when the plugin's content changes.

ZCode runtime pins (`zcode_app_version`, `zcode_cli_version`) are in
`build/version.json` and must match `references/zcode-baseline.json`.

## Tests and benchmarks (in parent repo)

Tests live in the **parent control-plane repo** (`rldyour-ai-cli-tools`), NOT
inside this module — by design, to keep the implementation clean:

```
rldyour-ai-cli-tools/validation/nddev-zcode-app/
  conftest.py + _helpers.py        ← fixtures + helpers
  test_*.py (7 files, 31 tests)    ← pytest (marketplace structure, lifecycle,
                                      restore safety, backup rotation, config
                                      rendering, version parity, validation scripts)
  benchmarks/bench_lifecycle.py    ← performance timing
  scripts/validate_fast.sh         ← quick lane (<60s)
  scripts/validate_release.sh      ← full lane (<300s)
```

Run: `python3 -m pytest -q validation/nddev-zcode-app/ --rootdir=validation/nddev-zcode-app`

## Secrets

- `build/.env.example` — committed template (keys only, no values).
- `build/.env` — gitignored real values. Loaded by the installer at runtime.
- MCP servers get `${VAR}` rendered at install time.
- CLI tools get `~/.zcode/.env` (chmod 600, rendered from `build/.env` at install).

## Workspace skills (in `.agents/skills/`)

These are read by ZCode when working inside this repo. They are NOT shipped to
`~/.zcode` — they exist only for developing this repo.

| Skill | Purpose |
|---|---|
| `repo-orientation` (this skill) | What the repo is and how it's structured. Read FIRST. |
| `dev-workflow` | How to develop: make changes, validate, test, commit, release. |

## Where rules live

- `AGENTS.md` (repo root) — workspace rules for editing this repo.
- `marketplaces/<name>/AGENTS.md` — the system instructions installed into `~/.zcode`.
- `config/nddev-contract.json` — the product contract (format, policy refs).
- `build/manifest.json` — machine-readable layout, backup/restore policy.
- `references/zcode-baseline.json` — verified ZCode runtime baseline.
- `docs/` — install, architecture, and secrets documentation.

## ZCode native format reminders

- **Each marketplace is self-contained** — AGENTS.md and config templates live inside it.
- Plugin components are **convention-discovered** (`skills/<n>/SKILL.md`, `commands/<n>.md`,
  `agents/<n>.md`). The manifest is metadata-only.
- Hooks live under `hooks.events.<Event>` in `cli/config.json` (requires `hooks.enabled: true`;
  exactly 7 events). Config-file hooks do NOT use `hooks.<Event>` directly.
- MCP servers use `{"mcpServers":{}}` in `.mcp.json` (plugin form) or `mcp.servers` in
  `cli/config.json`. Config-file servers do NOT expand `${VAR}` — the installer does it.
- Secrets are **never committed** — only `${VAR}` placeholders.

## Key principles (timeless)

- **This repo evolves.** Marketplaces, plugins, and skills are added over time. The
  architecture scales: new marketplace = new directory, new plugin = new bundle inside it.
- **No hardcoded marketplace names in the architecture docs.** The system works for any
  marketplace, not just the current ones.
- **The installer is the only way to modify `~/.zcode`.** Never hand-edit rendered files.
- **English only** — all content, including skill descriptions.
- **Conventional-commit style** — `type(scope): description`.
