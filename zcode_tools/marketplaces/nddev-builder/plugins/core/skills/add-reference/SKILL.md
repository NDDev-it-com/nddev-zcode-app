---
name: add-reference
description: Adds a reference documentation file — a spec, format reference, or design doc — under a plugin's references/ directory. Use when adding background documentation that plugin skills and commands should cite. Reference docs are plain Markdown, not a loadable component type.
---

# add-reference

Adds a reference document to a plugin bundle.

## Where references live

```
plugins/<plugin>/
  references/
    <doc-name>.md    ← a reference document
```

References are plain Markdown files. They are NOT components (not skills, not
commands, not agents) — they are documentation that skills and commands can
reference by path. The `core` plugin has `references/zcode-native-format.md`
as an example.

## Procedure

1. Ask the user for:
   - The marketplace name.
   - The plugin name (must exist — confirm `plugins/<plugin>/` is present).
   - The reference document name (kebab-case, e.g. `api-contract`,
     `design-tokens`).

2. Create the directory if it does not exist:
   ```bash
   mkdir -p zcode_tools/marketplaces/<mp>/plugins/<plugin>/references
   ```

3. Write the reference file:
   `zcode_tools/marketplaces/<mp>/plugins/<plugin>/references/<name>.md`

   Start with a top-level `# <name>` heading. Write the content as clear,
   dense reference documentation (tables, code blocks, field lists). This is
   NOT a procedure — it is a spec that other skills cite.

4. Remind the user that references are NOT declared in `plugin.json` — they
   are discovered by convention (any `.md` under `references/`).

5. Validate the file exists and is non-empty:
   ```bash
   test -s zcode_tools/marketplaces/<mp>/plugins/<plugin>/references/<name>.md
   ```

6. Run the installer plan to confirm nothing broke:
   ```bash
   cli-tools/scripts/install.sh install --marketplace <mp> --platform macos --plan
   ```

## Rules

- References are Markdown only — no frontmatter needed (they are not skills).
- Do NOT add reference paths to `plugin.json` — convention discovery.
- One `.md` file per reference topic.
- English only.
- Keep references dense and useful — they consume context when cited.
