# AGENTS.md

## Purpose

`nddev-zcode-app` is a build system + installer that recreates a complete,
version-stamped `~/.zcode` from source on macOS (desktop) and Ubuntu
(desktop/server). It is **not** a runtime — it produces the `~/.zcode` directory
that the ZCode client reads.

GitHub repository: `https://github.com/NDDev-it-com/nddev-zcode-app` (`PRIVATE`).
Author: Danil Silantyev (github:rldyourmnd), CEO NDDev. License: AGPL-3.0-or-later.

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
- `build/version.json` — the build version and ZCode runtime baseline.
- `build/manifest.json` — source layout, backup policy, restore policy.
- `build/.env.example` → `build/.env` (gitignored) — secrets injected at install
  (shared across all marketplaces).
- `.serena/` — Serena project config and durable project memory (memories/).
- `.agents/skills/repo-orientation/` — the repository map skill (read first).
- `.claude/CLAUDE.md` — Claude Code bridge to `AGENTS.md`.

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
`hooks` (`hooks.enabled: true`) and
`mcp.servers`.

## Rules

- English for code, docs, and commits (Conventional Commits). Sole author:
  Danil Silantyev — no co-author trailers.
- Never commit secrets. Real values live only in `build/.env` (gitignored). The
  `validate` workflow fails if any `.env` is tracked.
- To change the ZCode environment, edit the **source** in `zcode_tools/` and
  re-run the installer. Do not hand-edit a rendered `~/.zcode`.
- The installer defaults to `--plan` (dry-run). `--apply` is the irreversible
  step (it wipes and rebuilds `~/.zcode`, keeping a versioned backup).
- Bump `build/version.json` and `VERSION`, and update `CHANGELOG.md`, for release
  behavior changes.
