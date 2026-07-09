---
description: List all plugins, skills, commands, agents, hooks, and MCP servers in a marketplace. Read-only inventory.
---

List the components of a marketplace.

Follow the `list-components` skill exactly:

1. Ask the user for the marketplace name (or use the active one).
2. Read `marketplace.json` and list registered plugins.
3. Scan the directory tree for skills, commands, agents, references, tools, hooks, and MCP servers.
4. Print a summary table with counts and paths.
