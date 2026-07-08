# core (nddev-developer marketplace)

The `core` plugin of the **nddev-developer** marketplace. Developer toolkit for the
`nddev-zcode-app` estate: skills, slash commands, and a reviewer subagent for building
plugins, authoring skills, managing MCP servers, and cutting releases of the `~/.zcode`
build.

- **3 skills** — `add-plugin`, `add-skill`, `release-build`
- **3 slash commands** — `/nddev-add-plugin`, `/nddev-add-skill`, `/nddev-release`
- **1 subagent** — `nddev-native-reviewer` (GLM-5.2)

## What it provides

| Component | Purpose |
|---|---|
| `add-plugin` skill + `/nddev-add-plugin` | Scaffold a new self-contained plugin bundle inside a marketplace and register it |
| `add-skill` skill + `/nddev-add-skill` | Author a SKILL.md in the correct location (plugin- or user-scoped) |
| `release-build` skill + `/nddev-release` | Bump version sources in sync, update CHANGELOG, validate, tag |
| `nddev-native-reviewer` agent | Strict reviewer for ZCode-native format correctness |

## Install

Enable via **ZCode → Settings → Plugin Management** after adding the `nddev-developer`
marketplace (the local `zcode_tools/marketplaces/nddev-developer/` directory), or let the
installer lay it down into `~/.zcode/marketplaces/nddev-developer/plugins/core/`.

## Rules

- English only — code, docs, manifests, descriptions.
- Plugin manifests are metadata-only; components are convention-discovered.
- See the `repo-orientation` skill for the full repository map.
