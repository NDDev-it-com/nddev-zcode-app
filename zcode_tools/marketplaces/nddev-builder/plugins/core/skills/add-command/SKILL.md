---
name: add-command
description: Author a new ZCode slash command (commands/<name>.md with YAML frontmatter) in the correct location inside the active marketplace. Covers frontmatter requirements, naming, and nested-command colon syntax. Use when adding a new slash command to the nddev-builder or any marketplace.
---

# add-command

Authors a new ZCode slash command.

## Where commands live

Commands live inside the active marketplace at:

```
zcode_tools/marketplaces/<marketplace>/commands/<name>.md      ← user-scope
zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/commands/<name>.md  ← plugin-scoped
```

Prefer **plugin-scoped** if the command belongs to a plugin's domain; user-scope
for cross-plugin personal commands.

## Command anatomy

A command is a single `.md` file. The filename becomes the command name:
`commands/review.md` → `/review`. Nested directories join with a colon:
`commands/review/code.md` → `/review:code`.

```markdown
---
description: <English. One sentence — what this command does and when to use it.>
---

<Body: the instructions the agent follows when the command is invoked.>
```

## Frontmatter rules

- `description` (required) — **English only**. State what the command does and
  **when** to invoke it. This is what the user sees in the `/` menu.
- No `name` field needed — the filename IS the name.
- No `version`, `tags`, or other fields.

## Procedure

1. Decide the scope (user vs plugin) and confirm the active marketplace exists.
2. Pick the command name (lowercase, hyphens, no spaces). Remember the filename
   → command-name mapping and the nested-colon rule.
3. Create the file at the chosen path.
4. Write frontmatter: `description` (English, trigger-rich).
5. Write the body: a clear, imperative set of instructions an agent follows
   when the command runs. Reference skills by name (e.g. "Follow the `add-skill`
   skill") when the command delegates to one.
6. Confirm the frontmatter is delimited by `---` fences and parses as YAML.
7. Remind that commands are **convention-discovered** — do NOT add them to any
   `plugin.json` component array.

## Rules

- English only — including the `description`.
- One `.md` file per command; the filename (with `/` → `:` for nested) is the
  invocation name.
- Do not declare commands in `plugin.json` — discovery is by convention.
- Keep the body imperative and concise — it is the agent's runbook.
