---
name: add-plugin
description: Scaffold a new self-contained ZCode plugin bundle under zcode_tools/plugins/. Creates the .zcode-plugin/plugin.json manifest (metadata-only), the convention directories (skills/, commands/, agents/), a README, and registers the plugin in marketplace.json. Use when adding a new plugin to the nddev marketplace.
---

# add-plugin

Scaffolds a new ZCode-native plugin bundle in this repository.

## ZCode plugin format (the rules this skill enforces)

A plugin is a **self-contained directory** under `zcode_tools/plugins/<name>/`. ZCode
discovers its components **by convention** — the manifest is metadata-only and does not
list components.

```
zcode_tools/plugins/<name>/
  .zcode-plugin/plugin.json     ← metadata only (name, version, author, license, keywords, dependencies[])
  skills/<skill>/SKILL.md       ← one subfolder per skill
  commands/<cmd>.md             ← one file per slash command
  agents/<agent>.md             ← one file per subagent
  .mcp.json                     ← (only on the MCP transport plugin) {"mcpServers": {}}
  references/                   ← optional reference docs
  README.md
```

## Procedure

1. **Read the marketplace.** Open `zcode_tools/marketplace.json` and confirm the new
   plugin `name` is not already present. Plugin names match `^[a-z0-9][a-z0-9._-]{0,127}$`
   and should be prefixed `nddev-`.

2. **Create the directory tree:**
   ```
   zcode_tools/plugins/<name>/
     .zcode-plugin/
     skills/
     commands/
     agents/
   ```

3. **Write the manifest** at `.zcode-plugin/plugin.json`. Metadata-only — do NOT add
   `commands`, `skills`, `hooks`, `mcpServers`, or `agents` arrays. Use this shape:
   ```json
   {
     "name": "nddev-<name>",
     "version": "1.0.0",
     "description": "<English, one sentence>",
     "author": { "name": "Danil Silantyev (github:rldyourmnd), CEO NDDev", "url": "https://github.com/rldyourmnd" },
     "license": "AGPL-3.0-or-later",
     "homepage": "https://github.com/NDDev-it-com/nddev-zcode-app/tree/main/zcode_tools/plugins/nddev-<name>",
     "repository": "https://github.com/NDDev-it-com/nddev-zcode-app",
     "keywords": ["<topic>", "nddev"]
   }
   ```
   Add `dependencies` **only** if the plugin requires another plugin to be enabled first
   (e.g. an MCP-dependent plugin lists the MCP transport plugin).

4. **Add a README.md** at the plugin root: one-line purpose, what it provides (N skills,
   M commands, K agents), and the install note (enable via ZCode Plugin Management).

5. **Register in the marketplace.** Add an entry to the `plugins` array in
   `zcode_tools/marketplace.json`:
   ```json
   {
     "name": "nddev-<name>",
     "source": "./plugins/nddev-<name>",
     "description": "<English, matches the manifest description>",
     "version": "1.0.0",
     "author": { "name": "Danil Silantyev (github:rldyourmnd), CEO NDDev" },
     "category": "<development|infrastructure|research|quality|...>",
     "tags": ["<topic>", "nddev"],
     "license": "AGPL-3.0-or-later"
   }
   ```

6. **Validate.** Run `python3 -c "import json; json.load(open('zcode_tools/marketplace.json'))"`
   and the same for the new `plugin.json`.

7. **Bump version + changelog** if this is a release behavior change (see the
   `release-build` skill).

## Rules

- English only — for code, docs, manifests, descriptions, and keywords.
- Metadata-only manifests. Never declare component arrays.
- MCP servers go in ONE `plugins/<mcps>/.mcp.json` with `{"mcpServers": {}}`, never
  scattered across plugin manifests.
- Self-contained: a plugin's skills/commands/agents live inside its own directory.
