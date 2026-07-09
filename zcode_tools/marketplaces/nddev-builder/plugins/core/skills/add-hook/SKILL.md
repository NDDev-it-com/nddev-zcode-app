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

Each event key holds an array of hook entries. There are **two hook types** —
do not mix their fields (mixing → hook silently dropped):

### type: "command" (shell)

```json
{
  "matcher": "<regex>",
  "hooks": [
    {
      "type": "command",
      "command": "<shell command>",
      "timeout": 30,
      "timeoutMs": 30000,
      "statusMessage": "Running check..."
    }
  ]
}
```

- `command` — a shell string. Runs via the shell.
- `timeout` — **SECONDS** (e.g. `30` = 30 seconds). ⚠️ Not milliseconds!
- `timeoutMs` — **MILLISECONDS** (takes precedence over `timeout` if both set).
- `shell` — optional; override the shell path (default: `/bin/sh` on POSIX).
- `statusMessage` — optional; text shown while the hook runs.
- `async` — has NO runtime effect (ignored).

### type: "process" (no shell, most portable)

```json
{
  "matcher": "<regex>",
  "hooks": [
    {
      "type": "process",
      "command": "/usr/bin/python3",
      "args": ["-c", "print('ok')"],
      "timeoutMs": 5000
    }
  ]
}
```

- `command` — an executable path (not a shell string).
- `args` — array of string arguments.
- `timeoutMs` — **MILLISECONDS** (e.g. `5000` = 5 seconds). ⚠️ Not seconds!
- Accepts ONLY `command`, `args`, `timeoutMs` — no other fields.

**⚠️ Critical timeout asymmetry:** `command.timeout` is in SECONDS, but
`process.timeoutMs` is in MILLISECONDS. A value of `500` means 500 seconds for
a command hook but 500ms (half a second) for a process hook. Default is 60000ms
(60 seconds) if neither is set.

### matcher (case-sensitive REGEX)

`matcher` is a **case-sensitive regular expression** tested against the match value:
- Tool events (`PreToolUse`/`PostToolUse`/`PostToolUseFailure`/`PermissionRequest`):
  matched against the tool name (`Bash`, `Read`, `Write`, `Edit`, `Agent`).
  Aliases: `Task`↔`Agent`, `Write`/`Edit`↔`ApplyPatch`. `"bash"` will NOT match `Bash`.
- `SessionStart`: matched against `startup`/`resume`/`clear`/`compact`.
- `UserPromptSubmit`: matched against the prompt text.
- `Stop`: matched against the response preview.
- Omitted matcher = match all. Invalid regex = never matches (silently).

### Output and exit codes

- **stdout** is parsed as **strict JSON** — any extra/unknown key fails validation.
  Use the documented keys only (e.g. `{"decision": "block", "reason": "..."}`).
- **exit codes**: `0` = pass, `2` = block (deny for PreToolUse/PermissionRequest),
  any other non-zero = error. Non-JSON stdout is shown to the model as context.

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

## After creating

- Validate: `cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan`.
- Validate the same marketplace with `--platform ubuntu --plan`.
- Before a repository release, use one strict SemVer in `VERSION`, the
  `build_version` fields in `build/version.json` and `build/manifest.json`, the
  `nddev-builder` marketplace `core` entry, and the core plugin manifest; also
  update `CHANGELOG.md`.
