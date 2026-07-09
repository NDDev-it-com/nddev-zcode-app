# core (nddev-builder marketplace)

The `core` plugin of the **nddev-builder** marketplace — the complete toolkit for
building and maintaining everything under ZCode: plugin scaffolding, component
authoring, MCP/hook/provider registration, marketplace creation, listing,
removal, releases, and consistency checking.

- **18 skills** — add-plugin, add-skill, add-command, add-agent, add-hook,
  add-mcp-server, add-provider, add-reference, add-tool, add-marketplace,
  list-components, remove-component, enable-plugin, run-tests, add-test, run-benchmarks, release-build, doctor
- **18 slash commands** — `/nddev-add-plugin`, `/nddev-add-skill`,
  `/nddev-add-command`, `/nddev-add-agent`, `/nddev-add-hook`,
  `/nddev-add-mcp`, `/nddev-add-provider`, `/nddev-add-reference`,
  `/nddev-add-tool`, `/nddev-add-marketplace`, `/nddev-list`, `/nddev-remove`,
  `/nddev-enable`, `/nddev-release`, `/nddev-doctor`
- **1 subagent** — `nddev-native-reviewer` (GLM-5.2)

## What it provides

| Component | Purpose |
|---|---|
| `add-marketplace` | Scaffold a brand-new self-contained marketplace |
| `add-plugin` | Scaffold a self-contained plugin bundle inside a marketplace |
| `add-skill` | Author a SKILL.md (plugin- or user-scoped) |
| `add-command` | Author a slash command (commands/<name>.md) |
| `add-agent` | Author a subagent (agents/<name>.md with name + model) |
| `add-hook` | Register a lifecycle hook in hooks.json |
| `add-mcp-server` | Register a tool — classic MCP OR CLI+skill alternative |
| `add-provider` | Add a model provider (LLM endpoint) to v2-config |
| `add-reference` | Add a reference doc to a plugin bundle |
| `add-tool` | Add a CLI tool (non-MCP) with a companion skill |
| `list-components` | List all components in a marketplace (read-only) |
| `remove-component` | Safely remove a component (checks references first) |
| `enable-plugin` | Enable or disable a plugin in cli-config |
| `run-tests` | Run the test suite (30 pytest tests + fast lane) |
| `add-test` | Scaffold a new test file |
| `run-benchmarks` | Run installer performance benchmarks |
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
