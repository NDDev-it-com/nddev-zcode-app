---
description: Scaffold a new ZCode plugin bundle inside a marketplace and register it.
---

Scaffold a new self-contained ZCode plugin in this repository.

Follow the `add-plugin` skill exactly:

1. Ask for the plugin name (must match `^[a-z0-9][a-z0-9._-]{0,127}$`) and which marketplace it belongs to. If the marketplace is not given, default to the first one under `zcode_tools/marketplaces/`.
2. Create `zcode_tools/marketplaces/<marketplace>/plugins/<name>/` with `.zcode-plugin/`, `skills/`, `commands/`, `agents/`.
3. Write a metadata-only `.zcode-plugin/plugin.json` (English description, AGPL-3.0-or-later, no component arrays).
4. Add a `README.md` at the plugin root.
5. Register the plugin in the `plugins` array of `zcode_tools/marketplaces/<marketplace>/marketplace.json` (`source: "./plugins/<name>"`).
6. Validate both JSON files parse.
7. Report what was created and remind to bump the build version if this is a release.

Do not invent placeholder skills/commands inside the new plugin — leave the convention dirs empty (with a `.gitkeep`) unless the user asks for content.
