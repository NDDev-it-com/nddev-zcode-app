---
description: Register a lifecycle hook in the active marketplace's hooks.json and wire its command.
---

Register a ZCode lifecycle hook.

Follow the `add-hook` skill exactly:

1. Ask which of the 7 events (SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, Stop) and which tool to match (if applicable).
2. Write the hook command — a shell one-liner or a script under `zcode_tools/marketplaces/<marketplace>/scripts/<name>.sh`. Make scripts executable.
3. Open `hooks.json` in the active marketplace and add the entry to the matching event array (matcher + hooks[{type:"command", command:"..."}]).
4. Validate `hooks.json` is valid JSON.
5. Remind that `hooks.enabled: true` must be set in `cli-config.template.json` (it is by default) and the hook takes effect on the next `install --apply`.
