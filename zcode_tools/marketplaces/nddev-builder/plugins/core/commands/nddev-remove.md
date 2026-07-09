---
description: Safely remove a component (plugin, skill, command, agent, reference, or tool) from a marketplace — checks references first, updates marketplace.json, validates.
---

Remove a component from a marketplace.

Follow the `remove-component` skill exactly:

1. Ask the user for: the marketplace name, the component type, and the component name.
2. Resolve the path and confirm it exists.
3. Search for references to the component in other files. If found, ask the user to confirm or abort.
4. Remove the component (directory or file).
5. If removing a plugin, update `marketplace.json` (remove the entry, validate JSON).
6. Run `install --plan` to confirm nothing broke.
