# AGENTS.md

## Purpose

`nddev-zcode-app` is a build system + installer that recreates a complete,
version-stamped `~/.zcode` from source on macOS (desktop) and Ubuntu
(desktop/server). It is **not** a runtime — it produces the `~/.zcode` directory
that the ZCode client reads.

GitHub repository: `https://github.com/NDDev-it-com/nddev-zcode-app` (`PRIVATE`).
Author: Danil Silantyev (github:rldyourmnd), CEO NDDev. License: AGPL-3.0-or-later.

## Source of truth

- `zcode_tools/` — the source of the complete `~/.zcode`. Edit here; the
  installer renders it into `~/.zcode`.
- `cli-tools/scripts/install.sh` — the installer entry point.
- `cli-tools/scripts/lib/{common,version,build}.sh` — shared installer logic.
- `cli-tools/scripts/{macos,ubuntu}/install.sh` — platform runners.
- `cli-tools/scripts/restore.sh` — selective runtime-state restore.
- `build/version.json` — the build version and ZCode runtime baseline.
- `build/manifest.json` — source layout, backup policy, restore policy.
- `build/.env.example` → `build/.env` (gitignored) — secrets injected at install.

## Three layers

```
zcode_tools/   ← SOURCE: the complete desired ~/.zcode as editable files
cli-tools/     ← INSTALLER: renders zcode_tools/ into ~/.zcode (macOS + Ubuntu)
build/         ← ARTIFACTS: version, manifest, system files, secrets templates
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
from `zcode_tools/{skills,commands,agents}/`). Hooks and the MCP server registry
live in `~/.zcode/cli/config.json` under `hooks` (`hooks.enabled: true`) and
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
