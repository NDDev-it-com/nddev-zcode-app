---
name: add-plugin
description: Scaffold a new self-contained ZCode plugin bundle inside a marketplace. Creates the .zcode-plugin/plugin.json manifest (metadata-only), the convention directories (skills/, commands/, agents/), a README, and registers the plugin in that marketplace's marketplace.json. Use when adding a new plugin to any nddev marketplace.
---

# add-plugin

Scaffolds a new ZCode-native plugin bundle inside a marketplace in this repository.

## ZCode plugin format (the rules this skill enforces)

Plugins live **inside a marketplace directory** under
`zcode_tools/marketplaces/<marketplace>/plugins/<name>/`. ZCode discovers components
**by convention** — the manifest is metadata-only and does not list components.

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
   `commands`, `skills`, `hooks`, `mcpServers`, or `agents` arrays. Use this shape:
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

8. **Bump version + changelog** if this is a release behavior change (see the
   `release-build` skill).

## Rules

- English only — for code, docs, manifests, descriptions, and keywords.
- Metadata-only manifests. Never declare component arrays.
- MCP servers go in ONE `plugins/<mcps>/.mcp.json` with `{"mcpServers": {}}`, never
  scattered across plugin manifests.
- Self-contained: a plugin's skills/commands/agents live inside its own directory.
- A marketplace can hold many plugins; a plugin belongs to exactly one marketplace.
