# ZCode native format reference

A condensed reference for the rules every component in this repository must follow.
Authoritative source: the `nddev-builder-orientation` skill and the built-in
`zcode-configuration-guide` / `diagnosing-plugins` skills (the ZCode runtime's own
guide), corroborated against the pinned ZCode 3.3.6 / CLI 0.15.2 engine.

## Marketplaces and plugin bundles

The repo supports **multiple marketplaces**. Each is a directory under
`zcode_tools/marketplaces/<marketplace>/` with its own root `marketplace.json` and a
`plugins/` subdir holding self-contained plugin bundles.

```
marketplaces/<marketplace>/
  marketplace.json               ← the marketplace root manifest
  plugins/
    <name>/
      .zcode-plugin/plugin.json  ← metadata only (ZCode reads this first)
      .claude-plugin/plugin.json ← optional portability fallback (see below)
      skills/<skill>/SKILL.md
      commands/<cmd>.md
      agents/<agent>.md
      .mcp.json                  ← only on the MCP transport plugin
      references/
      tools/                     ← optional CLI tools (not flattened)
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
| `dependencies` | no | `name@marketplace` strings this plugin requires |

Never add component arrays (`commands`, `skills`, `hooks`, `mcpServers`, `agents`)
or the inert fields listed below — the manifest is metadata-only and discovery is
by convention.

**Manifest search order (portability).** ZCode resolves a plugin manifest in the
order `.zcode-plugin/plugin.json` → `.claude-plugin/plugin.json` →
`.codex-plugin/plugin.json`. ZCode's plugin/marketplace/skill/command/hook formats
are the Claude Code formats with ZCode-specific runtime differences (below). To
make one bundle run in both tools, you may ship **both** `.zcode-plugin/plugin.json`
(ZCode-first) and an identical `.claude-plugin/plugin.json` (Claude Code fallback).
ZCode-only bundles need only `.zcode-plugin`.

## Component execution model (ZCode 3.3.6)

The pinned ZCode 3.3.6 runtime **executes only four plugin-manifest component
fields** — `commands`, `skills`, `hooks`, `mcpServers` — plus `agents`, which
execute only from user scope (which is why the installer flattens `agents/` into
`~/.zcode/agents/` instead of trusting a plugin.json `agents` field).

**Recorded but NOT executed** as plugin.json fields (declaring them has no
runtime effect, so never author them expecting behavior): `channels`,
`lspServers`, `outputStyles`, `settings`. The public Plugin doc lists **LSP** as a
bundleable component, but on this runtime an `lspServers` / `.lsp.json` block is
**inert** (LSP is delivered through a hook, not a native component) — there is **no
loadable LSP component**, so this toolkit ships no `add-lsp` skill by design. This
is a documented-surface-vs-executed-runtime gap; if a future pinned runtime
executes these fields, this reference and the runtime pin move together. (The
desktop `v2-setting` file this repo renders is a different surface: the ZCode app's
own settings, written to `~/.zcode/v2/`, not the inert plugin.json `settings`.)

### Plugin-root variable

The engine-verified ZCode-native plugin-root substitution is
**`${ZCODE_PLUGIN_ROOT}`** (use it in hook commands and any path that must resolve
to a plugin's installed root). `${CLAUDE_PLUGIN_ROOT}` is the Claude Code spelling
and may resolve as a compat alias, but prefer `${ZCODE_PLUGIN_ROOT}` and confirm
resolution with `devtest-plugin` before relying on it. **Caveat for this repo's
headless flatten install:** only `skills/`, `commands/`, and `agents/` are
flattened to user scope; `references/` and `tools/` are not, and a plugin-root
variable may be unset for a file-installed (non-UI) marketplace — a companion skill
should reference a tool by its absolute installed path
(`~/.zcode/marketplaces/<mp>/plugins/<plugin>/tools/...`) when in doubt.

## Skills

```
skills/<name>/SKILL.md
```

Frontmatter (ZCode-required): `name` (matches dir), `description` (English,
trigger-rich, ≤1024 chars; the first ~250 characters carry the routing weight, so
front-load a concrete "Use when …"). Body is markdown. Prefer **progressive
disclosure**: keep `SKILL.md` short and push detail into bundled scripts, `tools/`,
and `references/` loaded on demand. Extended frontmatter keys from the Claude Code
lineage (`allowed-tools`, `disable-model-invocation`, `${…SKILL_DIR}`,
`` !`cmd` `` injection) are not in ZCode's public docs — confirm with
`devtest-plugin` before depending on them.

**Loading reality (ZCode 3.3.6):** ZCode loads skills/commands/agents only from
user scope (`~/.zcode/{skills,commands,agents}`, `~/.agents/skills`), never from
`~/.zcode/marketplaces/.../plugins/`. The installer flattens each plugin's
`skills/`, `commands/`, and `agents/` into user scope; basenames must be unique
across every plugin (the flatten fails closed on a collision). Skills are invoked
by typing `$`; the first same-named skill in discovery order wins.

## Commands

```
commands/<name>.md     ← becomes /<name>
```

Frontmatter: `description` (and optional `argument-hint`, `allowed-tools`, `model`,
`skills`, `disable-noninteractive`). Nested dirs join with a **colon**:
`review/code.md` → `/review:code` (not a slash). Arguments interpolate as
`$ARGUMENTS`, `$1`, `$2`. Invoked with `/`. Built-ins include `/goal` and
`/compact`. ZCode keeps Commands and Skills distinct (unlike current Claude Code,
which is moving commands into skills).

## Agents (subagents)

```
agents/<name>.md
```

Frontmatter: `name`, `model` (`GLM-5.2`, `GLM-5-Turbo`, or "inherit"),
`description` (drives auto-selection). Built-in agents: **General-Purpose** and
**Explore** (read-only — use it for recon before writes). Invoked automatically or
explicitly with `@`. **Beta constraints (3.3.6):** user-level only, foreground,
**parallel supported but no background execution**. Plugin-bundled `agents/` are
diagnostic-only until flattened to `~/.zcode/agents/`.

## MCP servers

Two authoring modes — pick per `add-mcp-server` (standard MCP) or `add-tool`
(CLI-tool-as-alternative):

**Standard MCP.** This repo's setup-level MCP config is a **`mcp.json` at the
marketplace root** (`marketplaces/<marketplace>/mcp.json`, shape
`{"mcpServers": {}}`); the installer merges its `mcpServers` into
`~/.zcode/cli/config.json` under **`mcp.servers`** (the ZCode-native config key).
A plugin-scoped `.mcp.json` inside a plugin directory is the Claude-Code
plugin-level form, used by UI-installed plugins. See `add-mcp-server`.
Transports: **stdio** (default; `command` **must be a string**, plus `args`, `env`),
**http**/**sse** (`type` + `url`, plus `headers` for auth). `type` is inferred from
`command`/`url`. Strict rules (getting these wrong drops the server silently or
crashes the parser): `command` is a string not an array; exact field names
`env`/`headers`/`enabled`; **no unknown top-level keys**; default timeout
`timeoutMs` 30000. Remote auth uses a `headers` `Authorization` entry or **MCP
OAuth** (since 3.3.2); local MCP config can sync to an SSH remote (3.3.0). ZCode
can import MCP from Claude Code / Codex / OpenCode configs and `~/.agents/mcp.json`.
Secrets use `${VAR}` placeholders — they expand in a plugin `.mcp.json` but **not**
in `cli/config.json`, so this repo renders them from `build/.env` at install time.

**CLI-tool alternative.** A small script in `plugins/<p>/tools/<name>/` plus a
token-thin companion skill (see `add-tool`). Prefer it for local-dev token economy,
deterministic composition (pipes/loops/files), and simple process-env secrets;
prefer standard MCP for cross-agent tool discovery or a constrained permission
model.

## Hooks

Live in `~/.zcode/cli/config.json` under `hooks` (requires `hooks.enabled: true`).
The **seven** supported events: `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `PostToolUse`, `PostToolUseFailure`, `Stop`
(`SubagentStop`/`PreCompact`/`Notification`/`SessionEnd` are **not** supported).
Handler types: `type:"command"` (shell; `timeout` in **seconds**) and
`type:"process"` (no shell; `timeoutMs` in **milliseconds**; cross-platform —
prefer it). `matcher` is a **case-sensitive regex** (aliases `Task↔Agent`,
`Write/Edit↔ApplyPatch`). Stdout is a **strict schema** (`additionalContext`, or
`decision`/`reason` for `Stop`); a `Stop` block re-continues at most 3 times. Use
`${ZCODE_PLUGIN_ROOT}` to resolve a plugin-relative command.

