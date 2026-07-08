---
name: repo-orientation
description: Map of the nddev-zcode-app repository — read it FIRST when working anywhere inside this repo. Explains the three-layer build model (zcode_tools source → cli-tools installer → build artifacts), where each kind of file lives, the backup/restore contract, and the secrets policy. Use when unsure what a directory is for, where to add a skill/plugin/MCP server, or how the installer flows. RU triggers — карта репозитория, где лежит, структура репо, как устроен, что куда добавлять, installer, бекап, восстановление, zcode, сборка.
---

# nddev-zcode-app — repository map

`nddev-zcode-app` is **not** a runtime. It is a build system + installer that
recreates a complete, version-stamped `~/.zcode` from source on macOS (desktop)
and Ubuntu (desktop/server). Read `AGENTS.md` for rules; this skill is the map.

## The three layers

| Layer | Dir | What it is | Git nature |
|---|---|---|---|
| **Source** | `zcode_tools/` | the complete desired `~/.zcode` as editable files | tracked source |
| **Installer** | `cli-tools/` | renders `zcode_tools/` into `~/.zcode` (macOS + Ubuntu) | tracked source |
| **Artifacts** | `build/` | version, manifest, system files, secrets templates | tracked + gitignored `.env` |

Everything else (`docs/`, `development/`, `tests/`, `.github/`) supports these three.

## Where things live

| You want to add… | Put it here |
|---|---|
| A user-scope skill | `zcode_tools/skills/<name>/SKILL.md` |
| A slash command | `zcode_tools/commands/<name>.md` |
| A subagent | `zcode_tools/agents/<name>.md` |
| A marketplace | `zcode_tools/marketplaces/<marketplace>/marketplace.json` (one dir per marketplace) |
| A plugin (inside a marketplace) | `zcode_tools/marketplaces/<marketplace>/plugins/<name>/.zcode-plugin/plugin.json` + `skills/`, `commands/`, `agents/` |
| An MCP server | `zcode_tools/mcp.json` (`{"mcpServers":{}}`) + the secret in `build/.env.example` |
| A lifecycle hook | `zcode_tools/hooks.json` (merged into `cli/config.json` under `hooks`) |
| Provider definitions | `zcode_tools/v2-config.template.json` |
| Desktop preferences | `zcode_tools/v2-setting.template.json` |
| A secret | `build/.env.example` (template) → `build/.env` (gitignored real value) |
| A meta-skill (to develop THIS repo) | `development/skills/<name>/SKILL.md` |

## The installer flow

```
cli-tools/scripts/install.sh --platform macos|ubuntu [--apply|--plan]
```

1. **Backup** — `~/.zcode` → `~/.zcode-backups/<N>-<DD.MM.YYYY>-<VERSION>-old.zcode`
   (N = 1–9 rotation slot; VERSION = the build being backed up).
2. **Build** — render `zcode_tools/` into a clean `~/.zcode` (secrets from `build/.env`).
3. **Stamp** — write `~/.zcode/BUILD-VERSION` (version + platform + timestamp).
4. **Restore** — selective: always restore credentials, certs, sessions, db, artifacts;
   never restore logs, crash, plugin cache (ZCode regenerates those).
5. **Verify** — JSON valid, `BUILD-VERSION` present, `AGENTS.md` present.

`--plan` (default) prints every action without touching disk. `--apply` is irreversible
(wipes `~/.zcode`, keeps the versioned backup).

## Orienting yourself

```bash
# What build version is installed?
cat ~/.zcode/BUILD-VERSION

# Dry-run the installer against the current ~/.zcode:
cli-tools/scripts/install.sh --plan

# Read the source-of-truth contract:
cat config/nddev-contract.json
```

## Where rules live

- `AGENTS.md` — workspace rules for editing this repo (the source of truth for agents).
- `.claude/CLAUDE.md` — Claude Code bridge (points at `AGENTS.md`).
- `build/manifest.json` — machine-readable source layout, backup policy, restore policy.
- `build/version.json` — the build version and ZCode runtime baseline.
- `docs/` — install, architecture, and secrets documentation.

## ZCode native format reminders

- **Multiple marketplaces are supported.** Each lives in its own directory under
  `zcode_tools/marketplaces/<name>/` with a root `marketplace.json` and a `plugins/` subdir.
  The installer copies all of them into `~/.zcode/marketplaces/`.
- Plugin components are **convention-discovered**: `skills/<n>/SKILL.md`,
  `commands/<n>.md`, `agents/<n>.md`. The manifest is metadata-only.
- MCP servers use `{"mcpServers":{}}` in `plugins/<mcps>/.mcp.json` or the `mcp.servers`
  key in `cli/config.json`.
- Hooks need `hooks.enabled: true` in `cli/config.json`; exactly seven events are supported.
- Secrets are **never** committed — only `${VAR}` placeholders in templates, rendered from
  the gitignored `build/.env` at install time.
