---
name: add-skill
description: Authors a ZCode skill (SKILL.md) inside a plugin bundle or at user scope. Use when adding a skill or teaching the agent a reusable workflow. For a slash command use add-command; for a subagent use add-agent.
---

# add-skill

Authors a new ZCode skill in the correct place.

## Where skills live

Author a skill inside a plugin bundle; the installer is what makes ZCode load
it. **ZCode 3.3.6 never loads skills from `~/.zcode/marketplaces/.../plugins/`** —
it loads user-scope skills only from `~/.zcode/skills/` (and `~/.agents/skills/`).
So the installer **flattens** every plugin's `skills/` into `~/.zcode/skills/`
(`cli-tools/scripts/lib/build.sh`, `flatten_plugin_components`); that flattened
copy is what actually loads.

| Scope | Location (source) | What ZCode loads |
|---|---|---|
| Plugin-scoped | `.../plugins/<plugin>/skills/<skill>/SKILL.md` | `~/.zcode/skills/<skill>/` (installer-flattened) |
| User-scoped | `.../<marketplace>/skills/<skill>/SKILL.md` | `~/.zcode/skills/<skill>/` (copied as-is) |

Prefer **plugin-scoped** so the skill travels with its plugin's domain;
user-scoped only for personal cross-project skills. Either way the loaded copy
lands in `~/.zcode/skills/`.

> **Global uniqueness is mandatory.** Because the flatten collapses every
> plugin's `skills/` into one `~/.zcode/skills/`, a skill basename must be unique
> across *every plugin in the marketplace*, not just within its plugin. A
> cross-plugin name clash makes the install **fail closed** (see the collision
> guard in `flatten_plugin_components`), not silently shadow one.

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

The installer delivers our skills to level 2 (`~/.zcode/skills`). Level 6
(plugin roots) is reached **only** by marketplaces added through the ZCode UI —
a headless file-install never populates it, which is exactly why the installer
flattens to user scope instead. A user-scope skill shadows any same-named skill
below it, so keep basenames unique.

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
