---
name: nddev-builder-orientation
description: Orients you in the nddev-builder toolkit and in how ZCode 3.3.6 discovers and loads extensions. Use when asking how nddev-builder is structured, how ZCode loads skills/commands/agents, where components go and why, why an installed skill is not loading, what the installer does (flatten to user scope), or the install/remove/switch lifecycle. Read this first before authoring or debugging a marketplace.
---

# nddev-builder orientation

The single map for this toolkit: how it is laid out, **how ZCode 3.3.6 actually
loads extensions**, what the installer does, and where every component ends up
and why. Read this before `add-*`, and whenever a component "installs" but does
not appear in ZCode.

## The one fact that governs everything

ZCode 3.3.6 loads **user-scope** skills, commands, and agents only from:

- `~/.zcode/skills/`, `~/.zcode/commands/`, `~/.zcode/agents/`
- `~/.agents/skills/` (shared across agent tools)

It **never** loads anything from `~/.zcode/marketplaces/<mp>/plugins/`. A
marketplace only becomes a live *plugin* when it is added through the ZCode UI
(Discover → `+`); there is **no CLI `plugin add`**, so a headless file-install
cannot register a plugin. Authoring a component inside a plugin bundle is
therefore necessary but not sufficient — something must place it at user scope.

**A fast-moving surface.** The plugin system is young and evolving — **Beta since
ZCode 3.2.0** — so its distribution and sync keep growing. A marketplace can now
be distributed as a **GitHub repo, Git URL, or ZIP URL** and installed through
the ZCode **Marketplace tab**, not only through this repo's headless flatten
installer (still the local path); see the Marketplace `source` rules in
`../../references/zcode-native-format.md` and the `publish-marketplace` skill.
Skill, MCP, plugin, and marketplace state can also **sync over SSH** now. None of
these is a CLI `plugin add` — the UI/Marketplace path is not a CLI, so a headless
file-install still cannot register a plugin.

## What the installer does about it

`install.sh install --setup <marketplace>` builds a complete `~/.zcode` and then
**flattens** each plugin's components to user scope
(`cli-tools/scripts/lib/build.sh`, `nddev::flatten_plugin_components`):

```
marketplaces/<mp>/plugins/<plugin>/skills/<name>/   ->  ~/.zcode/skills/<name>/
marketplaces/<mp>/plugins/<plugin>/commands/<name>  ->  ~/.zcode/commands/<name>
marketplaces/<mp>/plugins/<plugin>/agents/<name>    ->  ~/.zcode/agents/<name>
```

The marketplace tree stays under `~/.zcode/marketplaces/<mp>/` for the plugin
model and any later UI install, but the **flattened copy is what ZCode loads.**

Only **skills, commands, and agents** are flattened. `references/`, `tools/`,
`mcp.json`, `hooks.json`, and providers are **not** — they reach ZCode through
other channels (see the table) or are authoring-time material only.

## Where each component goes, and why

| Component | Authored in | Reaches ZCode via | Loaded from |
|---|---|---|---|
| Skill | `plugins/<p>/skills/<n>/SKILL.md` | installer flatten | `~/.zcode/skills/` |
| Command | `plugins/<p>/commands/<n>.md` | installer flatten | `~/.zcode/commands/` |
| Agent (subagent) | `plugins/<p>/agents/<n>.md` | installer flatten | `~/.zcode/agents/` |
| MCP server | `mcp.json` (template) | rendered into config | `~/.zcode/cli/config.json` → `mcp.servers` |
| Hook | `hooks.json` (template) | merged into config | `~/.zcode/cli/config.json` → `hooks` |
| Provider | `v2-config.template.json` | rendered | `~/.zcode/v2/config.json` |
| Plugin enable | `cli-config.template.json` | rendered | `~/.zcode/cli/config.json` → `plugins.enabledPlugins` |
| Reference / Tool | `plugins/<p>/{references,tools}/` | **not flattened** | reference via absolute installed path only |

Because skills/commands/agents all collapse into one flat user-scope directory
each, a component **basename must be unique across every plugin in the
marketplace**. A cross-plugin clash makes the install **fail closed**, not
shadow one silently.

## Fields ZCode records but never executes

Only `commands`, `skills`, `hooks`, and `mcpServers` execute on the pinned ZCode
3.3.6 runtime (plus `agents`, via the user-scope flatten above). The
plugin-manifest fields **`lspServers` (LSP/language servers), `outputStyles`,
`channels`, and `settings` are recorded but not executed** — authoring them
produces dead config. There is **no sixth "LSP component"** to add, so this
toolkit ships no skill for one by design. Mind the
**documented-surface-vs-executed-runtime gap**: the public Plugin doc lists LSP
as a bundle component, but 3.3.6 treats `lspServers` as inert and delivers LSP
through a **hook**, not a native component. A hook — or any plugin-relative
command — resolves the plugin root with the ZCode-native **`${ZCODE_PLUGIN_ROOT}`**;
prefer it over the Claude Code spelling `${CLAUDE_PLUGIN_ROOT}`. See
`../../references/zcode-native-format.md` for the full execution model.

## Lifecycle

- **install** — backup → build clean `~/.zcode` from the setup → flatten to user
  scope → render configs → restore preserved runtime state (credentials, tasks,
  certs). Each install writes a numbered backup slot.
- **switch** — `install --setup <other>` rebuilds `~/.zcode` from a different
  marketplace; the flatten regenerates user scope for the new setup.
- **remove** — backs up and deletes the whole managed `~/.zcode`; the flattened
  copies live inside it, so removal is clean. Skills in `~/.agents/skills`
  (other tools' shared skills) are untouched.

## Discovery precedence (for shadowing)

Skills/commands scan earliest-wins: configured roots → `~/.zcode/skills` →
`~/.agents/skills` → workspace `.zcode` → workspace `.agents` → enabled plugin
roots (lowest, UI-only). Our components load at `~/.zcode/skills` and shadow any
same-named skill below them.

## Routing to the authoring skills

New to the toolkit? Start with **`getting-started`** — a guided first run that
routes you to the right skill for each step (add one component, compose a whole
plugin, or start a new setup).

Author with the dedicated skills; each now documents the flatten reality:
`add-skill`, `add-command`, `add-agent`, `add-hook`, `add-mcp-server`,
`add-provider`, `add-plugin`, `add-marketplace`, `add-reference`, `add-tool`,
`add-instructions`; inspect with `list-components`, remove with
`remove-component`, pre-check with `validate-components`.

For whole-plugin and whole-marketplace work, five workflow skills sit on top of
the `add-*` set: `scaffold-plugin` composes a complete bundle from an intent,
`devtest-plugin` runs an isolated install-and-verify loop in throwaway
`HOME`/`ZCODE_HOME`, `release-review` gates the whole marketplace for release
readiness, `publish-marketplace` distributes a marketplace via GitHub / Git /
ZIP-URL for UI install, and `orchestrate-subagents` designs multi-subagent
workflows.
