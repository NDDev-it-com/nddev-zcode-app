---
name: add-instructions
description: Authors and maintains ZCode AGENTS.md instruction files at user or workspace scope. Use when adding default agent instructions, editing AGENTS.md, deciding user-vs-workspace scope, or reasoning about the load and merge order of instruction files in ZCode.
---

# Add or maintain AGENTS.md instructions

`AGENTS.md` is ZCode's instruction surface — broad behavior rules injected into
the model context. It is not a skill, command, hook, MCP server, or plugin; it
has its own two scopes and a defined merge order.

## Scopes and load order

| Scope | File | Applies to | Loads |
|---|---|---|---|
| User | `~/.zcode/AGENTS.md` | every workspace | first |
| Workspace | `<repo>/AGENTS.md` | that project only | after user (can narrow/override) |

ZCode injects `~/.zcode/AGENTS.md` first, then the workspace `AGENTS.md` resolved
from the current directory upward to the project root — so workspace rules
appear later and take precedence for that repo.

A marketplace ships its own `AGENTS.md` at its root; the installer renders it to
`~/.zcode/AGENTS.md` (user scope). Edit the marketplace's `AGENTS.md` to change
the installed user-scope defaults.

## Choosing scope

- **User** (`~/.zcode/AGENTS.md`, i.e. the marketplace `AGENTS.md`): personal or
  setup-wide defaults — preferred language, review style, local conventions.
- **Workspace** (`<repo>/AGENTS.md`): repository rules shared with the team —
  architecture boundaries, logging, testing, commit/MR policy. Create or update
  it with ZCode's built-in `/init` (it targets the workspace file, never the
  user default).

## Procedure

1. Decide scope from the rule's reach (setup-wide vs repository-specific).
2. Keep it concise and imperative; state rules the model must follow, not prose.
3. If a marketplace uses managed begin/end markers around a generated block,
   keep edits inside the markers so the installer can re-render cleanly.
4. Do not put skills, commands, hooks, MCP, or plugin config here — those are
   separate resources (see `nddev-builder-orientation`). AGENTS.md is
   instructions only.
5. Verify the file is valid Markdown and loads (open ZCode, or check the
   rendered `~/.zcode/AGENTS.md` after install).
