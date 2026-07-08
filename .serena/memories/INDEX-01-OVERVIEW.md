# nddev-zcode-app — project memory index

> Serena durable project memory. Add domain-specific memories as
> `<DOMAIN>-<NN>-<TOPIC>.md` siblings. This index is the entry point.

## Project

`nddev-zcode-app` — build system + installer that recreates a complete,
version-stamped `~/.zcode` from source on macOS (desktop) and Ubuntu
(desktop/server). Not a runtime; produces `~/.zcode`.

## Architecture (three layers)

- `zcode_tools/` — SOURCE: the complete desired `~/.zcode` as editable files.
- `cli-tools/` — INSTALLER: renders `zcode_tools/` into `~/.zcode`.
- `build/` — ARTIFACTS: version.json, manifest.json, system/, secrets templates.

## Key facts

- Build version source: `build/version.json` → written to `~/.zcode/BUILD-VERSION`.
- Backup convention: `~/.zcode-backups/<N>-<DD.MM.YYYY>-<VERSION>-old.zcode` (N=1-9).
- Secrets: `build/.env.example` (committed) → `build/.env` (gitignored); `${VAR}`
  placeholders rendered at install time.
- ZCode plugin components are convention-discovered (skills/commands/agents);
  MCP uses `{"mcpServers":{}}`; hooks need `hooks.enabled: true`.

## Memory domains

(Add new memories here as they are written. Example domains: RELEASE, TECHDEBT,
INSTALLER, PLUGINS.)
