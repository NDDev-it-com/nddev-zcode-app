# Development — workspace meta-skills

This directory documents the **workspace-scope skills** for developing this repo.
These skills are NOT shipped into `~/.zcode` — they exist only here, read by the
agent when working inside this repository.

## Workspace skills (in `.agents/skills/`)

These are discovered by ZCode when the working directory is inside this repo.
Read them at the start of a new session:

| Skill | Location | Purpose |
|---|---|---|
| `repo-orientation` | `.agents/skills/repo-orientation/` | The repository map — read FIRST. Explains the three-layer architecture, self-contained marketplace model, full installer lifecycle, where things live, and the timeless principles. |
| `dev-workflow` | `.agents/skills/dev-workflow/` | The daily workflow — how to make changes, validate, test in temp dirs, commit, and release. Includes the "how to add X" routing table. |

## Builder skills (in the nddev-builder core plugin)

These ship to end users inside the `nddev-builder` marketplace `core` plugin.
They are the tools for building ZCode components:

| Skill | Purpose |
|---|---|
| `add-plugin` | Scaffold a plugin bundle inside a marketplace |
| `add-skill` | Author a SKILL.md |
| `add-command` | Author a slash command |
| `add-agent` | Author a subagent |
| `add-hook` | Register a lifecycle hook |
| `add-mcp-server` | Register a tool (MCP or CLI+skill) |
| `add-marketplace` | Scaffold a new marketplace |
| `release-build` | Bump version, CHANGELOG, tag |
| `doctor` | Deep consistency check |

Location: `zcode_tools/marketplaces/nddev-builder/plugins/core/skills/`.

## This directory

`development/skills/` is reserved for future workspace-only meta-skills that are
too specific for the general `.agents/skills/` location (e.g. internal release-ops,
estate integration helpers). Currently empty.
