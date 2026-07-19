---
name: getting-started
description: A guided first run of the nddev-builder toolkit — from zero to a working, validated ZCode plugin or marketplace in ordered steps. Use when new to nddev-builder, onboarding, or unsure which skill to start with.
---

# getting-started

The fastest correct path from nothing to a working, installed ZCode extension.
Pick a path below; each step hands off to a focused skill.

## The one thing to understand first

Read `nddev-builder-orientation` once. The fact that governs everything: ZCode
3.3.6 loads extensions only from **user scope** (`~/.zcode/{skills,commands,agents}`),
and this repo's installer **flattens** each plugin's components there. You author
inside a marketplace; the installer makes it live. There is no CLI `plugin add`.

## Path 1 — add one component to an existing setup

1. Choose the setup (marketplace): `nddev-builder`, `nddev-designer`, or your own.
2. Run the matching skill: `add-skill`, `add-command`, `add-agent`, `add-hook`,
   `add-mcp-server`, `add-provider`, `add-tool`, `add-instructions`, or
   `add-reference`.
3. Pre-check with `validate-components`, then prove it loads with `devtest-plugin`.

## Path 2 — build a whole plugin from an idea

1. `scaffold-plugin` — compose the bundle (manifest plus the components the idea
   needs) from intent.
2. `validate-components` → `devtest-plugin` → `release-review`.
3. Ship: bump the five version sources plus `CHANGELOG.md`; use
   `publish-marketplace` if others should install it.

## Path 3 — start a new setup / marketplace from scratch

1. `add-marketplace` — scaffold the self-contained `~/.zcode` build source.
2. Add plugins with `add-plugin` or `scaffold-plugin`.
3. `validate-components` → `release-review` → `publish-marketplace`.

## Need several agents to cooperate?

Use `orchestrate-subagents` to design a multi-subagent workflow within ZCode's
limits (user-scope, foreground, parallel-yes / background-no).

## Golden rules (from day one)

- Every skill/command/agent basename is unique across the marketplace — the
  flatten fails closed on a collision.
- Plugin manifests are metadata-only; author only executed fields (`commands`,
  `skills`, `hooks`, `mcpServers`, and user-scope `agents`).
- Front-load each skill `description` with a concrete "Use when …" (the first
  ~250 characters carry the routing weight).
- English only; never commit secrets or machine-local paths.
- Static validation is necessary but not sufficient — `devtest-plugin` proves it
  loads.

## Where to go deeper

`nddev-builder-orientation` for the full loading model, and
`../../references/zcode-native-format.md` for every component's exact rules.
