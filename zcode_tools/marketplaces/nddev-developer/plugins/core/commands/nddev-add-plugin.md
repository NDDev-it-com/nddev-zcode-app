---
description: Scaffold a new ZCode plugin bundle under zcode_tools/plugins/ and register it in the marketplace.
---

Scaffold a new self-contained ZCode plugin in this repository.

Follow the `add-plugin` skill exactly:

1. Read `zcode_tools/marketplace.json` and ask for the plugin name if not given (must match `^[a-z0-9][a-z0-9._-]{0,127}$`, prefer the `nddev-` prefix).
2. Create `zcode_tools/plugins/<name>/` with `.zcode-plugin/`, `skills/`, `commands/`, `agents/`.
3. Write a metadata-only `.zcode-plugin/plugin.json` (English description, AGPL-3.0-or-later, no component arrays).
4. Add a `README.md` at the plugin root.
5. Register the plugin in the `plugins` array of `zcode_tools/marketplace.json` (`source: "./plugins/<name>"`).
6. Validate both JSON files parse.
7. Report what was created and remind to bump the build version if this is a release.

Do not invent placeholder skills/commands inside the new plugin — leave the convention dirs empty (with a `.gitkeep`) unless the user asks for content.
