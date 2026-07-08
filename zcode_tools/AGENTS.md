# Global Agent Instructions

<!-- nddev-zcode-app:begin -->
# ZCode environment — nddev-zcode-app

This `~/.zcode` directory is produced by **nddev-zcode-app** (`NDDev-it-com/nddev-zcode-app`),
a build system + installer that recreates a complete, version-stamped ZCode environment from
source on macOS (desktop) and Ubuntu (desktop/server).

## What lives here

- `AGENTS.md` — this file. User-scope default instructions for every ZCode workspace.
- `skills/`, `commands/`, `agents/` — user-scope skills, slash commands, and subagents.
- `marketplace.json` — the local `nddev` plugin marketplace (installed via Discover → local directory).
- `plugins/` — self-contained plugin bundles (`<name>/.zcode-plugin/plugin.json` + `skills/`,
  `commands/`, `agents/`, `.mcp.json`).
- `cli/config.json` — plugin enable/disable state, hooks (`hooks.enabled: true`), and MCP servers
  (`mcp.servers`).
- `v2/` — desktop-app state: provider definitions (`config.json`), preferences (`setting.json`),
  and credentials (`credentials.json`, restored from backup — never committed to the repo).

## Operating rules

- English for code, docs, and commits (Conventional Commits). Sole author: Danil Silantyev.
- Plugins are convention-discovered: `skills/<name>/SKILL.md`, `commands/<name>.md`,
  `agents/<name>.md`. MCP is centralized in `plugins/<mcps>/.mcp.json` with `{"mcpServers":{}}`.
- Secrets never live in this tree — they are rendered from `build/.env` (gitignored) at install
  time. `credentials.json` is restored from the backup, not templated.
- To change this environment, edit the **source** in the `zcode_tools/` directory of the
  nddev-zcode-app repo and re-run the installer — do not hand-edit the rendered files here.
<!-- nddev-zcode-app:end -->
