# ZCode native format reference

A condensed reference for the rules every component in this repository must follow.
Authoritative source: the `nddev-builder-orientation` skill and the built-in
`zcode-configuration-guide` / `diagnosing-plugins` skills (the ZCode runtime's own guide).

## Marketplaces and plugin bundles

The repo supports **multiple marketplaces**. Each is a directory under
`zcode_tools/marketplaces/<marketplace>/` with its own root `marketplace.json` and a
`plugins/` subdir holding self-contained plugin bundles.

```
marketplaces/<marketplace>/
  marketplace.json               ← the marketplace root manifest
  plugins/
    <name>/
      .zcode-plugin/plugin.json  ← metadata only
      skills/<skill>/SKILL.md
      commands/<cmd>.md
      agents/<agent>.md
      .mcp.json                  ← only on the MCP transport plugin
      references/
      README.md
```

### Manifest fields (`plugin.json`)

| Field | Required | Notes |
|---|---|---|
| `name` | yes | matches `^[a-z0-9][a-z0-9._-]{0,127}$` |
| `version` | yes | SemVer, matches the marketplace entry |
| `description` | yes | English, one sentence |
| `author` | yes | `{name, url}` |
| `license` | yes | `AGPL-3.0-or-later` |
| `homepage` | no | plugin path in the repo |
| `repository` | no | the GitHub repo URL |
| `keywords` | no | English tags |
| `dependencies` | no | other plugin names this one requires |

Never add component arrays (`commands`, `skills`, `hooks`, `mcpServers`, `agents`)
or the inert fields listed below — the manifest is metadata-only and discovery is
by convention.

## Component execution model (ZCode 3.3.6)

The pinned ZCode 3.3.6 runtime **executes only four plugin-manifest component
fields** — `commands`, `skills`, `hooks`, `mcpServers` — plus `agents`, which
execute only from user scope (which is why the installer flattens `agents/` into
`~/.zcode/agents/` instead of trusting a plugin.json `agents` field).

**Recorded but NOT executed** as plugin.json fields (declaring them has no
runtime effect, so never author them expecting behavior): `channels`,
`lspServers`, `outputStyles`, `settings`. In particular an
`lspServers` / `.lsp.json` block is **inert** on this runtime — there is **no
loadable LSP component**, so this toolkit ships no `add-lsp` skill by design.
(The desktop `v2-setting` file this repo renders is a different surface: it is
the ZCode app's own settings, written directly to `~/.zcode/v2/`, not the inert
plugin.json `settings` field.) If a future pinned runtime executes these fields,
this reference and the runtime pin move together.

Authoritative source: the built-in `zcode-guide` plugin
(`zcode-configuration-guide`, `diagnosing-plugins`).

## Skills

```
skills/<name>/SKILL.md
```

Frontmatter: `name` (matches dir), `description` (English, trigger-rich). Body is markdown.
The first same-named skill in discovery order wins (user > workspace > plugin).

**Loading reality (ZCode 3.3.6):** ZCode loads skills/commands/agents only from
user scope (`~/.zcode/{skills,commands,agents}`, `~/.agents/skills`), never from
`~/.zcode/marketplaces/.../plugins/`. The installer flattens each plugin's
`skills/`, `commands/`, and `agents/` into user scope; basenames must be unique
across every plugin (the flatten fails closed on a collision). `references/` and
`tools/` are not flattened.

## Commands

```
commands/<name>.md     ← becomes /<name>
```

Frontmatter: `description`. Nested dirs join with a colon: `review/code.md` → `/review:code`.

## Agents

```
agents/<name>.md
```

Frontmatter: `name`, `model` (e.g. `GLM-5.2`).

## MCP servers

Centralized in ONE file per MCP transport plugin:
`marketplaces/<marketplace>/plugins/<mcps>/.mcp.json`, shape `{"mcpServers": {}}`.
Each entry is either:

- stdio: `{"command": "...", "args": [...], "env": {...}}`
- http: `{"type": "http", "url": "..."}`

Secrets use `${VAR}` placeholders, rendered from `build/.env` at install time.

## Hooks

Live in `~/.zcode/cli/config.json` under `hooks` (requires `hooks.enabled: true`). The
seven supported events: `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `PostToolUse`, `PostToolUseFailure`, `Stop`.

## Marketplace

`zcode_tools/marketplaces/<name>/marketplace.json` — one root manifest per marketplace,
with `name`, `owner`, `description`, and a
`plugins[]` array. Each entry: `name`, `source` (relative `./plugins/<name>`),
`description`, `version`, `author`, `category`, `tags`, `license`.
