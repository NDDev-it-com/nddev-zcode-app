---
name: dev-workflow
description: How to develop the nddev-zcode-app repository — the daily workflow, conventions, and quality gates. Covers making changes, running the doctor check, testing in a temp directory, and cutting releases. Use when starting work on this repo, before committing changes, or when unsure about the development process.
---

# dev-workflow

The daily workflow for developing `nddev-zcode-app`. Read this after
`repo-orientation` (which explains what the repo IS).

## Step 1: Understand the scope

Before making changes, read:
1. `.agents/skills/repo-orientation/SKILL.md` — the repository map.
2. `AGENTS.md` — the workspace rules.
3. The specific area you're changing (e.g. a marketplace, the installer, docs).

## Step 2: Make changes

Follow the architecture: edit source files in `zcode_tools/marketplaces/<name>/`
(for setup content) or `cli-tools/` (for installer logic) or `build/` (for
version/secrets). Never edit rendered `~/.zcode` files directly.

### Conventions

- **English only** for all content.
- **Conventional commits**: `type(scope): description` (imperative, lowercase, 72 chars).
- **Plugin manifests are metadata-only** — no component arrays.
- **Convention discovery**: skills/commands/agents are found by directory structure.
- **Secrets never committed** — `${VAR}` placeholders + `build/.env` (gitignored).

## Step 3: Validate (run before every commit)

```bash
# Quick: JSON validity + plan passes + no secrets tracked
python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('**/*.json', recursive=True)]"
cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan
cli-tools/scripts/install.sh install --marketplace <name> --platform ubuntu --plan
git ls-files | grep -E '\.env$'  # must be empty
```

For a deep check, follow the `doctor` skill (in `nddev-builder/plugins/core/skills/doctor/`)
— it checks 8 axes: versions, ZCode spec, stale paths, broken commands, JSON,
secrets, installer plan, cross-references.

## Step 4: Test in a temp directory (safe, isolated)

Never test `--apply` against the live `~/.zcode` while ZCode is running. Use a
temp target:

```bash
# Full lifecycle test (install → update → switch → restore → remove):
NDDEV_TARGET=/tmp/zcode-test NDDEV_BACKUPS_DIR=/tmp/zcode-test-backups \
  cli-tools/scripts/install.sh install --marketplace <name> --platform macos --apply
```

This builds into `/tmp/zcode-test` without touching the real `~/.zcode`.

## Step 5: Commit and push

```bash
git add -A
git commit -m "type(scope): description"
git push
```

The repo has branch protection (blocks force-push and deletion). Direct pushes
to `main` are allowed for the solo maintainer.

## Step 6: Release (when behavior changes)

Follow the `release-build` skill (in `nddev-builder/plugins/core/skills/release-build/`):
1. Bump `build/version.json` + `VERSION` (default: patch `+0.0.1`).
2. Add a CHANGELOG entry.
3. Validate (Step 3).
4. Tag + push (`git tag X.Y.Z && git push --tags`).

The `release.yml` workflow verifies tag == VERSION and publishes a GitHub Release.

## How to add new things

| You want to… | Read this skill (in nddev-builder core plugin) |
|---|---|
| Add a plugin | `add-plugin` |
| Add a skill | `add-skill` |
| Add a command | `add-command` |
| Add an agent | `add-agent` |
| Add a hook | `add-hook` |
| Add an MCP/CLI tool | `add-mcp-server` |
| Add a marketplace | `add-marketplace` |
| Cut a release | `release-build` |
| Check consistency | `doctor` |

These skills are in `zcode_tools/marketplaces/nddev-builder/plugins/core/skills/`.
They are also installed as slash commands: `/nddev-add-plugin`, `/nddev-doctor`, etc.

## Common pitfalls

- **Don't hardcode marketplace names** in docs or architecture — the system is generic.
- **Don't edit `~/.zcode` directly** — always change source and re-run the installer.
- **Don't forget `hooks.events.<Event>`** (not `hooks.<Event>`) in cli-config templates.
- **Don't use `cp -R src dest`** for restore when dest exists (nesting bug) — use
  the `restore.sh` script which handles file vs dir correctly.
- **Don't run `--apply` inside a live ZCode session** — it moves `~/.zcode` out from
  under the running process.