## Marketplace

`zcode_tools/marketplaces/<name>/marketplace.json` — one root manifest per
marketplace, with `name`, `owner`, `description`, and a `plugins[]` array. Each
entry: `name`, `source`, `description`, `version`, `author`, `category`, `tags`,
`license`.

**`source` — local vs remote.** For this repo's **headless flatten install**, use a
**local** relative `source` (`./plugins/<name>`) that exists on disk — the installer
flattens local plugin dirs and cannot fetch remote ones. For **UI distribution**,
ZCode 3.3.6 also accepts remote plugins: a `source` object `{"source":"github",
"repo":"owner/repo"}`, and users can add a whole marketplace from a **GitHub repo,
Git URL, local path, or ZIP URL** through the Marketplace tab (npm is not a
supported source). See `publish-marketplace` for the distribution story and
`validate-components` for which `source` forms each path requires.

**Maturity and sync.** The plugin/marketplace system is **Beta** (introduced in
ZCode 3.2.0) and still evolving: skill sync over SSH landed in 3.2.5, MCP-config
sync in 3.3.0, and plugin + marketplace sync in 3.3.4 — relevant to multi-machine
authoring. Expect the surface to keep hardening; re-verify against the changelog
when the runtime pin advances.

## Providers (model configuration)

Rendered into `~/.zcode/v2/config.json` (see `add-provider`). ZCode 3.3.6 documents
**GLM Coding Plan (Z.ai / BigModel), Anthropic, OpenAI, OpenRouter, Moonshot,
MiniMax, Xiaomi MiMo**, and custom Anthropic/OpenAI-compatible providers. Auth is
account **OAuth** ("Continue with Z.ai / BigModel") or an **API key**. Models:
`GLM-5.2` and `GLM-5-Turbo`; Z.ai Anthropic base `https://api.z.ai/api/anthropic`,
BigModel `https://open.bigmodel.cn/api/anthropic`. Custom API-key providers must
never reuse ZCode-owned `builtin:*` identities.
