---
name: validate-components
description: Validates a marketplace's components statically before install, so an authoring mistake fails at author time instead of install time. Use before installing or shipping a marketplace, or when a skill, command, or agent is being rejected or silently dropped.
---

# Validate marketplace components

Catch authoring mistakes before `install`, especially the ones that abort a
build. Run these checks against a marketplace source tree.

## What to check (and the ZCode rule behind each)

1. **Skill frontmatter** — each `plugins/<p>/skills/<n>/SKILL.md` opens and
   closes with `---`, parses as YAML, has `name` equal to its directory, and a
   non-empty `description` of **≤ 1024 characters** (ZCode drops a skill whose
   `name`/`description` is missing or over-length). Only the first ~250
   characters of the description drive triggering — front-load the "use when".
2. **Command frontmatter** — each `plugins/<p>/commands/<n>.md` filename matches
   `^[a-z0-9][a-z0-9_:-]{0,63}$`; recognized keys are hyphenated
   (`description`, `argument-hint`, `allowed-tools`, `model`, `skills`,
   `disable-noninteractive`); a nested command uses a colon (`review:code`), not
   a slash; `description` or a body is present.
3. **Agent frontmatter** — each `plugins/<p>/agents/<n>.md` has the fields your
   marketplace policy requires (this toolkit uses `name` + `model` +
   `description`); it loads only after the installer flattens it to
   `~/.zcode/agents`.
4. **Cross-plugin basename uniqueness (fail-closed)** — the installer flattens
   every plugin's `skills/`, `commands/`, and `agents/` into a single
   `~/.zcode/{skills,commands,agents}` each, and **aborts on a duplicate
   basename**. Verify no two plugins in the marketplace share a skill, command,
   or agent name. This is the single most common install-time abort.
5. **JSON validity** — `marketplace.json`, every `.zcode-plugin/plugin.json`,
   and the `*.template.json` / `mcp.json` / `hooks.json` files parse; each
   `plugins[].source` is a relative path that exists.

## Procedure

1. Walk `plugins/*/` and collect skills, commands, agents.
2. Apply checks 1-3 per component; report each failure with its file.
3. Apply check 4 across all plugins; report any duplicate basename as a
   **blocking** error (the install would fail closed).
4. Apply check 5 to every JSON file.
5. As a final gate, run `install.sh install --setup <mp> --plan` — the planner
   re-runs the staged verification without mutating anything.
