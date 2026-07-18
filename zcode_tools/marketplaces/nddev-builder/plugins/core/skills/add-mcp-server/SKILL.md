---
name: add-mcp-server
description: Register a tool integration for the agent — either a classic MCP server OR a CLI+skill alternative. Covers the MCP vs CLI trade-off (token cost, composability), both registration paths, and secrets handling. Use when adding any external tool, API, or data source the agent should be able to call.
---

# add-mcp-server

Registers a tool integration. **Two paths exist** — choose based on the trade-off.

## Path A (classic MCP) vs Path B (CLI + skill) — the decision

MCP servers expose tool schemas to the agent's session context. The exact
context footprint depends on the client and server surface, and results also
pass through the model context. This standardized interface is useful, but a
large tool catalog can create a larger permanent context surface.

CLI tools plus a concise skill or README keep baseline routing metadata small;
the detailed skill body, command help, and tool output are loaded only when
needed. The agent can compose loops, pipes, and scripts, but the shell surface
is less constrained than MCP.

| Dimension | MCP server | CLI + skill |
| --- | --- | --- |
| Context footprint | Session tool schemas | Small metadata; detail on demand |
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

```text
zcode_tools/marketplaces/<marketplace>/mcp.json
```

The installer merges `mcp.json` → `cli/config.json` under `mcp.servers` at install
time.

### Entry shapes

stdio server (`command` is a **string**, NOT an array — OpenCode-style arrays crash):

```json
{
  "mcpServers": {
    "<name>": {
      "command": "uvx",
      "args": ["some-mcp-server@1.2.3"],
      "env": { "API_KEY": "${API_KEY}" },
      "cwd": "/path/to/dir",
      "timeoutMs": 60000
    }
  }
}
```

http server:

```json
{
  "mcpServers": {
    "<name>": { "url": "https://...", "headers": {}, "timeoutMs": 30000 }
  }
}
```

### Strict schema rules (violations silently drop the server)

- **`command` MUST be a string** (not an array). `command: ["npx", "..."]` crashes
  Settings with `command.trim is not a function`.
- Field names: `env` (not `environment`), `headers` (not `http_headers`),
  `enabled` (not `enable`). Wrong names → zero tools registered.
- **Unknown top-level keys are NOT tolerated** — the schema is strict. An extra
  key drops the entire server.
- `type` is optional — inferred from `command` (→ stdio) or `url` (→ http).
- Default timeout: **30000 ms**. Use `timeoutMs` to override.

### Secrets and `${VAR}` expansion — important limitation

**Template `${...}` expansion is PLUGIN-ONLY.** Our installer merges `mcp.json`
into `cli/config.json` (a configuration file), where `${...}` is **NOT expanded**
by ZCode — it reaches the process literally. This is why **our installer does the
substitution at render time** (it reads `build/.env` and replaces `${VAR}` before
writing `cli/config.json`). So `${VAR}` placeholders work in our setup because
the installer resolves them, not ZCode.

For reference (if editing `cli/config.json` directly, bypassing the installer):
config-file servers do NOT expand `${...}` — use absolute values or env vars
read by the server process itself. Plugin `.mcp.json` servers (inside a plugin
directory) DO expand `${CLAUDE_PLUGIN_ROOT}`, `${ZCODE_PROJECT_DIR}`, etc.

Add the matching `VAR=` key (empty) to `build/.env.example` (committed) and
`build/.env` (gitignored real value).

## Path B: CLI + skill (the lean alternative)

Instead of an MCP server, create a small CLI tool (a shell or node script) plus
a skill (or README) that documents how the agent calls it. Compact metadata
supports routing; the detailed skill body and tool output are consumed on
demand.

### Layout

CLI tools live **inside the plugin** in a `tools/` directory. The installer
copies the whole marketplace (including plugins) into `~/.zcode/marketplaces/`,
so tools arrive there — but `tools/` is **not** flattened to user scope, and
`${CLAUDE_PLUGIN_ROOT}` is unset for a file-installed marketplace. At runtime the
companion skill must reference the tool by its **absolute installed path**,
`~/.zcode/marketplaces/<mp>/plugins/<plugin>/tools/<name>/<script>`.

```text
zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/
  tools/<name>/                   ← the CLI tool(s)
    README.md                     ← how to call them (the agent reads this)
    <tool>.sh | <tool>.js
  skills/<skill>/SKILL.md         ← skill that triggers and documents the tool
```

### Secrets at runtime

Pass CLI-tool secrets through the process environment. Prefer the active
project's existing launcher, secrets manager, or environment-loading helper so
ownership, allowlisting, and redaction stay centralized.

The installed `~/.zcode/.env` is sensitive data, not a shell script. A tool
must never execute it with `source`, `.`, or `eval`. If a project deliberately
supports reading that file, use its provided non-evaluating parser and accept
only explicitly allowlisted keys. Never print the file or inherited secret
values in help output, traces, errors, or diagnostics.

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

This pattern keeps permanent routing text compact while leaving detailed
command guidance available on demand.

## Procedure (both paths)

1. **Decide the path** (MCP vs CLI+skill) using the trade-off above. If unsure,
   default to CLI+skill for local-dev; MCP for cross-agent standardized tools.
2. **Path A (MCP):** add the server entry to `mcp.json`, add the secret key to
   `build/.env.example`, validate the JSON.
3. **Path B (CLI+skill):** create the tool(s) under `plugins/<plugin>/tools/<name>/`,
   write a README or SKILL.md documenting the commands, make scripts executable.
4. **Secrets:** never commit real values. Use `${VAR}` for installer-rendered
   MCP configuration. For CLI tools, accept an explicit process environment
   supplied by the project's approved launcher or secrets helper. Add each
   supported key to `build/.env.example` without a value.
5. Remind to run `install --apply` to propagate (MCP servers and ~/.zcode/.env).

## Rules

- English only.
- Secrets are never committed, shell-sourced, printed, or embedded in examples.
  Use `${VAR}` placeholders for rendered MCP config and an approved process
  environment for CLI tools.
- Prefer CLI+skill for token efficiency unless MCP's constrained model is needed.
- Document CLI tools with a README or skill so the agent discovers them on demand.
