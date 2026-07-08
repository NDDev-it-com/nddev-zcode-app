---
name: add-hook
description: Register a lifecycle hook in the active marketplace's hooks.json and wire its command script. Covers the seven ZCode hook events, the matcher + command shape, the hooks.enabled flag, and how the installer merges hooks into cli/config.json. Use when adding a SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, or Stop hook.
---

# add-hook

Registers a ZCode lifecycle hook in the active marketplace.

## The seven events

ZCode supports exactly these events (no others):

| Event | Fires when |
|---|---|
| `SessionStart` | a new session begins |
| `UserPromptSubmit` | the user submits a prompt |
| `PreToolUse` | before a tool runs (match by tool name) |
| `PermissionRequest` | a permission is requested |
| `PostToolUse` | after a tool runs successfully |
| `PostToolUseFailure` | after a tool fails |
| `Stop` | the session stops |

## Where hooks live

Hooks are defined in the active marketplace's `hooks.json`:

```
zcode_tools/marketplaces/<marketplace>/hooks.json
```

The installer merges these into `~/.zcode/cli/config.json` under the `hooks` key
(requires `hooks.enabled: true`, which the template already sets).

## Hook entry shape

Each event key holds an array of hook entries. A hook entry is:

```json
{
  "matcher": "<ToolName|.*>",
  "hooks": [
    {
      "type": "command",
      "command": "<shell command>"
    }
  ]
}
```

- `matcher` — for `PreToolUse`/`PostToolUse`/`PostToolUseFailure`/`PermissionRequest`,
  a tool name to match (e.g. `"Bash"`, `"Edit"`). Use `".*"` or omit to match all tools.
  Ignored for `SessionStart`/`UserPromptSubmit`/`Stop`.
- `command` — a shell command. It receives event context via stdin (JSON) and its
  exit code / stdout feed back into the session (exit 2 blocks the action for
  PreToolUse; stdout is shown to the model).

## Procedure

1. Identify the event and the tool to match (if applicable).
2. Write the hook command — a shell one-liner or a script path. If the logic is
   non-trivial, put it in a script under the marketplace (e.g.
   `zcode_tools/marketplaces/<marketplace>/scripts/<name>.sh`) and reference it
   by path.
3. Open `hooks.json` in the active marketplace and add the entry to the matching
   event array. Strip the `_comment` key mentally — the installer drops it at
   merge time.
4. Confirm `hooks.json` is valid JSON after editing.
5. Remind: `hooks.enabled: true` must be set in `cli-config.template.json`
   (it already is by default). The installer merges `hooks.json` → `cli/config.json`
   at install time, so the hook takes effect on the next `install --apply`.

## Example

```json
{
  "_comment": "...",
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        { "type": "command", "command": "scripts/block-dangerous.sh" }
      ]
    }
  ]
}
```

## Rules

- English only for any comments or docs.
- Only the seven listed events — no others.
- The installer merges `hooks.json` into `cli/config.json` at install time.
- `hooks.enabled: true` is required (set in the template).
- Keep hook commands fast — they run on every matched event.
