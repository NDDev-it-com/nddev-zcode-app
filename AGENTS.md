# AGENTS.md

## Purpose

`nddev-zcode-app` is a build system + installer that recreates a complete,
version-stamped `~/.zcode` from source on macOS (desktop) and Ubuntu
(desktop/server). It is **not** a runtime — it produces the `~/.zcode` directory
that the ZCode client reads.

GitHub repository: `https://github.com/NDDev-it-com/nddev-zcode-app` (`PUBLIC`).
Author: Danil Silantyev (github:rldyourmnd), CEO NDDev. License: AGPL-3.0-or-later.

## Quick orientation

**Read `.agents/skills/repo-orientation/SKILL.md` first** — it's the full
repository map. Then `.agents/skills/dev-workflow/SKILL.md` for the daily
development process.

## Current state (3 marketplaces)

| Marketplace | Purpose | Status |
|---|---|---|
| **nddev-builder** | Development toolkit (`core` plugin: 18 skills, 18 commands, 1 agent). Use this to build and maintain all other marketplaces. | Complete |
| **nddev-designer** | Designer-oriented setup (placeholder). | Placeholder |
| **nddev-developer** | Full-stack developer setup (placeholder — to be filled). | Placeholder |

## Source of truth

- `zcode_tools/marketplaces/<name>/` — each marketplace is a **self-contained
  setup** (its own AGENTS.md, config templates, mcp/hooks, skills/commands/agents,
  plugins). The installer selects ONE and builds `~/.zcode` from it.
- `cli-tools/scripts/install.sh` — the installer entry point (`--marketplace <name>`).
- `cli-tools/scripts/lib/{common,version,build}.sh` — shared installer logic.
- `cli-tools/scripts/{macos,ubuntu}/install.sh` — platform runners.
- `cli-tools/scripts/restore.sh` — selective runtime-state restore.
- `config/nddev-contract.json` — the product contract (native format, secrets
  policy, backup/restore refs).
- `references/zcode-baseline.json` — the verified ZCode runtime baseline.
- `build/version.json` + `VERSION` + `pyproject.toml` + `build/manifest.json` —
  the **4 version files** that must always agree.
- `build/.env.example` → `build/.env` (gitignored) — secrets injected at install
  (shared across all marketplaces).
- `.agents/skills/repo-orientation/` — the repository map skill (read first).
- `.claude/CLAUDE.md` — Claude Code bridge to `AGENTS.md`.

## Tests and benchmarks

Tests live in the **parent control-plane repo** (`rldyour-ai-cli-tools`), under
`validation/nddev-zcode-app/` — NOT inside this module. This keeps the
implementation clean. 31 pytest tests cover marketplace structure, installer
lifecycle, restore safety, backup rotation, config rendering, version parity,
and validation helper scripts.

Run: `python3 -m pytest -q validation/nddev-zcode-app/ --rootdir=validation/nddev-zcode-app`

## Three layers

```
zcode_tools/marketplaces/<name>/   ← SOURCE: one self-contained ~/.zcode setup each
cli-tools/                         ← INSTALLER: --marketplace <name> → ~/.zcode
build/                             ← ARTIFACTS: version, manifest, secrets (shared)
```

## ZCode native format (when adding components)

ZCode discovers plugin components **by convention**, not by manifest declaration:

- `plugins/<name>/.zcode-plugin/plugin.json` — metadata only (`name`, `version`,
  `author`, `license`, `keywords`, `dependencies[]`).
- `plugins/<name>/skills/<skill>/SKILL.md` — a skill.
- `plugins/<name>/commands/<name>.md` — a slash command.
- `plugins/<name>/agents/<name>.md` — a subagent.
- `plugins/<name>/.mcp.json` — MCP servers, shape `{"mcpServers": {...}}`.

User-scope components live under `~/.zcode/{skills,commands,agents}/` (sourced
from the selected marketplace at `zcode_tools/marketplaces/<name>/{skills,commands,agents}/`).
Hooks and the MCP server registry live in `~/.zcode/cli/config.json` under
`hooks` (`hooks.enabled: true`) and `mcp.servers`.

## The nddev-builder toolkit (18 skills)

Use the `nddev-builder` marketplace's `core` plugin to build and maintain any
marketplace. Slash commands: `/nddev-add-skill`, `/nddev-doctor`, `/nddev-release`, etc.

| Category | Skills |
|---|---|
| CREATE | add-marketplace, add-plugin, add-skill, add-command, add-agent, add-hook, add-mcp-server, add-provider, add-reference, add-tool |
| LIST | list-components |
| MODIFY | enable-plugin |
| REMOVE | remove-component |
| TEST | run-tests, add-test, run-benchmarks |
| VALIDATE | doctor |
| RELEASE | release-build |

## Rules

- English for code, docs, and commits (Conventional Commits). Sole author:
  Danil Silantyev — no co-author trailers.
- Never commit secrets. Real values live only in `build/.env` (gitignored). The
  `validate` workflow fails if any `.env` is tracked.
- To change the ZCode environment, edit the **source** in `zcode_tools/` and
  re-run the installer. Do not hand-edit a rendered `~/.zcode`.
- The installer defaults to `--plan` (dry-run). `--apply` is the irreversible
  step (it wipes and rebuilds `~/.zcode`, keeping a versioned backup).
- Bump **all 4** version files (`build/version.json`, `VERSION`, `pyproject.toml`,
  `build/manifest.json`), and update `CHANGELOG.md`, for release behavior changes.
- After any change: validate (`install --plan`), run doctor (`/nddev-doctor`),
  run tests (`/nddev-run-tests`), then release.
