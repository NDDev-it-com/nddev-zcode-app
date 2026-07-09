# Architecture

`nddev-zcode-app` produces a complete, reproducible ZCode home from source. It
does not run ZCode or own ZCode runtime data.

## Implementation layers

```text
zcode_tools/   SOURCE: self-contained marketplace setups
cli-tools/     INSTALLER: lifecycle and rendering for macOS and Ubuntu
build/         CONTRACT: versions, manifest, system files, secret template
```

### Marketplace sources

Each `zcode_tools/marketplaces/<name>/` directory is a complete setup. The
installer selects exactly one marketplace and builds the target from it.

| Marketplace source | Installed target | Treatment |
| --- | --- | --- |
| `AGENTS.md` | `<target>/AGENTS.md` | copied |
| `skills/`, `commands/`, `agents/` | same paths under target | copied |
| full marketplace directory | `<target>/marketplaces/<name>/` | copied |
| `cli-config.template.json` | `<target>/cli/config.json` | rendered |
| `v2-config.template.json` | `<target>/v2/config.json` | rendered |
| `v2-setting.template.json` | `<target>/v2/setting.json` | rendered |
| `hooks.json`, `mcp.json` | keys in `cli/config.json` | merged |

Template rendering expands `${VAR}` values from the process environment and
the local `build/.env` file. Unknown placeholders remain unchanged so optional
provider or tool credentials can be configured later.

### Installer

The entry point is `cli-tools/scripts/install.sh`. Platform runners source the
shared libraries and execute the same lifecycle:

1. resolve and validate the selected marketplace,
2. back up a prior stamped target,
3. check the live ZCode runtime in apply mode,
4. render a clean target,
5. write `BUILD-VERSION`,
6. selectively restore runtime state,
7. verify the rendered result.

Plan mode describes the operation without writes or live `zcode` execution.

Shared implementation:

- `lib/common.sh` owns logging, target/platform helpers, backup naming, safe
  dry-run operations, and template rendering.
- `lib/version.sh` owns the public build/runtime version contract and installed
  stamp.
- `lib/build.sh` owns selection, backup, build, restore, verification, and
  orchestration.
- `restore.sh` applies the explicit per-path restore modes.

### Build contract

- `VERSION`, `build/version.json`, and `build/manifest.json` carry the same
  module build version.
- `build/version.json` also pins the verified ZCode app, CLI, runtime model, CDN,
  artifacts, and launcher locations.
- `build/manifest.json` defines public layout, backup, restore, and secrets
  contracts.
- The `nddev-builder/core` version is independent and must match between its
  marketplace entry and `.zcode-plugin/plugin.json`.

## ZCode-native component format

ZCode discovers plugin components by convention:

```text
marketplaces/<marketplace>/marketplace.json
marketplaces/<marketplace>/plugins/<plugin>/.zcode-plugin/plugin.json
marketplaces/<marketplace>/plugins/<plugin>/skills/<skill>/SKILL.md
marketplaces/<marketplace>/plugins/<plugin>/commands/<command>.md
marketplaces/<marketplace>/plugins/<plugin>/agents/<agent>.md
marketplaces/<marketplace>/plugins/<plugin>/.mcp.json
```

Plugin manifests are metadata, not component registries. User-scope components
live directly under `<target>/{skills,commands,agents}/`. Hooks and MCP servers
are installed into `<target>/cli/config.json`.

## Public/private repository boundary

This repository is the public implementation module. It intentionally excludes
repository-local agent configuration, development memories, validation
implementations, tests, and benchmarks.

The private `nddev-harnesses` repository is the development control plane. It
pins this module under `modules/nddev-zcode-app`, owns cross-platform and release
gates, and validates a specific public commit before release. The dependency is
one-way: the harness knows the public module; the module never requires the
harness at runtime.
