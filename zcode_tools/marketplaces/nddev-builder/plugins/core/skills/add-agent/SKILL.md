---
name: add-agent
description: Author a new ZCode subagent (agents/<name>.md with name + model frontmatter) in the correct location inside the active marketplace. Covers role definition, model pinning, and output contracts. Use when adding a subagent (reviewer, researcher, worker) to the nddev-builder or any marketplace.
---

# add-agent

Authors a new ZCode subagent.

## Where agents live

Agents live inside the active marketplace at:

```
zcode_tools/marketplaces/<marketplace>/agents/<name>.md                    ← user-scope
zcode_tools/marketplaces/<marketplace>/plugins/<plugin>/agents/<name>.md   ← plugin-scoped
```

## Agent anatomy

A subagent is a single `.md` file with YAML frontmatter:

```markdown
---
name: <agent-name>
model: GLM-5.2
description: <English. What this agent does and when to delegate to it.>
---

<Body: the system prompt for the subagent — its role, constraints, and output format.>
```

## Frontmatter rules

- `name` (required) — must match the filename (without `.md`).
- `model` (required) — pin the model. Use `GLM-5.2` (the ZCode runtime baseline)
  unless there is a deliberate reason for a different model.
- `description` (recommended) — English, trigger-rich. Explains WHEN to delegate.
- No other fields.

## Body: the system prompt

The body IS the subagent's system prompt. Write it as a complete role definition:

1. **Role** — one sentence: "You are a strict reviewer for…", "You are a
   researcher that…".
2. **Task / checklist** — what the agent checks or produces. Be specific and
   exhaustive.
3. **Constraints** — what the agent must NOT do (e.g. "do not edit files, only
   report", "do not push", "read-only").
4. **Output format** — a fixed template the agent returns (e.g. `VERDICT: PASS
   | FAIL` with findings). This makes the output parseable by the caller.

## Procedure

1. Decide the scope (user vs plugin) and confirm the active marketplace exists.
2. Pick the agent name (lowercase, hyphens). The filename must match the
   `name` field.
3. Create `agents/<name>.md`.
4. Write frontmatter: `name` (matches filename), `model: GLM-5.2`, `description`.
5. Write the body as a complete role definition (role → checklist → constraints
   → output format).
6. Confirm the frontmatter parses as valid YAML.
7. Remind that agents are **convention-discovered** — do NOT add them to any
   `plugin.json` component array.

## Rules

- English only — including the `description` and body.
- `name` must match the filename; `model` must be `GLM-5.2` by default.
- The body is a system prompt — be specific about role, constraints, and output.
- Convention-discovered: no `agents` array in `plugin.json`.

## After creating

- Validate: `cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan`.
- Validate the same marketplace with `--platform ubuntu --plan`.
- Before a repository release, use one strict SemVer in `VERSION`, the
  `build_version` fields in `build/version.json` and `build/manifest.json`, the
  `nddev-builder` marketplace `core` entry, and the core plugin manifest; also
  update `CHANGELOG.md`.
