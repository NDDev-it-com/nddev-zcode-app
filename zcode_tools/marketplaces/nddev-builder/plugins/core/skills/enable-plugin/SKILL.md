---
name: enable-plugin
description: Enable or disable a plugin in a marketplace's cli-config template by populating the enabledPlugins map. Explains the plugin enable key format (name@marketplace) and the enabled/disabled semantics. Use when a marketplace has plugins registered in marketplace.json but they are not enabled in the config template, or when you need to toggle a plugin on or off.
---

# enable-plugin

Populates the `enabledPlugins` map in `cli-config.template.json` so ZCode
knows which plugins to activate.

## How plugin enabling works

ZCode's `cli/config.json` has:
```json
{
  "plugins": {
    "enabled": true,
    "enabledPlugins": {
      "plugin-name@marketplace-name": true
    }
  }
}
```

- `plugins.enabled` (bool) — master switch for the plugin system. Must be
  `true` (the default in every marketplace template).
- `plugins.enabledPlugins` (object) — per-plugin enable map. The key format is
  `<plugin-name>@<marketplace-name>`. Value `true` = enabled, `false` =
  explicitly disabled. Absent = not enabled.

If `enabledPlugins` is `{}` (empty), no plugins are active even if they are
registered in `marketplace.json`.

## Procedure

1. Ask the user for:
   - The marketplace name.
   - The plugin name to enable (or disable).
   - Action: enable or disable.

2. Read `marketplace.json` and confirm the plugin is registered:
   ```bash
   python3 -c "import json; d=json.load(open('zcode_tools/marketplaces/<mp>/marketplace.json')); print([p['name'] for p in d.get('plugins',[])])"
   ```
   If the plugin is not in the list, tell the user to add it first (follow the
   `add-plugin` skill).

3. Read `cli-config.template.json` and locate `plugins.enabledPlugins`.

4. Set the key `<plugin-name>@<marketplace-name>`:
   - **Enable**: set to `true`.
   - **Disable**: set to `false` (or remove the key entirely).

5. Write the updated JSON (preserve `_comment`, indent=2, trailing newline).

6. Validate:
   ```bash
   python3 -c "import json; d=json.load(open('zcode_tools/marketplaces/<mp>/cli-config.template.json')); print(d['plugins']['enabledPlugins'])"
   cli-tools/scripts/install.sh install --marketplace <mp> --platform macos --plan
   ```

## Rules

- The key format is `plugin-name@marketplace-name` (NOT `plugin-name` alone).
- `plugins.enabled` must remain `true` — do not disable the master switch.
- Preserve the `_comment` field and all other keys in the template.
- English only.
