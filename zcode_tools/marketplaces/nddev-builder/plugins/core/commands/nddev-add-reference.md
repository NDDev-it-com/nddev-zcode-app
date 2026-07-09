---
description: Add a reference documentation file to a plugin bundle under plugins/<name>/references/.
---

Add a reference document to a plugin.

Follow the `add-reference` skill exactly:

1. Ask the user for: the marketplace name, the plugin name, and the reference document name.
2. Create `plugins/<plugin>/references/` if it does not exist.
3. Write the reference Markdown file (spec, format, design doc — not a procedure).
4. Remind that references are NOT declared in `plugin.json` — convention discovery.
5. Run `install --plan` to confirm nothing broke.
