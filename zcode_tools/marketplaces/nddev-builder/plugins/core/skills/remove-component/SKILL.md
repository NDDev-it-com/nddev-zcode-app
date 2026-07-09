---
name: remove-component
description: Safely remove a component (plugin, skill, command, agent, reference, or CLI tool) from a marketplace. Checks for references in other files before deletion, updates marketplace.json if removing a plugin, and validates JSON after changes. Refuses if the component is referenced elsewhere unless the user confirms. Use when cleaning up, refactoring, or deleting a component that is no longer needed.
---

# remove-component

Safely removes a component from a marketplace.

## Procedure

1. Ask the user for:
   - The marketplace name.
   - The component type: plugin, skill, command, agent, reference, or tool.
   - The component name (directory or filename without `.md`).

2. Resolve the path:
   - **plugin**: `zcode_tools/marketplaces/<mp>/plugins/<name>/`
   - **skill** (plugin-scoped): `plugins/<plugin>/skills/<name>/`
   - **skill** (user-scoped): `skills/<name>/`
   - **command**: `commands/<name>.md` or `plugins/<plugin>/commands/<name>.md`
   - **agent**: `agents/<name>.md` or `plugins/<plugin>/agents/<name>.md`
   - **reference**: `plugins/<plugin>/references/<name>.md`
   - **tool**: `plugins/<plugin>/tools/<name>/`

3. Confirm the path exists. If not, report and stop.

4. **Reference check** — search ALL `.md`, `.json`, `.sh` files in the
   marketplace for mentions of the component name:
   ```bash
   grep -rn '<name>' zcode_tools/marketplaces/<mp>/ --include='*.md' --include='*.json' --include='*.sh' \
     | grep -v 'marketplace.json' | grep -v '<path-to-the-component-itself>'
   ```
   If references are found:
   - Report each file:line.
   - Ask the user to confirm removal despite references, or abort.
   - Do NOT auto-remove referenced components without confirmation.

5. **Remove the component**:
   - Directory: `rm -rf <path>`.
   - File: `rm <path>`.

6. **Update marketplace.json** (only if removing a plugin):
   - Remove the plugin entry from the `plugins` array.
   - Validate the JSON parses.
   - Ensure the remaining plugins still have valid `source` paths.

7. **Validate**:
   ```bash
   python3 -c "import json; json.load(open('zcode_tools/marketplaces/<mp>/marketplace.json'))"
   cli-tools/scripts/install.sh install --marketplace <mp> --platform macos --plan
   ```

8. If this is a release behavior change, remind the user to keep `VERSION`,
   `build/version.json`, and `build/manifest.json` in sync and update
   `CHANGELOG.md`.

## Rules

- Never remove a component without confirming references first.
- Always validate JSON and run `install --plan` after removal.
- If removing a plugin, also check whether other plugins declare it in their
  `dependencies` — those dependencies must be removed or updated too.
- English only for all output.
