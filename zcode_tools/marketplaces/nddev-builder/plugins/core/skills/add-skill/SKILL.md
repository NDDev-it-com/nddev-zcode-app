---
name: add-skill
description: Author a new ZCode skill (SKILL.md with YAML frontmatter) in the correct location — either inside a plugin bundle or at user scope. Covers frontmatter requirements, discovery order, and naming. Use when adding a skill to the nddev-zcode-app setup; use add-command for a slash command and add-agent for a subagent.
---

# add-skill

Authors a new ZCode skill in the correct place.

## Where skills live

| Scope | Location (source) | Installed to |
|---|---|---|
| Plugin-scoped | `zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/skills/<skill>/SKILL.md` | `~/.zcode/marketplaces/<marketplace>/plugins/<plugin>/skills/<skill>/` |
| User-scoped | `zcode_tools/marketplaces/<marketplace>/skills/<skill>/SKILL.md` | `~/.zcode/skills/<skill>/` |

Prefer **plugin-scoped** for anything tied to a plugin's domain; user-scoped only for
personal cross-project skills.

Slash commands and subagents are different component types with their own
frontmatter contracts: use `add-command` and `add-agent` respectively.

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

Recognized frontmatter keys (anything else is silently ignored):
- `name` (required) — must match the directory name. Lowercase kebab-case.
- `description` (required) — **English only** for this repo. State what the skill
  does and **when** an agent should load it. **Hard limit: 1024 characters — a
  description longer than 1024 chars causes the skill to be DROPPED entirely**
  (not truncated). However, only the first **~250 characters** are shown to the
  model for triggering, so front-load the trigger wording there. Be "pushy" —
  describe contexts where the skill applies even if the user doesn't say the
  exact keyword.
- `when_to_use` (optional) — additional trigger context, also shown to the model.
- `license`, `metadata` (optional, reserved) — rarely needed.

Do NOT invent `version`, `tags`, or `allowed-tools` — they are not recognized keys.

**Critical pitfalls:**
- Description > 1024 chars → skill silently dropped.
- Indented frontmatter keys are silently ignored — keep keys at column 0.
- Multi-line values need `>` or `|` block scalars (flat parser, no flow YAML).

## Discovery order (why location matters)

ZCode scans in this order; the first same-named skill wins:

1. Explicitly configured roots (if any) →
2. User `~/.zcode/skills` → 3. `~/.agents/skills` →
4. workspace `.zcode/skills` (deeper cwd location wins) →
5. workspace `.agents/skills` → 6. enabled **plugin** roots.

So a user-scope skill shadows a plugin skill of the same name. Pick unique names.

## Procedure

1. Decide scope (plugin vs user). If plugin, confirm the plugin exists.
2. Create `skills/<name>/SKILL.md` (or `plugins/<plugin>/skills/<name>/SKILL.md`).
3. Write frontmatter: `name` (matches dir), `description` (English, trigger-rich).
4. Write the body: a clear procedure an agent can follow.
5. Validate the YAML parses (a missing `---` fence is the most common error).
6. Validate: `cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan`.
7. Bump version + changelog if this is a release behavior change.

## Rules

- English only — including the `description`.
- One subfolder per skill; the folder name == the `name` field.
- A skill is a folder; a command and a subagent are flat `.md` files with their
  own required frontmatter (see `add-command` and `add-agent`).
- Don't declare skills in `plugin.json` — they are convention-discovered.
