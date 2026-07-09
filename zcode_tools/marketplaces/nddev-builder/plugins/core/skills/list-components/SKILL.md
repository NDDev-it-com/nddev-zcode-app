---
name: list-components
description: List all plugins, skills, commands, agents, hooks, and MCP servers in a marketplace. Scans the directory tree and reads marketplace.json to report counts and paths. Read-only — no file changes. Use when you need to see what a marketplace contains, inspect its structure, or check what components exist before adding or removing one.
---

# list-components

Lists every component in a marketplace. Read-only inventory.

## Procedure

1. Ask the user for the marketplace name (or use the active one). Confirm the
   directory exists: `zcode_tools/marketplaces/<name>/`.

2. Read `marketplace.json` and list registered plugins:
   ```bash
   python3 -c "import json; d=json.load(open('zcode_tools/marketplaces/<name>/marketplace.json')); [print(f'  plugin: {p[\"name\"]} v{p[\"version\"]} — {p[\"description\"]}') for p in d.get('plugins',[])]"
   ```

3. Scan the directory tree and report counts:
   - **Plugins**: `zcode_tools/marketplaces/<name>/plugins/*/` (each with
     `.zcode-plugin/plugin.json`).
   - **Skills** (plugin-scoped): `plugins/*/skills/*/SKILL.md`.
   - **Skills** (user-scoped): `skills/*/SKILL.md`.
   - **Commands**: `plugins/*/commands/*.md` and `commands/*.md`.
   - **Agents**: `plugins/*/agents/*.md` and `agents/*.md`.
   - **References**: `plugins/*/references/*.md`.
   - **CLI tools**: `plugins/*/tools/*/`.
   - **Hooks**: read `hooks.json` and list non-empty event arrays.
   - **MCP servers**: read `mcp.json` and list entries under `mcpServers`.
   - **Providers**: read `v2-config.template.json` and list entries under
     `provider` (with `enabled` status).

4. Print a summary table:
   ```
   Marketplace: <name>
   Plugins:     N  (names)
   Skills:      N  (plugin-scoped: X, user-scoped: Y)
   Commands:    N
   Agents:      N
   References:  N
   CLI tools:   N
   Hooks:       N active (events: ...)
   MCP servers: N
   Providers:   N (enabled: X, disabled: Y)
   ```

5. If a component type has zero entries, report "(none)" — do not omit it.

## Rules

- Read-only: do not create, edit, or delete any file.
- Report exact paths so the user can act on them.
- For hooks and MCP servers, only list non-empty entries (skip the empty
  skeleton arrays present in every marketplace template).
