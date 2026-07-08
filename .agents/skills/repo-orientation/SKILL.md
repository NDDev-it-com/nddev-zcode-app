---
name: repo-orientation
description: Map of the nddev-zcode-app repository — read it FIRST when working anywhere inside this repo. Explains the self-contained marketplace model (each marketplace = a complete ~/.zcode setup), the installer --marketplace selection, where each kind of file lives, the backup/restore contract, and the secrets policy. Use when unsure what a directory is for, where to add a skill/plugin/MCP server, or how to switch setups. RU triggers — карта репозитория, где лежит, структура репо, как устроен, что куда добавлять, маркетплейс, installer, бекап, восстановление, zcode, сборка, переключить сетап.
---

# nddev-zcode-app — repository map

`nddev-zcode-app` is **not** a runtime. It is a build system + installer that
recreates a complete, version-stamped `~/.zcode` from **one selected marketplace**
on macOS (desktop) and Ubuntu (desktop/server). Read `AGENTS.md` for rules; this
skill is the map.

## The core idea: each marketplace IS a complete setup

A marketplace is not just a plugin catalog — it is a **self-contained `~/.zcode`
build**: its own AGENTS.md, config templates, MCP/hooks, user-scope
skills/commands/agents, and plugins. The installer selects ONE marketplace and
builds a clean `~/.zcode` entirely from it. Switching setups = rebuild from a
different marketplace (the old `~/.zcode` is backed up first).

```
zcode_tools/marketplaces/<name>/        ← ONE complete setup
  AGENTS.md                             → ~/.zcode/AGENTS.md
  marketplace.json                      → ~/.zcode/marketplaces/<name>/marketplace.json
  cli-config.template.json              → ~/.zcode/cli/config.json       (rendered)
  v2-config.template.json               → ~/.zcode/v2/config.json        (rendered)
  v2-setting.template.json              → ~/.zcode/v2/setting.json       (rendered)
  mcp.json                              → reference (merged into cli/config.json)
  hooks.json                            → reference (merged into cli/config.json)
  skills/  commands/  agents/           → ~/.zcode/{skills,commands,agents}/
  plugins/<plugin>/                     → plugin bundles (convention-discovered)
```

## The three layers

| Layer | Dir | What it is |
|---|---|---|
| **Source** | `zcode_tools/marketplaces/<name>/` | one or more self-contained `~/.zcode` setups |
| **Installer** | `cli-tools/` | selects a marketplace, renders it into `~/.zcode` |
| **Artifacts** | `build/` | version, manifest, secrets templates (shared across setups) |

## Where things live

| You want to add… | Put it here (inside the marketplace) |
|---|---|
| System instructions | `marketplaces/<name>/AGENTS.md` |
| Provider definitions | `marketplaces/<name>/v2-config.template.json` |
| Desktop preferences | `marketplaces/<name>/v2-setting.template.json` |
| MCP servers | `marketplaces/<name>/mcp.json` + the secret in `build/.env.example` |
| Lifecycle hooks | `marketplaces/<name>/hooks.json` |
| A user-scope skill | `marketplaces/<name>/skills/<skill>/SKILL.md` |
| A slash command | `marketplaces/<name>/commands/<cmd>.md` |
| A subagent | `marketplaces/<name>/agents/<agent>.md` |
| A plugin | `marketplaces/<name>/plugins/<plugin>/.zcode-plugin/plugin.json` + `skills/`, `commands/`, `agents/` |
| A whole new setup | a new directory under `zcode_tools/marketplaces/<new-name>/` |
| A secret | `build/.env.example` (template, shared) → `build/.env` (gitignored real value) |
| A meta-skill (to develop THIS repo) | `development/skills/<name>/SKILL.md` |

## The installer flow

```bash
# List available setups:
cli-tools/scripts/install.sh list

# Install (plan first, then apply):
cli-tools/scripts/install.sh install --marketplace <name> --plan
cli-tools/scripts/install.sh install --marketplace <name> --apply

# Remove (back up + delete):
cli-tools/scripts/install.sh remove --apply

# Custom target directory:
cli-tools/scripts/install.sh install --marketplace <name> --target /opt/zcode --apply
```

Commands: `install` (default), `remove`, `list`. The target directory resolves as:
`--target` flag > `ZCODE_TARGET` (build/.env) > `~/.zcode`.

1. **Select** — `--marketplace <name>` picks the self-contained setup.
2. **Backup** — the target → `<backups>/<N>-<VERSION>-old.zcode` (10 slots 0-9; oldest overwritten when full).
3. **Build** — render the marketplace's config templates (secrets from `build/.env`),
   copy AGENTS.md, skills/commands/agents, and the marketplace dir itself.
4. **Stamp** — write `BUILD-VERSION` (version + platform + timestamp).
5. **Restore** — selective: always restore credentials, certs, sessions, db, artifacts;
   never restore logs, crash, plugin cache.
6. **Verify** — JSON valid, `BUILD-VERSION` present, `AGENTS.md` present.

`--plan` (default) prints every action without touching disk. `--apply` is irreversible
(wipes the target, keeps the versioned backup). `remove` refuses to delete a directory
without `BUILD-VERSION` (safety).

## Orienting yourself

```bash
# What build version / setup is installed?
cat ~/.zcode/BUILD-VERSION

# List available setups:
cli-tools/scripts/install.sh --list

# Dry-run a specific setup:
cli-tools/scripts/install.sh --marketplace nddev-builder --plan

# Read the source-of-truth contract:
cat config/nddev-contract.json
```

## Where rules live

- `AGENTS.md` (repo root) — workspace rules for editing this repo.
- `marketplaces/<name>/AGENTS.md` — the system instructions installed into `~/.zcode`.
- `.claude/CLAUDE.md` — Claude Code bridge (points at `AGENTS.md`).
- `build/manifest.json` — machine-readable source layout, backup/restore policy.
- `docs/` — install, architecture, and secrets documentation.

## ZCode native format reminders

- **Each marketplace is self-contained.** AGENTS.md and config templates live *inside*
  the marketplace, not at the `zcode_tools/` root.
- Plugin components are **convention-discovered**: `skills/<n>/SKILL.md`,
  `commands/<n>.md`, `agents/<n>.md`. The manifest is metadata-only.
- MCP servers use `{"mcpServers":{}}` in `plugins/<mcps>/.mcp.json` or the `mcp.servers`
  key in `cli/config.json`.
- Hooks need `hooks.enabled: true` in `cli/config.json`; exactly seven events are supported.
- Secrets are **never** committed — only `${VAR}` placeholders in templates, rendered from
  the gitignored `build/.env` at install time. Secrets are shared across setups (one `.env`).
