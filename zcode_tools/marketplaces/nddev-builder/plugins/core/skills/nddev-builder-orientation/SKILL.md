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

Author with the dedicated skills; each now documents the flatten reality:
`add-skill`, `add-command`, `add-agent`, `add-hook`, `add-mcp-server`,
`add-provider`, `add-plugin`, `add-marketplace`, `add-reference`, `add-tool`,
`add-instructions`; inspect with `list-components`, remove with
`remove-component`, pre-check with `validate-components`.
