---
description: Author a new ZCode skill (SKILL.md) in the correct location — plugin-scoped or user-scoped.
---

Author a new ZCode skill in this repository.

Follow the `add-skill` skill exactly:

1. Ask the user for: the skill name, whether it is plugin-scoped or user-scoped, and a one-sentence purpose.
2. Create the skill directory:
   - plugin-scoped: `zcode_tools/plugins/<plugin>/skills/<name>/SKILL.md`
   - user-scoped: `zcode_tools/skills/<name>/SKILL.md`
3. Write YAML frontmatter: `name` (matches the directory), `description` (English, trigger-rich — explain WHEN to use it).
4. Write the body as a clear procedure an agent can follow.
5. Confirm the YAML frontmatter is delimited by `---` fences and parses.
6. Remind that component arrays must NOT be added to any `plugin.json` — discovery is by convention.
