# Development — meta skills

This directory holds **skills for developing nddev-zcode-app itself**. These are
workspace-scope skills, read by ZCode when working inside this repository. They
encode the repeatable workflows for adding plugins, skills, commands, agents,
hooks, and MCP servers, and for cutting a new build release.

They are NOT shipped into `~/.zcode` by the installer — they live only here, for
editing this repo.

## Planned skills

- `add-plugin` — scaffold a new self-contained plugin bundle under
  `zcode_tools/plugins/<name>/` (`.zcode-plugin/plugin.json` + convention dirs).
- `add-skill` / `add-command` / `add-agent` — add a user-scope component under
  `zcode_tools/{skills,commands,agents}/`.
- `add-mcp-server` — register a server in `zcode_tools/mcp.json` and the secret
  in `build/.env.example`.
- `release-build` — bump `build/version.json` + `VERSION`, update `CHANGELOG.md`,
  and run the installer `--plan` to validate before commit.

Each skill follows the Agent Skills standard: `skills/<name>/SKILL.md` with a
YAML frontmatter `name` and Russian-first `description` trigger.
