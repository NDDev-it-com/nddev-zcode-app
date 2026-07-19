---
name: scaffold-plugin
description: Composes a complete ZCode plugin from a described intent — a metadata-only manifest plus the right mix of skills, commands, agents, hooks, and MCP config — and registers it in the marketplace. Use when starting a plugin from a goal rather than adding one component at a time.
---

# scaffold-plugin

Turn a described capability into a complete, install-ready ZCode plugin bundle in
one pass, then hand off to `validate-components`. This orchestrates the focused
`add-*` skills; it does not replace them.

## When to use

Use when the input is an intent ("a plugin that reviews Terraform and blocks
unsafe applies") rather than a single component. To add one skill or command to
an existing plugin, use the matching `add-*` skill directly.

## ZCode facts this skill respects

- A plugin is a metadata-only `.zcode-plugin/plugin.json` plus components under
  convention directories. ZCode 3.3.6 executes only `commands`, `skills`,
  `hooks`, `mcpServers`, and user-scope `agents`; never scaffold the inert
  `lspServers`/`outputStyles`/`channels`/`settings` fields or manifest component
  arrays. See `nddev-builder-orientation`.
- The headless install flattens every plugin's `skills/`, `commands/`, and
  `agents/` into `~/.zcode/{skills,commands,agents}` and fails closed on a
  duplicate basename, so every component this skill emits must have a
  repo-unique name.

## Procedure

1. **Fix the boundary.** From the intent, decide the plugin's single
   responsibility and the exact components it needs — which skills, which
   commands, whether an agent, a hook, or an MCP server is genuinely required.
   Prefer the smallest set that meets the intent.
2. **Pick or create the marketplace.** Use `add-marketplace` if none fits, then
   scaffold the empty bundle with `add-plugin` (manifest + directories + README +
   marketplace entry). For a bundle that must also run in Claude Code, use
   `add-plugin`'s optional dual `.zcode-plugin` + `.claude-plugin` manifest.
3. **Add each component** with its focused skill: `add-skill`, `add-command`,
   `add-agent`, `add-hook`, `add-mcp-server`, `add-instructions`,
   `add-reference`, `add-tool`, `add-provider`. Keep every basename unique across
   the whole repository.
4. **Wire dependencies only if real** (for example, an MCP-consuming plugin
   depends on the MCP transport plugin) — `name@marketplace` strings, with
   cross-marketplace dependencies listed in `allowCrossMarketplaceDependenciesOn`.
5. **Validate** with `validate-components`, then the non-mutating
   `install.sh install --setup <mp> --plan` gate. Run `devtest-plugin` for a
   behavioral pass.
6. **Record the release** per `add-plugin` step 8 (one SemVer across the five
   version sources plus `CHANGELOG.md`) if the bundle ships.

## Rules

- English only. Metadata-only manifests; never declare component arrays.
- Smallest component set that meets the intent; every emitted basename unique
  across all plugins.
- Generated content is a starting point — complete each component and run
  `validate-components` before shipping.
