---
name: add-plugin
description: Scaffolds a new self-contained plugin bundle inside a ZCode marketplace and registers it in marketplace.json. Use when adding a plugin to a marketplace, or grouping skills, commands, and agents into one installable bundle.
---

# add-plugin

Scaffolds a new ZCode-native plugin bundle inside a marketplace in this repository.

## ZCode plugin format (the rules this skill enforces)

Plugins live **inside a marketplace directory** under
`zcode_tools/marketplaces/<marketplace>/plugins/<name>/`, with a metadata-only
manifest and components under convention directories (`skills/`, `commands/`,
`agents/`).

> **How the components actually load.** Convention-discovery from a plugin root
> applies only to marketplaces **added through the ZCode UI**. For this repo's
> headless file-install, ZCode never reads `~/.zcode/marketplaces/.../plugins/`;
> the installer **flattens** each plugin's `skills/`, `commands/`, and `agents/`
> into `~/.zcode/{skills,commands,agents}`, and that flattened copy is what
> loads. `references/` and `tools/` are **not** flattened. Read
> `nddev-builder-orientation` for the full model, and keep component basenames
> unique across every plugin (the flatten fails closed on a collision).

```
zcode_tools/marketplaces/<marketplace>/
  marketplace.json                       ← the marketplace root manifest
  plugins/
    <name>/
      .zcode-plugin/plugin.json          ← metadata only (name, version, author, license, keywords, dependencies[])
      skills/<skill>/SKILL.md            ← one subfolder per skill
      commands/<cmd>.md                  ← one file per slash command
      agents/<agent>.md                  ← one file per subagent
      .mcp.json                          ← (only on the MCP transport plugin) {"mcpServers": {}}
      references/                        ← optional reference docs
      README.md
```

## Procedure

1. **Pick the marketplace.** Confirm which marketplace the plugin belongs to —
   `zcode_tools/marketplaces/<marketplace>/` must exist and have a `marketplace.json`.
   If a new marketplace is needed, create it first (its own directory + root
   `marketplace.json` with an empty `plugins: []`).

2. **Read the marketplace manifest.** Open
   `zcode_tools/marketplaces/<marketplace>/marketplace.json` and confirm the new plugin
   `name` is not already present. Plugin names match `^[a-z0-9][a-z0-9._-]{0,127}$`.

3. **Create the directory tree:**
   ```
   zcode_tools/marketplaces/<marketplace>/plugins/<name>/
     .zcode-plugin/
     skills/
     commands/
     agents/
   ```

4. **Write the manifest** at `.zcode-plugin/plugin.json`. Metadata-only — do NOT add
   `commands`, `skills`, `hooks`, `mcpServers`, or `agents` arrays, nor the inert
   `lspServers`, `outputStyles`, `channels`, or `settings` fields (ZCode 3.3.6
   records but never executes them; see `nddev-builder-orientation`). Use this shape:
   ```json
   {
     "name": "<name>",
     "version": "1.0.0",
     "description": "<English, one sentence>",
     "author": { "name": "Danil Silantyev (github:rldyourmnd), CEO NDDev", "url": "https://github.com/rldyourmnd" },
     "license": "AGPL-3.0-or-later",
     "homepage": "https://github.com/NDDev-it-com/nddev-zcode-app/tree/main/zcode_tools/marketplaces/<marketplace>/plugins/<name>",
     "repository": "https://github.com/NDDev-it-com/nddev-zcode-app",
     "keywords": ["<topic>", "nddev"]
   }
   ```
   Add `dependencies` **only** if the plugin requires another plugin to be enabled first
   (e.g. an MCP-dependent plugin lists the MCP transport plugin). Dependencies are
   `name@marketplace` strings; cross-marketplace deps require the target marketplace
   listed in the marketplace's `allowCrossMarketplaceDependenciesOn`.

   **Portability (optional):** ZCode resolves a manifest in the order
   `.zcode-plugin/plugin.json` → `.claude-plugin/plugin.json` →
   `.codex-plugin/plugin.json`. To make the same bundle also run in Claude Code,
   you may write an identical `.claude-plugin/plugin.json` alongside the
   `.zcode-plugin` one. ZCode-only bundles need only `.zcode-plugin`.

   **Component path rule (critical):** if you DO declare component paths in the
   manifest (e.g. `"skills": ["./skills"]`), they MUST be **relative and inside
   the plugin root**. An absolute path or one that escapes the plugin root
   (`../something`) is **rejected** and the component is silently dropped. By
   default, leave components undeclared — convention discovery handles them.

5. **Add a README.md** at the plugin root: one-line purpose, what it provides (N skills,
   M commands, K agents), and the install note (enable via ZCode Plugin Management).

6. **Register in the marketplace.** Add an entry to the `plugins` array in
   `zcode_tools/marketplaces/<marketplace>/marketplace.json`:
   ```json
   {
     "name": "<name>",
     "source": "./plugins/<name>",
     "description": "<English, matches the manifest description>",
     "version": "1.0.0",
     "author": { "name": "Danil Silantyev (github:rldyourmnd), CEO NDDev" },
     "category": "<development|infrastructure|research|quality|...>",
     "tags": ["<topic>", "nddev"],
     "license": "AGPL-3.0-or-later"
   }
   ```

7. **Validate.** Run
   `python3 -c "import json; json.load(open('zcode_tools/marketplaces/<marketplace>/marketplace.json'))"`
   and the same for the new `plugin.json`.

8. **Record release behavior changes.** Before a repository release, use one
   strict SemVer in `VERSION`, the `build_version` fields in
   `build/version.json` and `build/manifest.json`, the `nddev-builder`
   marketplace `core` entry, and the core plugin manifest; also update
   `CHANGELOG.md`.

## Rules

- English only — for code, docs, manifests, descriptions, and keywords.
- Metadata-only manifests. Never declare component arrays.
- MCP servers go in ONE `plugins/<mcps>/.mcp.json` with `{"mcpServers": {}}`, never
  scattered across plugin manifests.
- Self-contained: a plugin's skills/commands/agents live inside its own directory.
- A marketplace can hold many plugins; a plugin belongs to exactly one marketplace.
