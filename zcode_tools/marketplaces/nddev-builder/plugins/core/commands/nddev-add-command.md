---
description: Author a new ZCode slash command (commands/<name>.md) in the active marketplace.
---

Author a new slash command in this repository.

Follow the `add-command` skill exactly:

1. Ask the user for: the command name, whether it is plugin-scoped or user-scoped, and what it should do.
2. Create the file:
   - plugin-scoped: `zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/commands/<name>.md`
   - user-scoped: `zcode_tools/marketplaces/<marketplace>/commands/<name>.md`
3. Write YAML frontmatter with a `description` (English, explains what it does and when to use it).
4. Write the body as imperative instructions the agent follows when the command runs. Reference skills by name if the command delegates.
5. Confirm the frontmatter is delimited by `---` fences and parses.
6. Remind that the filename becomes the command name (`/name`), and nested dirs join with a colon (`/dir:name`).
