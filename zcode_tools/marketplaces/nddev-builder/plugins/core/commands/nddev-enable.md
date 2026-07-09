---
description: Enable or disable a plugin in a marketplace's cli-config template by populating the enabledPlugins map.
---

Enable or disable a plugin in a marketplace.

Follow the `enable-plugin` skill exactly:

1. Ask the user for: the marketplace name, the plugin name, and the action (enable or disable).
2. Confirm the plugin is registered in `marketplace.json`.
3. Set the key `<plugin-name>@<marketplace-name>` in `cli-config.template.json` under `plugins.enabledPlugins`.
4. Validate JSON and run `install --plan`.
