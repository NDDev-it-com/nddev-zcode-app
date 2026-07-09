---
description: Register a tool integration — either a classic MCP server OR a CLI+skill alternative. Help decide which path fits.
---

Register a tool integration for the agent.

Follow the `add-mcp-server` skill exactly. First, help the user decide the path:

1. **Explain the trade-off briefly:** MCP exposes standardized tool schemas at
   session scope; CLI+skill keeps compact routing metadata in the baseline and
   loads detailed guidance/output on demand, but is less constrained. Default
   to CLI+skill for local development; use MCP for standardized cross-agent
   discovery or a deliberately constrained interface.

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
