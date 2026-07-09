---
name: add-marketplace
description: Scaffold a new self-contained marketplace (a complete ~/.zcode setup) under zcode_tools/marketplaces/. Creates all required files (AGENTS.md, marketplace.json, config templates, mcp/hooks, empty skills/commands/agents/plugins dirs) so the installer's validation passes. Use when creating a brand-new setup like nddev-builder or nddev-designer.
---

# add-marketplace

Scaffolds a new self-contained marketplace — a complete `~/.zcode` build source.

## What a marketplace must contain (self-contained)

The installer's `validate_marketplace` requires these **5 files** to exist
inside the marketplace directory, or it refuses to build:

```
  AGENTS.md                    ← system instructions → ~/.zcode/AGENTS.md
  marketplace.json             ← root manifest (name, owner, plugins[])
  cli-config.template.json     ← → ~/.zcode/cli/config.json (rendered)
  v2-config.template.json      ← → ~/.zcode/v2/config.json (rendered)
  v2-setting.template.json     ← → ~/.zcode/v2/setting.json (rendered)
```

In addition, conventionally create these (start empty with a `_comment` key —
the installer merges them into `cli/config.json` if present):

```
  mcp.json                     ← MCP servers (merged into cli/config.json.mcp.servers)
  hooks.json                   ← lifecycle hooks (merged into cli/config.json.hooks.events)
  skills/   commands/   agents/   plugins/   ← user-scope dirs (start empty, add .gitkeep)
```

## Procedure

1. **Pick the name.** Convention: `nddev-<purpose>` (e.g. `nddev-builder`,
   `nddev-designer`). Lowercase, hyphens.

2. **Create the directory tree:**
   ```
   mkdir -p zcode_tools/marketplaces/<name>/{skills,commands,agents,plugins}
   ```

3. **Copy the template files from an existing marketplace** (e.g. `nddev-designer`
   is a clean, minimal starting point) and edit the marketplace-specific values:
   - `marketplace.json` → set `name` to `<name>`, write a one-sentence `description`.
   - `AGENTS.md` → set the `<!-- <name>:begin -->` marker and describe this setup.
   - `cli-config.template.json` → keep the default (plugins/hooks/mcp skeleton).
   - `v2-config.template.json` → set the provider definitions (default: Z.ai GLM-5.2).
   - `v2-setting.template.json` → set preferences (locale, recentProjects templated
     with `${HOME}`).
   - `mcp.json`, `hooks.json` → start empty (with the `_comment` key).

4. **Validate the marketplace is self-contained** before committing:
   ```bash
   cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan
   ```
   This runs `validate_marketplace` and will error if a required file is missing.

5. **Verify it appears in the list:**
   ```bash
   cli-tools/scripts/install.sh list
   ```

6. **Bump the build version** if this is a release behavior change (see
   `release-build` skill).

## Rules

- Every marketplace is self-contained — it owns its AGENTS.md and all config
  templates, not shared at the `zcode_tools/` root.
- The marketplace name must match its directory name.
- Start with empty `skills/`/`commands/`/`agents/`/`plugins/` (`.gitkeep`) and
  fill them deliberately later.
- English only for all content.
- `validate_marketplace` is the gatekeeper — if the `--plan` run passes, the
  marketplace is correctly structured.
