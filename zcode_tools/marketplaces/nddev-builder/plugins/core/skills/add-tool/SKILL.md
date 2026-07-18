---
name: add-tool
description: Add a CLI tool (non-MCP) to a plugin bundle. Creates a tools directory with an executable script and a README, plus optionally a companion skill that teaches the agent how to invoke the tool. Covers the CLI+skill pattern as a small-baseline, on-demand alternative to MCP servers that is more composable but less constrained. Use when adding a linter, formatter, utility script, or any command-line tool the agent should be able to run.
---

# add-tool

Adds a CLI tool to a plugin bundle. This "CLI+skill" pattern keeps baseline
routing metadata small and loads detailed guidance and output on demand.

## Why CLI+skill instead of MCP?

MCP servers expose tool schemas at session scope. A CLI tool plus a concise
companion skill keeps only compact routing metadata in the baseline context;
the skill body, command guidance, and output are consumed when the tool is
needed. The exact footprint depends on the client and integration surface.

## Layout

```text
plugins/<plugin>/
  tools/
    <tool-name>/
      README.md           ← what the tool does, how to run it
      <tool-name>.sh      ← the executable script (or .js, .py)
  skills/
    <tool-name>/          ← optional companion skill (teaches the agent)
      SKILL.md
```

## Procedure

1. Ask the user for:
   - The marketplace name.
   - The plugin name (must exist).
   - The tool name (kebab-case).
   - The script language: `bash`, `python`, or `node`.
   - A one-sentence description of what the tool does.
   - Whether to create a companion skill (recommended).

2. Create the directory:

   ```bash
   mkdir -p zcode_tools/marketplaces/<mp>/plugins/<plugin>/tools/<name>
   ```

3. Write the script (`<name>.sh`, `<name>.py`, or `<name>.js`):
   - **bash**: start with `#!/usr/bin/env bash` and `set -euo pipefail`.
   - **python**: start with `#!/usr/bin/env python3`.
   - Make it executable: `chmod +x <script>`.

4. Write `README.md` in the tool directory:
   - One-line purpose.
   - Usage: `./<name>.sh [args]` with flags documented.
   - Examples (at least 2).
   - Output format description.
   - Dependencies (if any).

5. **Companion skill** (recommended): create
   `skills/<name>/SKILL.md` with frontmatter (`name`, `description` — explain
   WHEN to use it). The body should contain: available commands, when to use
   each, examples, output format. **Point it at the absolute installed path**
   `~/.zcode/marketplaces/<mp>/plugins/<plugin>/tools/<name>/<script>` — the
   `tools/` directory is **not** flattened to user scope, and
   `${CLAUDE_PLUGIN_ROOT}` is unset for a file-installed marketplace, so a
   relative or `${CLAUDE_PLUGIN_ROOT}`-based path will not resolve. The skill
   itself *is* flattened, so it loads and can carry that absolute path.

6. **Secrets**: if the tool needs API keys or tokens:
   - Add the supported key to `build/.env.example` with an empty value.
   - Accept the real value through the process environment supplied by the
     active project's approved launcher, secrets manager, or environment
     helper.
   - Never execute an env file with `source`, `.`, or `eval`. If the project
     provides a non-evaluating env parser, accept only explicitly allowlisted
     keys.
   - Never hardcode, print, trace, or include secret values in errors.

7. Validate:

   ```bash
   cli-tools/scripts/install.sh install --marketplace <mp> --platform macos --plan
   ```

8. Test the script runs (at least `--help` or a dry-run mode).

## Rules

- Scripts must be executable (`chmod +x`).
- Secrets arrive through an approved process environment; never shell-source
  env files or hardcode secrets in the script.
- The companion skill is the agent's entry point — the script is the engine.
- Do NOT declare tools in `plugin.json` — convention discovery.
- English only for all content (scripts, README, skill).
- Keep the companion skill token-thin (description + commands + examples).
