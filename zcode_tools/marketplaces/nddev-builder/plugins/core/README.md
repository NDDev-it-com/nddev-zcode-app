# core (`nddev-builder` marketplace)

The `core` plugin is a reusable ZCode-native toolkit for creating and managing
marketplaces, plugins, and convention-discovered components.

- **13 skills**: `add-marketplace`, `add-plugin`, `add-skill`, `add-command`,
  `add-agent`, `add-hook`, `add-mcp-server`, `add-provider`, `add-reference`,
  `add-tool`, `list-components`, `remove-component`, and `enable-plugin`.
- **13 slash commands**: `/nddev-add-marketplace`, `/nddev-add-plugin`,
  `/nddev-add-skill`, `/nddev-add-command`, `/nddev-add-agent`,
  `/nddev-add-hook`, `/nddev-add-mcp`, `/nddev-add-provider`,
  `/nddev-add-reference`, `/nddev-add-tool`, `/nddev-list`, `/nddev-remove`,
  and `/nddev-enable`.
- **1 subagent**: `nddev-native-reviewer` (GLM-5.2).

## Capabilities

| Component | Purpose |
| --- | --- |
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
| `nddev-native-reviewer` | Review ZCode-native format correctness |

Development-only test, benchmark, release, and repository-doctor capabilities
are intentionally not shipped in this public plugin. Maintainers run them from
the private `nddev-harnesses` control plane.

## Install

Add the local `nddev-builder` marketplace in ZCode Plugin Management, or use the
repository installer to place it under
`~/.zcode/marketplaces/nddev-builder/plugins/core/`.

Plugin manifests are metadata-only; ZCode discovers skills, commands, agents,
references, and tools by convention.
