# core (`nddev-builder` marketplace)

The `core` plugin is a reusable ZCode-native toolkit for creating and managing
marketplaces, plugins, and convention-discovered components.

The exact skills, commands, agents, references, and tools are discovered from
this plugin's convention directories. `.zcode-plugin/plugin.json` owns plugin
identity and version.

## Capabilities

| Component | Purpose |
| --- | --- |
| `getting-started` | Guided first run — zero to a validated extension |
| `add-marketplace` | Scaffold a self-contained marketplace |
| `add-plugin` | Scaffold a plugin bundle inside a marketplace |
| `add-skill` | Author a plugin- or user-scoped `SKILL.md` |
| `add-command` | Author a slash command |
| `add-agent` | Author a ZCode subagent |
| `add-hook` | Register a lifecycle hook |
| `add-mcp-server` | Register an MCP server or CLI-plus-skill alternative |
| `add-provider` | Add an LLM provider to the v2 configuration |
| `add-reference` | Add a reference document to a plugin bundle |
| `add-tool` | Add a non-MCP CLI tool and optional companion skill |
| `list-components` | Inventory marketplace components without mutation |
| `remove-component` | Remove a component after reference checks |
| `enable-plugin` | Enable or disable a plugin in the CLI configuration |
| `scaffold-plugin` | Compose a whole plugin from an intent |
| `devtest-plugin` | Isolated install-and-verify loop in throwaway state |
| `release-review` | Gate a whole marketplace for release readiness |
| `publish-marketplace` | Distribute a marketplace via GitHub/Git/ZIP URL for UI install |
| `orchestrate-subagents` | Design multi-subagent workflows within ZCode limits |
| `nddev-native-reviewer` | Review ZCode-native format correctness |

Development-only test, benchmark, release, and repository-doctor capabilities
are intentionally not shipped in this public plugin.

## Install

Install with the repository installer (`install.sh install --setup nddev-builder`).
It places the marketplace under `~/.zcode/marketplaces/nddev-builder/` **and**
flattens each plugin's `skills/`, `commands/`, and `agents/` into
`~/.zcode/{skills,commands,agents}` — the flattened copy is the headless
runtime surface declared by `build/manifest.json`. Adding the marketplace through the ZCode UI (Plugin Management) is the
alternative that registers it as a live plugin.

Plugin manifests are metadata-only. `references/` and `tools/` are authoring
material and are not flattened. See the `nddev-builder-orientation` skill for the
full loading model.
