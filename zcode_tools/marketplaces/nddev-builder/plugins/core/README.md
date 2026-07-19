# core (`nddev-builder` marketplace)

The `core` plugin is a reusable ZCode-native toolkit for creating and managing
marketplaces, plugins, and convention-discovered components.

- **22 skills**: `getting-started`, `add-marketplace`, `add-plugin`, `add-skill`,
  `add-command`, `add-agent`, `add-hook`, `add-mcp-server`, `add-provider`,
  `add-reference`, `add-tool`, `add-instructions`, `list-components`,
  `remove-component`, `enable-plugin`, `nddev-builder-orientation`,
  `validate-components`, `scaffold-plugin`, `devtest-plugin`, `release-review`,
  `publish-marketplace`, and `orchestrate-subagents`.
- **22 slash commands**: `/nddev-start`, `/nddev-add-marketplace`,
  `/nddev-add-plugin`, `/nddev-add-skill`, `/nddev-add-command`,
  `/nddev-add-agent`, `/nddev-add-hook`, `/nddev-add-mcp`, `/nddev-add-provider`,
  `/nddev-add-reference`, `/nddev-add-tool`, `/nddev-add-instructions`,
  `/nddev-list`, `/nddev-remove`, `/nddev-enable`, `/nddev-orient`,
  `/nddev-validate`, `/nddev-scaffold`, `/nddev-devtest`,
  `/nddev-release-review`, `/nddev-publish`, and `/nddev-orchestrate`.
- **1 subagent**: `nddev-native-reviewer` (GLM-5.2).

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
are intentionally not shipped in this public plugin. Maintainers run them from
the private `nddev-harnesses` control plane.

## Install

Install with the repository installer (`install.sh install --setup nddev-builder`).
It places the marketplace under `~/.zcode/marketplaces/nddev-builder/` **and**
flattens each plugin's `skills/`, `commands/`, and `agents/` into
`~/.zcode/{skills,commands,agents}` — the flattened copy is what ZCode 3.3.6
loads, because it never reads the `marketplaces/.../plugins/` tree on a headless
install. Adding the marketplace through the ZCode UI (Plugin Management) is the
alternative that registers it as a live plugin.

Plugin manifests are metadata-only. `references/` and `tools/` are authoring
material and are not flattened. See the `nddev-builder-orientation` skill for the
full loading model.
