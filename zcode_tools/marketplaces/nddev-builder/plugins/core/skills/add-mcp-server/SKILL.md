---
name: add-mcp-server
description: Register a tool integration for the agent — either a classic MCP server OR a CLI+skill alternative. Covers the MCP vs CLI trade-off (token cost, composability), both registration paths, and secrets handling. Use when adding any external tool, API, or data source the agent should be able to call.
---

# add-mcp-server

Registers a tool integration. **Two paths exist** — choose based on the trade-off.

## Path A (classic MCP) vs Path B (CLI + skill) — the decision

MCP servers load their full tool schema into the agent's context **permanently**
(every session). Research and practice show this costs **4–32× more tokens** than
CLI tools for the same task. MCP schemas are also hard to extend and not
composable (results must pass through the context window).

CLI tools + a skill (or README) cost **zero tokens until invoked**. The agent
writes loops, pipes, and scripts — composable, cheap, easy to modify. The
trade-off: CLI is less constrained (the agent can do anything the shell allows).

| Dimension | MCP server | CLI + skill |
|---|---|---|
| Token cost | High (schema always loaded) | Zero until called |
| Composability | Low (results through context) | High (pipes, files, loops) |
| Safety | More constrained | Less constrained |
| Best for | Standardized discovery, cross-agent | Local dev, token efficiency |

**Rule of thumb:** prefer **CLI + skill** for local-dev and token-sensitive
workflows. Use **MCP** only when you need standardized tool discovery across
multiple agents/harnesses, or the tool genuinely benefits from a constrained
permission model.

## Path A: classic MCP server

### Where

Register in the active marketplace's `mcp.json`:

```
zcode_tools/marketplaces/<marketplace>/mcp.json
```

The installer merges `mcp.json` → `cli/config.json` under `mcp.servers` at install
time.

### Entry shapes

stdio server:
```json
{
  "mcpServers": {
    "<name>": {
      "command": "uvx",
      "args": ["some-mcp-server@1.2.3"],
      "env": { "API_KEY": "${API_KEY}" }
    }
  }
}
```

http server:
```json
{
  "mcpServers": {
    "<name>": { "type": "http", "url": "https://..." }
  }
}
```

### Secrets

Secrets use `${VAR}` placeholders. Add the matching `VAR=` key (empty) to
`build/.env.example` (committed template) and `build/.env` (gitignored real
value). The installer substitutes at render time.

## Path B: CLI + skill (the lean alternative)

Instead of an MCP server, create a small CLI tool (a shell or node script) plus
a skill (or README) that documents how the agent calls it. The agent discovers
the tool by reading the skill on demand — zero context cost until used.

### Layout

```
zcode_tools/marketplaces/<marketplace>/
  scripts/<name>/             ← the CLI tool(s)
    README.md                 ← how to call them (the agent reads this)
    <tool>.sh | <tool>.js
  plugins/<plugin>/skills/<name>/SKILL.md   ← optional: auto-triggering skill
```

### What the skill/README must contain

- The available commands (one-liner each with flags).
- When to use each.
- Examples (start, navigate, query, screenshot — whatever the tool does).
- Output format (so the agent knows what to expect).

Keep it **token-thin**: a handful of commands, short descriptions. The agent
already knows how to write Bash/code — lean on that.

### Example (browser tools pattern)

```markdown
# Browser Tools

Minimal CDP tools for site exploration.

## Start
./scripts/browser/start.js [--profile]

## Navigate
./scripts/browser/nav.js <url> [--new]

## Evaluate JS
./scripts/browser/eval.js 'document.title'

## Screenshot
./scripts/browser/screenshot.js
```

This README is ~225 tokens vs 13–18k for an MCP server covering the same surface.

## Procedure (both paths)

1. **Decide the path** (MCP vs CLI+skill) using the trade-off above. If unsure,
   default to CLI+skill for local-dev; MCP for cross-agent standardized tools.
2. **Path A (MCP):** add the server entry to `mcp.json`, add the secret key to
   `build/.env.example`, validate the JSON.
3. **Path B (CLI+skill):** create the script(s) under `scripts/<name>/`, write a
   README or SKILL.md documenting the commands, make scripts executable.
4. **Secrets:** never commit real values. Use `${VAR}` (MCP) or env vars read by
   the script (CLI). Add the key to `build/.env.example`.
5. Remind to run `install --apply` to propagate (MCP) or note the script paths (CLI).

## Rules

- English only.
- Secrets never committed — `${VAR}` placeholders + `build/.env` (gitignored).
- Prefer CLI+skill for token efficiency unless MCP's constrained model is needed.
- Document CLI tools with a README or skill so the agent discovers them on demand.
