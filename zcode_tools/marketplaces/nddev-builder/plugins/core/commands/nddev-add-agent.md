---
description: Author a new ZCode subagent (agents/<name>.md with name + model) in the active marketplace.
---

Author a new subagent in this repository.

Follow the `add-agent` skill exactly:

1. Ask the user for: the agent name, its role (reviewer, researcher, worker), and what it should produce.
2. Create the file:
   - plugin-scoped: `zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/agents/<name>.md`
   - user-scoped: `zcode_tools/marketplaces/<marketplace>/agents/<name>.md`
3. Write YAML frontmatter: `name` (matches filename), `model: GLM-5.2`, `description` (English, when to delegate).
4. Write the body as a complete system prompt: role → checklist/constraints → output format.
5. Confirm the frontmatter parses.
6. Remind that the body IS the system prompt — be specific about constraints and output format.
