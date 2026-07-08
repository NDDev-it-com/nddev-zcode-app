# Architecture

`nddev-zcode-app` is a build system for a ZCode environment. It does not *run*
ZCode — it produces a complete, reproducible `~/.zcode` directory from source.

## Three layers

```
zcode_tools/   ← SOURCE: the complete desired ~/.zcode as editable files
cli-tools/     ← INSTALLER: renders zcode_tools/ into ~/.zcode (macOS + Ubuntu)
build/         ← ARTIFACTS: version, manifest, system files, secrets templates
```

### zcode_tools/ — the source

This directory *is* the desired `~/.zcode`, expressed as source. The installer
copies most of it verbatim and renders the templated config files.

| Source file | Target | Rendered? |
|---|---|---|
| `AGENTS.md` | `~/.zcode/AGENTS.md` | copy |
| `skills/` | `~/.zcode/skills/` | copy |
| `commands/` | `~/.zcode/commands/` | copy |
| `agents/` | `~/.zcode/agents/` | copy |
| `marketplace.json` | `~/.zcode/marketplace.json` | copy |
| `plugins/` | `~/.zcode/plugins/` | copy (self-contained bundles) |
| `cli-config.template.json` | `~/.zcode/cli/config.json` | **render** (`${VAR}`) |
| `v2-config.template.json` | `~/.zcode/v2/config.json` | **render** (`${API_KEY}`) |
| `v2-setting.template.json` | `~/.zcode/v2/setting.json` | **render** (`${HOME}`) |
| `hooks.json`, `mcp.json` | (reference, merged into cli/config.json) | reference |

### cli-tools/ — the installer

Entry point: `cli-tools/scripts/install.sh`. It:

1. Parses `--platform macos|ubuntu` (auto-detect) and `--apply|--plan`.
2. Validates prerequisites.
3. Delegates to the platform runner (`macos/install.sh` or `ubuntu/install.sh`),
   which sources the shared libraries and calls the install sequence.

Shared libraries under `cli-tools/scripts/lib/`:

- `common.sh` — logging, dry-run-aware `run`/`copy`/`move`/`ensure_dir`, platform
  detection, backup-name computation, and the `${VAR}` template renderer.
- `version.sh` — reads `build/version.json`, writes `~/.zcode/BUILD-VERSION`.
- `build.sh` — the backup → build → restore → verify orchestration.

`restore.sh` is standalone: it copies the always-restore paths from a backup into
the freshly built `~/.zcode`, and never touches the never-restore paths.

### build/ — artifacts

- `version.json` — the build version and ZCode runtime baseline.
- `manifest.json` — the source layout, backup policy, and restore policy.
- `.env.example` → `.env` — secrets (gitignored).
- `system/macos/`, `system/ubuntu/` — reserved for per-OS system files.

## ZCode native format

ZCode discovers plugin components **by convention**, not by declaration in the
manifest:

- `plugins/<name>/.zcode-plugin/plugin.json` — metadata only
  (`name`, `version`, `author`, `license`, `keywords`, `dependencies[]`).
- `plugins/<name>/skills/<skill>/SKILL.md` — a skill.
- `plugins/<name>/commands/<name>.md` — a slash command.
- `plugins/<name>/agents/<name>.md` — a subagent.
- `plugins/<name>/.mcp.json` — MCP servers, shape `{"mcpServers": {...}}`.

User-scope components live directly under `~/.zcode/{skills,commands,agents}/`.
Hooks and the MCP server registry live in `~/.zcode/cli/config.json` under `hooks`
(with `hooks.enabled: true`) and `mcp.servers`.

See the `zcode-configuration-guide` skill for the full reference.
