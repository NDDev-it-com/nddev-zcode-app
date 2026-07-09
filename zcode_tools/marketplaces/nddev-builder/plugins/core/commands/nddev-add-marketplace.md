---
description: Scaffold a new self-contained marketplace (a complete ~/.zcode setup) under zcode_tools/marketplaces/.
---

Scaffold a brand-new marketplace.

Follow the `add-marketplace` skill exactly:

1. Ask for the marketplace name (convention: `nddev-<purpose>`).
2. Create the directory tree: `zcode_tools/marketplaces/<name>/{skills,commands,agents,plugins}`.
3. Copy the template files from `nddev-designer` (the cleanest minimal example) and edit:
   - `marketplace.json` → set `name` and `description`.
   - `AGENTS.md` → set the `<!-- <name>:begin -->` marker and write substantive,
     purpose-specific operating instructions.
   - Keep `recentProjects: []`; update providers and enabled plugins
     deliberately. Empty plugins/hooks/MCP are valid only when the profile
     documents why workspace-specific tooling is intentional.
4. Validate by running: `cli-tools/scripts/install.sh install --marketplace <name> --plan` — it must pass `validate_marketplace`.
5. Confirm it appears in `install.sh list`.
6. Remind to bump the build version if this is a release change.
