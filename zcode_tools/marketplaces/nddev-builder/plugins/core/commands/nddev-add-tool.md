---
description: Add a CLI tool (non-MCP) to a plugin — creates a script + README + optional companion skill. The CLI+skill alternative to MCP servers.
---

Add a CLI tool to a plugin.

Follow the `add-tool` skill exactly:

1. Ask the user for: the marketplace name, the plugin name, the tool name, the script language (bash/python/node), and a one-sentence description.
2. Create `plugins/<plugin>/tools/<name>/` with the executable script and a README.
3. Optionally create a companion skill (`skills/<name>/SKILL.md`) that teaches the agent when and how to invoke the tool.
4. If the tool needs secrets, declare the key with an empty value in
   `build/.env.example` and accept it through the active project's approved
   process environment. Never `source`, `.`, or `eval` an env file.
5. Make the script executable (`chmod +x`).
6. Run `install --plan` to confirm nothing broke.
