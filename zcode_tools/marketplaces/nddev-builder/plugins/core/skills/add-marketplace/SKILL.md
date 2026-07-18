---
name: add-marketplace
description: Scaffolds a new self-contained ZCode marketplace — a complete ~/.zcode setup — under zcode_tools/marketplaces/. Use when creating a brand-new setup or profile such as nddev-builder or nddev-designer, or bootstrapping a marketplace directory from scratch.
---

# add-marketplace

Scaffolds a new self-contained marketplace — a complete `~/.zcode` build source.

## What a marketplace must contain (self-contained)

The installer's `validate_marketplace` requires these **5 files** to exist
inside the marketplace directory, or it refuses to build:

```text
  AGENTS.md                    ← system instructions → ~/.zcode/AGENTS.md
  marketplace.json             ← root manifest (name, owner, plugins[])
  cli-config.template.json     ← → ~/.zcode/cli/config.json (rendered)
  v2-config.template.json      ← → ~/.zcode/v2/config.json (rendered)
  v2-setting.template.json     ← → ~/.zcode/v2/setting.json (rendered)
```

In addition, conventionally create these (start empty with a `_comment` key —
the installer merges them into `cli/config.json` if present):

```text
  mcp.json                     ← MCP servers (merged into cli/config.json.mcp.servers)
  hooks.json                   ← lifecycle hooks (merged into cli/config.json.hooks.events)
  skills/   commands/   agents/   plugins/   ← optional user-scope component dirs
```

## Procedure

1. **Pick the name.** Convention: `nddev-<purpose>` (e.g. `nddev-builder`,
   `nddev-designer`). Lowercase, hyphens.

2. **Create the directory tree:**

   ```bash
   mkdir -p zcode_tools/marketplaces/<name>/{skills,commands,agents,plugins}
   ```

3. **Copy the template files from an existing marketplace** (e.g. `nddev-designer`
   is a clean, minimal starting point) and edit the marketplace-specific values:
   - `marketplace.json` → set `name` to `<name>`, write a one-sentence `description`.
   - `AGENTS.md` → set the `<!-- <name>:begin -->` marker and describe this setup.
   - `cli-config.template.json` → keep an explicit `provider/model` main-model
     reference, the matching secret-free provider/base URL/model declaration,
     and the plugins/hooks/MCP skeleton. ZCode CLI 0.15.2 will not create a
     desktop session without this bootstrap.
   - `v2-config.template.json` → define only optional explicit API-key
     providers under `custom:*` identities. Never reuse app-owned `builtin:*`
     identities; the default Z.ai OAuth provider is managed by ZCode.
   - `v2-setting.template.json` → set portable preferences; start
     `recentProjects` as `[]` and let ZCode populate device-local paths.
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

6. **Record release behavior changes.** Before a repository release, use one
   strict SemVer in `VERSION`, the `build_version` fields in
   `build/version.json` and `build/manifest.json`, the `nddev-builder`
   marketplace `core` entry, and the core plugin manifest; also update
   `CHANGELOG.md`.

## Rules

- Every marketplace is self-contained — it owns its AGENTS.md and all config
  templates, not shared at the `zcode_tools/` root.
- Every CLI template owns a valid main model reference and matching provider
  definition. OAuth credentials remain restored runtime state, not template
  values.
- Custom API-key providers never use ZCode-owned `builtin:*` identities.
- The marketplace name must match its directory name.
- Empty `skills/`/`commands/`/`agents/`/`plugins/` are valid only for a
  deliberately minimal profile whose `AGENTS.md` and marketplace description
  explain why project-specific tooling comes from the active workspace. Do not
  publish a future-work placeholder as an available setup.
- English only for all content.
- `validate_marketplace` proves the minimum structure. Also inspect provider
  semantics, portability, enabled plugins, secret boundaries, and the profile's
  substantive operating instructions before treating it as release-ready.
