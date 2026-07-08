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
`commands/review/code.md` → `/review:code` (NOT `/review/code`).

```markdown
---
description: <English. One sentence — what this command does and when to use it.>
---

<Body: the instructions the agent follows when the command is invoked.>
```

## Filename rules (strict)

The filename must match `^[a-z0-9][a-z0-9_:-]{0,63}$`:
- Lowercase alphanumeric start.
- Allowed chars: `a-z 0-9 _ : -` (no spaces, no dots, no uppercase).
- Max **64 characters**.
- Violation → command silently dropped.

## Frontmatter rules (flat parser)

The frontmatter is a **flat key:value parser** — indented keys are silently
ignored, and multi-line YAML arrays are dropped. Keep every value on ONE line.

Recognized keys (all **hyphenated**, NOT snake_case):
- `description` — English, what the command does. If omitted, the first
  non-empty body line is used. If BOTH are empty → command dropped.
- `argument-hint` (optional) — hint text for the `/` menu.
- `allowed-tools` (optional) — inline comma list, e.g. `Read, Bash`. NOT multi-line.
- `model` (optional) — model override.
- `skills` (optional) — auto-mounted skills.

**Do NOT use snake_case** (`allowed_tools`, `argument_hint`) — they are silently
ignored. No `version`, `name`, or `tags`.

## Argument substitution

If the command accepts arguments, use `$ARGUMENTS` (full string) or `$1`, `$2`
(positional). Note: `${ARGUMENTS}` (braces form) is **NOT recognized** — use
`$ARGUMENTS`.

## Procedure

1. Decide the scope (user vs plugin) and confirm the active marketplace exists.
2. Pick the command name — must match `^[a-z0-9][a-z0-9_:-]{0,63}$`. Remember
   the filename → command-name mapping and the nested-colon rule.
3. Create the file at the chosen path.
4. Write frontmatter: `description` (English, one line). Use hyphenated keys
   only. Keep everything flat (no multi-line arrays).
5. Write the body: a clear, imperative set of instructions. Reference skills by
   name when the command delegates. Use `$ARGUMENTS`/`$1` for args (not braces).
6. Confirm the frontmatter is delimited by `---` fences and parses.
7. Remind that commands are **convention-discovered** — do NOT add them to any
   `plugin.json` component array.

## Rules

- English only — including the `description`.
- One `.md` file per command; the filename (with `/` → `:` for nested) is the
  invocation name.
- Do not declare commands in `plugin.json` — discovery is by convention.
- Keep the body imperative and concise — it is the agent's runbook.
