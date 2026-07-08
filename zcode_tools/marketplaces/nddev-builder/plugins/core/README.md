# core (nddev-builder marketplace)

The `core` plugin of the **nddev-builder** marketplace — the complete toolkit for
building and maintaining everything under ZCode: plugin scaffolding, component
authoring, MCP/hook registration, marketplace creation, releases, and
consistency checking.

- **9 skills** — add-plugin, add-skill, add-command, add-agent, add-hook,
  add-mcp-server, add-marketplace, release-build, doctor
- **9 slash commands** — `/nddev-add-plugin`, `/nddev-add-skill`,
  `/nddev-add-command`, `/nddev-add-agent`, `/nddev-add-hook`,
  `/nddev-add-mcp`, `/nddev-add-marketplace`, `/nddev-release`, `/nddev-doctor`
- **1 subagent** — `nddev-native-reviewer` (GLM-5.2)

## What it provides

| Component | Purpose |
|---|---|
| `add-plugin` | Scaffold a self-contained plugin bundle inside a marketplace |
| `add-skill` | Author a SKILL.md (plugin- or user-scoped) |
| `add-command` | Author a slash command (commands/<name>.md) |
| `add-agent` | Author a subagent (agents/<name>.md with name + model) |
| `add-hook` | Register a lifecycle hook in hooks.json |
| `add-mcp-server` | Register a tool — classic MCP OR CLI+skill alternative |
| `add-marketplace` | Scaffold a brand-new self-contained marketplace |
| `release-build` | Bump version sources, update CHANGELOG, validate, tag |
| `doctor` | Deep consistency check (versions, ZCode-spec, stale paths, JSON, secrets) |
| `nddev-native-reviewer` | Strict reviewer for ZCode-native format correctness |

## Install

Enable via **ZCode → Settings → Plugin Management** after adding the
`nddev-builder` marketplace (the local `zcode_tools/marketplaces/nddev-builder/`
directory), or let the installer lay it down into
`~/.zcode/marketplaces/nddev-builder/plugins/core/`.

## Rules

- English only — code, docs, manifests, descriptions.
- Plugin manifests are metadata-only; components are convention-discovered.
- See the `repo-orientation` skill for the full repository map.
