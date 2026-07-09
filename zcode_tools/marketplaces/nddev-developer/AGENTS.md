# Global Agent Instructions

<!-- nddev-developer:begin -->
# ZCode environment — nddev-developer

This ~/.zcode directory is produced by nddev-zcode-app
(NDDev-it-com/nddev-zcode-app) from the `nddev-developer` marketplace — a
developer-oriented setup for full-stack engineering and writing any code.
Currently a placeholder scaffold; to be filled with full-stack development
plugins, skills, and tooling.

## What lives here
- AGENTS.md — this file. User-scope default instructions for every ZCode workspace.
- skills/, commands/, agents/ — user-scope skills, slash commands, and subagents
  (currently empty — fill deliberately).
- marketplace.json — the local nddev-developer plugin marketplace.
- plugins/ — self-contained plugin bundles (currently empty).
- cli/config.json — plugin enable/disable state, hooks (`hooks.enabled: true`),
  and MCP servers (`mcp.servers`).
- v2/ — desktop-app state: provider definitions (config.json), preferences
  (setting.json), and credentials (credentials.json, restored from backup —
  never committed).

## Operating rules
- English for code, docs, and commits (Conventional Commits). Sole author:
  Danil Silantyev — no co-author trailers.
- Plugins are convention-discovered: `skills/<name>/SKILL.md`,
  `commands/<name>.md`, `agents/<name>.md`. MCP centralized in
  `plugins/<mcps>/.mcp.json` with `{"mcpServers":{}}`.
- Secrets never live in this tree — rendered from `build/.env` (gitignored) at
  install time. `credentials.json` restored from backup, not templated.
- To change this environment, edit the SOURCE in `zcode_tools/` and re-run the
  installer. Do not hand-edit rendered `~/.zcode` files.
<!-- nddev-developer:end -->
