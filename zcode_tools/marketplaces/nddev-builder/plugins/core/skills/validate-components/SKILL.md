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
6. **Hook schema** — every authored hook (in `hooks.json` or the rendered
   `hooks` block) names one of the **seven** supported events — `SessionStart`,
   `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`,
   `PostToolUseFailure`, `Stop` — and keeps its handler fields pure: a
   `type:"command"` handler carries `timeout` (**seconds**), a `type:"process"`
   handler carries `timeoutMs` (**milliseconds**); never mix the two on one
   handler.
7. **MCP strict schema** — in every `.mcp.json`, each server's `command` is a
   **string, not an array**, there are **no unknown top-level keys** per server,
   and the field names are exactly `env` / `headers` / `enabled`. Getting these
   wrong drops the server silently or crashes the parser.
8. **Placeholder integrity** — every `${VAR}` referenced in the setup's
   templates (`*.template.json`, `mcp.json`, `hooks.json`) must appear in
   `build/.env.example`. An undeclared placeholder has no source value at render
   time, leaving that field empty in the rendered config.
9. **Inert-field warning (WARN, not fail)** — warn if any
   `.zcode-plugin/plugin.json` authors `lspServers`, `outputStyles`, `channels`,
   or `settings`: ZCode 3.3.6 records but never executes them, so they are dead
   config, not an install-blocking error.

Checks 6-9 encode the ZCode-native execution model, hook, and MCP-schema rules;
see `../../references/zcode-native-format.md` for the authoritative detail.

## Procedure

1. Walk `plugins/*/` and collect skills, commands, agents.
2. Apply checks 1-3 per component; report each failure with its file.
3. Apply check 4 across all plugins; report any duplicate basename as a
   **blocking** error (the install would fail closed).
4. Apply check 5 (JSON validity) to every JSON file, then the schema checks —
   6 (hook events and handler purity), 7 (`.mcp.json` strict schema), and 8
   (placeholder integrity against `build/.env.example`) — as blocking failures,
   and check 9 (inert `plugin.json` fields) as a **warning** only.
5. As a final gate, run `install.sh install --setup <mp> --plan` — the planner
   re-runs the staged verification without mutating anything.
