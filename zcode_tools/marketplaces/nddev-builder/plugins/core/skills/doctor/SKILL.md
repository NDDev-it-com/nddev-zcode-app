---
name: doctor
description: Deep consistency check for the entire nddev-zcode-app repo. READ THE RULE SKILLS FIRST (repo-orientation, zcode-native-format, add-plugin, add-skill), then verify everything against them — version parity, ZCode-spec compliance, stale paths, broken commands, JSON validity, secrets safety, and installer plan. Run after ANY change to the repo. Returns a pass/fail verdict with specific findings.
---

# doctor

The repository health check. **Read the rule-skills first**, then verify the repo
against them. This skill is run after every change to catch drift early.

## Step 0 — Load the rules (read these in full before checking)

Before checking anything, read these files so you know what "correct" means:

1. `.agents/skills/repo-orientation/SKILL.md` — the repository map, three-layer
   model, where things live, the installer flow.
2. `zcode_tools/marketplaces/nddev-builder/plugins/core/references/zcode-native-format.md`
   — the ZCode native format reference (marketplace shape, plugin manifests,
   component convention-discovery, hooks, mcp).
3. `config/nddev-contract.json` — the product contract (source_root, native_format).
4. `build/manifest.json` — the declared layout, backup/restore policy.

Only after reading these can you judge whether the repo matches its own rules.

## Step 1 — Version parity

Check that these all agree on the build version:
- `VERSION`
- `build/version.json` → `build_version`
- `build/manifest.json` → `build_version`
- `pyproject.toml` → `version`
- Each `marketplace.json` plugin entry `version` == its `plugin.json` `version`

Check ZCode pin consistency:
- `build/version.json` `zcode_app_version` == `references/zcode-baseline.json` → `zcode.app_version`
- `build/version.json` `zcode_cli_version` == `references/zcode-baseline.json` → `zcode.cli_version`

Report any mismatch with file + field.

## Step 2 — ZCode spec compliance

For EVERY marketplace under `zcode_tools/marketplaces/`:

- **marketplace.json** — has `name`, `owner`, `description`, `plugins[]`. Each
  plugin entry has `name`, `source`, `description`, `version`, `author`,
  `category`, `tags`, `license`. The `name` matches the directory name.
- **plugin.json** (each plugin) — metadata-only: NO `commands`, `skills`,
  `hooks`, `mcpServers`, or `agents` arrays. `name` matches
  `^[a-z0-9][a-z0-9._-]{0,127}$`. Any declared component paths are **relative
  and inside the plugin root** (no absolute/escaping paths).
- **SKILL.md** (each) — frontmatter `name` matches the directory name.
  Frontmatter delimited by `---`. **`description` is ≤ 1024 characters** (over
  = silently dropped). Recognized keys: `name`, `description`, `when_to_use`,
  `license`, `metadata` (any other key is silently ignored).
- **commands/*.md** — filename matches `^[a-z0-9][a-z0-9_:-]{0,63}$`. Frontmatter
  has `description` (or a non-empty body). Keys are **hyphenated**
  (`allowed-tools`, not `allowed_tools`). No multi-line arrays (flat parser).
- **agents/*.md** — frontmatter has `name` and `model`.
- **cli-config.template.json** — `hooks.enabled: true`, all 7 events present,
  uses `mcp.servers` (NOT top-level `mcpServers`).
- **mcp.json** — uses `mcpServers` key (correct for the plugin/reference form).
- **hooks.json** — only the 7 supported event keys (plus `_comment`).

## Step 3 — Stale path detection

Search ALL `.md`, `.sh`, `.json`, `.yml` files for patterns that indicate the
old pre-refactor structure (these should NOT appear outside CHANGELOG history):

- `zcode_tools/marketplace.json` (old single-marketplace root)
- `zcode_tools/plugins/` WITHOUT a `marketplaces/` prefix
- `zcode_tools/AGENTS.md` (now inside marketplaces)
- `zcode_tools/cli-config`, `zcode_tools/v2-config`, `zcode_tools/mcp.json`,
  `zcode_tools/hooks.json` (now inside marketplaces)
- bare `nddev` marketplace name (the old pre-refactor name, now `nddev-builder`).
  Note: `nddev-developer` is a valid active marketplace (full-stack developer
  setup) — do NOT flag it as stale.

## Step 4 — Broken command detection

Every documented `install.sh` invocation must use the correct syntax:
`install --marketplace <name>`. Search docs and skills for bare
`install.sh --plan` or `install.sh --apply` without the `install` subcommand
and `--marketplace` — these will error.

## Step 5 — JSON validity

Validate every JSON file parses:
```bash
for f in $(find . -name '*.json' -not -path './.git/*'); do
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" || echo "INVALID: $f"
done
```

## Step 6 — Secrets safety

- No `.env` file tracked by git: `git ls-files | grep -E '(^|/)\.env$'` → must be empty.
- Every `${VAR}` placeholder in templates has a matching key in `build/.env.example`.

## Step 7 — Installer plan

EVERY marketplace must pass dry-run on both platforms:
```bash
for mp in $(ls zcode_tools/marketplaces/); do
  cli-tools/scripts/install.sh install --marketplace "$mp" --platform macos --plan
  cli-tools/scripts/install.sh install --marketplace "$mp" --platform ubuntu --plan
done
```
Every run must end with `[ok] all checks passed`.

## Step 8 — Cross-reference integrity

- `config/nddev-contract.json` `source_root`, `installer_entry`,
  `native_format.marketplace_root` match the actual structure.
- `build/manifest.json` `layout` matches reality.
- Every file path mentioned in docs (README, AGENTS, CONTRIBUTING, docs/*, the
  repo-orientation skill) actually exists.

## Output format

```
DOCTOR: PASS | FAIL

Findings:
- [PASS|FAIL] <step name>: <detail>
...
```

If any step FAILs, list the exact file:line and what's wrong. Do not fix issues
during the doctor run — only report. The caller decides what to fix.
