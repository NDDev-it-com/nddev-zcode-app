---
name: devtest-plugin
description: Runs an isolated install-and-verify loop for a marketplace using temporary HOME and ZCODE_HOME, proving components flatten and load without touching live ~/.zcode. Use to behaviorally test a plugin during development, after static validation.
---

# devtest-plugin

Prove a marketplace actually installs and its components load — in throwaway
state, never against the owner's live `~/.zcode`.

## What ZCode does and does NOT provide (read this first)

ZCode 3.3.6 has **no** `zcode plugin add`, no plugin cache, no `/plugins`
command, and no developer-mode hot reload. Headless activation is the installer
**flattening** each plugin's `skills/`, `commands/`, and `agents/` into
`~/.zcode/{skills,commands,agents}`; UI activation (Discover → +) is a separate,
non-scriptable path. So this loop is install-and-inspect, not a CLI cache-buster.
See `nddev-builder-orientation`.

## Procedure

1. **Static gate.** `validate-components` must pass first.
2. **Isolate.** Create a temporary directory and point both `HOME` and
   `ZCODE_HOME` into it. Never run against the real `~/.zcode`.
3. **Plan.** `install.sh install --setup <mp> --target <tmp> --plan` — read-only
   staged verification; it must report a clean plan.
4. **Apply.** `install.sh install --setup <mp> --target <tmp> --apply` into the
   isolated target.
5. **Assert the flatten.** Confirm each expected skill, command, and agent
   basename now exists exactly once under the isolated
   `~/.zcode/{skills,commands,agents}`, and that `references/` and `tools/` were
   NOT flattened.
6. **Reload to observe.** Component discovery is read at startup; a running ZCode
   must be restarted to pick up changes. Note this rather than expecting a live
   reload.
7. **Tear down.** Remove the temporary state; the loop leaves no trace in live
   user state.

## Rules

- Never touch live `HOME` or `~/.zcode`; always isolated temporary state.
- Static validation (`validate-components`) precedes every behavioral run.
- Report exactly what installed and loaded; a static pass is not a load proof.
