# nddev-zcode-app — project memory index

> Serena durable project memory. Add domain-specific memories as
> `<DOMAIN>-<NN>-<TOPIC>.md` siblings. This index is the entry point.

Last updated: 2026-07-09
Last commit: 5a6dcd3

## Project

`nddev-zcode-app` — build system + installer that recreates a complete,
version-stamped `~/.zcode` from source on macOS (desktop) and Ubuntu
(desktop/server). Not a runtime; produces `~/.zcode`.

## Architecture (three layers)

- `zcode_tools/marketplaces/` — SOURCE: the complete desired `~/.zcode` as editable files.
- `cli-tools/` — INSTALLER: renders `zcode_tools/` into `~/.zcode`.
- `build/` — ARTIFACTS: version.json, manifest.json, system/, secrets templates.

## Current marketplaces (3)

- **nddev-builder** — development toolkit (core plugin: 18 skills, 18 commands, 1 agent).
  Used to build and maintain all other marketplaces.
- **nddev-designer** — designer setup (placeholder).
- **nddev-developer** — full-stack developer setup (placeholder).

## Key facts

- Build version source (4 files, must always agree): `VERSION`, `build/version.json`,
  `build/manifest.json`, `pyproject.toml`.
- Core plugin version (2 files, independent of build version): `marketplace.json`
  plugins[] entry + `plugins/core/.zcode-plugin/plugin.json`.
- Backup convention: `~/.zcode-backups/<N>-<VERSION>-old.zcode` (10 slots 0-9;
  oldest overwritten when full, regardless of version).
- Secrets: `build/.env.example` (committed) → `build/.env` (gitignored); `${VAR}`
  placeholders rendered at install time.
- ZCode plugin components are convention-discovered (skills/commands/agents);
  MCP uses `{"mcpServers":{}}`; hooks need `hooks.enabled: true` + `hooks.events.<Event>`.
- Tests (31 pytest) + benchmarks live in the PARENT repo (`rldyour-ai-cli-tools/
  validation/nddev-zcode-app/`), NOT inside this module. The suite includes
  validation helper coverage for `validate_fast.sh`.
- Restore hardening (1.0.1): C1 (temp-copy staging prevents source self-destruction),
  C2 (BUILD-VERSION guard), C3 (no silenced failures).

## nddev-builder toolkit (18 skills)

CREATE (10): add-marketplace, add-plugin, add-skill, add-command, add-agent,
add-hook, add-mcp-server, add-provider, add-reference, add-tool
LIST (1): list-components
MODIFY (1): enable-plugin
REMOVE (1): remove-component
TEST (3): run-tests, add-test, run-benchmarks
VALIDATE (1): doctor (8 axes + Step 9 test suite)
RELEASE (1): release-build

## Memory domains

(Add new memories here as they are written. Example domains: RELEASE, TECHDEBT,
INSTALLER, PLUGINS.)
