# Development — meta skills

This directory holds **skills for developing nddev-zcode-app itself**. These are
workspace-scope skills, read by ZCode when working inside this repository. They
are NOT shipped into `~/.zcode` by the installer — they live only here, for
editing this repo.

> **Note:** the functional equivalents already ship inside the `nddev-builder`
> marketplace `core` plugin
> (`zcode_tools/marketplaces/nddev-builder/plugins/core/skills/`). All 9 skills
> exist there: `add-plugin`, `add-skill`, `add-command`, `add-agent`, `add-hook`,
> `add-mcp-server`, `add-marketplace`, `release-build`, `doctor`.
>
> This `development/skills/` directory is reserved for future workspace-only
> meta-skills that should NOT ship to end users (e.g. internal release-ops,
> estate-sync helpers). It is currently empty.

## Existing skills (in the core plugin, not here)

| Skill | Purpose |
|---|---|
| `add-plugin` | Scaffold a self-contained plugin bundle inside a marketplace |
| `add-skill` | Author a SKILL.md (plugin- or user-scoped) |
| `add-command` | Author a slash command (commands/<name>.md) |
| `add-agent` | Author a subagent (agents/<name>.md with name + model) |
| `add-hook` | Register a lifecycle hook in hooks.json |
| `add-mcp-server` | Register a tool — classic MCP OR CLI+skill alternative |
| `add-marketplace` | Scaffold a brand-new self-contained marketplace |
| `release-build` | Bump version sources, update CHANGELOG, validate, tag |
| `doctor` | Deep consistency check (versions, ZCode-spec, stale paths, JSON, secrets) |

Each follows the Agent Skills standard: `skills/<name>/SKILL.md` with YAML
frontmatter `name` and `description`.
