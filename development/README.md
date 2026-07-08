# Development — meta skills

This directory holds **skills for developing nddev-zcode-app itself**. These are
workspace-scope skills, read by ZCode when working inside this repository. They
encode the repeatable workflows for adding plugins, skills, commands, agents,
hooks, and MCP servers, and for cutting a new build release.

They are NOT shipped into `~/.zcode` by the installer — they live only here, for
editing this repo.

> **Note:** the equivalent functional skills already ship inside the
> `nddev-builder` marketplace `core` plugin
> (`zcode_tools/marketplaces/nddev-builder/plugins/core/skills/`). The skills
> below are a planned superset for this workspace. Only `add-plugin`, `add-skill`,
> and `release-build` exist today (in the plugin); the rest are placeholders.

## Planned skills (workspace-scope, for editing THIS repo)

- `add-plugin` — scaffold a new self-contained plugin bundle inside a marketplace
  under `zcode_tools/marketplaces/<marketplace>/plugins/<name>/`.
- `add-skill` / `add-command` / `add-agent` — add a user-scope component inside
  the active marketplace: `zcode_tools/marketplaces/<marketplace>/{skills,commands,agents}/`.
- `add-mcp-server` — register a server in the active marketplace's `mcp.json` and
  the secret in `build/.env.example`.
- `release-build` — bump `build/version.json` + `VERSION`, update `CHANGELOG.md`,
  and run the installer `install --plan` to validate before commit.

Each skill follows the Agent Skills standard: `skills/<name>/SKILL.md` with a
YAML frontmatter `name` and `description`.
