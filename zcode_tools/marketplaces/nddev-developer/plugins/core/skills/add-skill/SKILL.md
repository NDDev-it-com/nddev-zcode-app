---
name: add-skill
description: Author a new ZCode skill (SKILL.md with YAML frontmatter) in the correct location — either inside a plugin bundle or at user scope. Covers frontmatter requirements, discovery order, and naming. Use when adding a skill, command, or subagent to the nddev-zcode-app setup.
---

# add-skill

Authors a new ZCode skill in the correct place.

## Where skills live

| Scope | Location (source) | Installed to |
|---|---|---|
| Plugin-scoped | `zcode_tools/plugins/<plugin>/skills/<skill>/SKILL.md` | `~/.zcode/plugins/<plugin>/skills/<skill>/` |
| User-scoped | `zcode_tools/skills/<skill>/SKILL.md` | `~/.zcode/skills/<skill>/` |

Prefer **plugin-scoped** for anything tied to a plugin's domain; user-scoped only for
personal cross-project skills.

Commands live at `commands/<name>.md` and agents at `agents/<name>.md` (same scope rules).

## Skill anatomy

A skill is a directory containing a `SKILL.md` with YAML frontmatter:

```
skills/
  my-skill/
    SKILL.md          ← required
```

```markdown
---
name: my-skill
description: <English prose. Explain WHEN to use it. Include trigger verbs.>
---

# my-skill

<Body: procedure, rules, examples. Markdown.>
```

## Frontmatter rules

- `name` (required) — must match the directory name. Lowercase, hyphens.
- `description` (required) — **English only** for this repo. State what the skill does
  and **when** an agent should load it. This field is what triggers auto-discovery, so be
  specific about the situations it handles.
- No other fields are required. Do not invent `version`, `tags`, or `allowed-tools`.

## Discovery order (why location matters)

ZCode scans in this order; the first same-named skill wins:

1. User `~/.zcode/skills` → 2. `~/.agents/skills` → 3. workspace `.zcode/skills`
   → 4. workspace `.agents/skills` → 5. enabled **plugin** roots.

So a user-scope skill shadows a plugin skill of the same name. Pick unique names.

## Procedure

1. Decide scope (plugin vs user). If plugin, confirm the plugin exists.
2. Create `skills/<name>/SKILL.md` (or `plugins/<plugin>/skills/<name>/SKILL.md`).
3. Write frontmatter: `name` (matches dir), `description` (English, trigger-rich).
4. Write the body: a clear procedure an agent can follow.
5. Validate the YAML parses (a missing `---` fence is the most common error).
6. Bump version + changelog if this is a release behavior change.

## Rules

- English only — including the `description`.
- One subfolder per skill; the folder name == the `name` field.
- Commands are flat `.md` files; agents are flat `.md` files.
- Don't declare skills in `plugin.json` — they are convention-discovered.
