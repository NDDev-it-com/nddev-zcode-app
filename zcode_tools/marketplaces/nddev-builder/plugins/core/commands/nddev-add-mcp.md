---
description: Register a tool integration — either a classic MCP server OR a CLI+skill alternative. Help decide which path fits.
---

Register a tool integration for the agent.

Follow the `add-mcp-server` skill exactly. First, help the user decide the path:

1. **Explain the trade-off briefly:** MCP loads schemas permanently (4-32x more tokens); CLI+skill costs zero until called and is more composable. Default to CLI+skill for local-dev; MCP for cross-agent standardized tools.

2. **Path A (classic MCP):**
   - Add the server entry to `zcode_tools/marketplaces/<marketplace>/mcp.json` under `mcpServers` (stdio or http shape).
   - Add the secret key to `build/.env.example` (empty value) and `build/.env` (real, gitignored).
   - Use `${VAR}` placeholders for secrets.
   - Validate the JSON.

3. **Path B (CLI + skill):**
   - Create the tool(s) under `zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/tools/<name>/`.
   - Write a README or SKILL.md documenting the available commands, when to use each, and output format. Keep it token-thin.
   - Make scripts executable.

4. Remind to run `install --apply` to propagate (MCP servers and ~/.zcode/.env).
