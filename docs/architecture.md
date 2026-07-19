# Architecture

`nddev-zcode-app` produces a complete, reproducible ZCode home from source. It
does not run ZCode agent sessions. Its lifecycle does manage the installed
configuration and only the explicitly declared runtime paths during protected
backup and restore operations.

## Implementation layers

```text
zcode_tools/   SOURCE: self-contained setup catalog in ZCode-native marketplaces
cli-tools/     SETUP MANAGER: discovery, status, lifecycle, and rendering
build/         CONTRACT: versions, artifact integrity, manifest, secret template
```

### Marketplace sources

Each `zcode_tools/marketplaces/<name>/` directory is a complete setup. The
installer selects exactly one setup and builds the target from its native
marketplace representation. `--setup` is canonical and `--marketplace` is a
backward-compatible alias.

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
the local `build/.env` file through structured JSON substitution. Source
templates never contain real credentials. Rendered `.env`, provider configs,
MCP configs, credentials, and backups are runtime secrets and remain private to
the current user.

Every CLI template declares one explicit `provider/model` main-model reference,
the matching provider kind and base URL, and the referenced model metadata.
ZCode CLI 0.15.2 requires that bootstrap contract before it can create a
desktop agent session. The bootstrap provider entry contains no credential;
ZCode mounts the restored OAuth credential through its runtime provider
registry after the CLI adapter has initialized.

The local env file is accepted only when it is a current-user-owned regular
non-symlink with no group/world permissions. Existing environment variables win
over file values. No shell expansion occurs; only `ZCODE_TARGET` and
`ZCODE_BACKUPS_DIR` recognize a leading literal `$HOME` or `${HOME}` path
prefix.

### Setup profiles

- `nddev-builder` enables `core@nddev-builder`, a native component-authoring
  toolkit with 21 skills, 21 matching commands, and one reviewer agent.
- `nddev-designer` is a production-ready minimal design profile. Its empty
  extension maps are intentional; project-specific design tools come from the
  active workspace.
- `nddev-developer` is a production-ready minimal engineering profile. Its
  empty extension maps are intentional; language, framework, and repository
  tools come from the active workspace.

All preference templates keep `modelProviderFamilyModes.zai` set to `oauth`,
which is the verified ZCode 3.3.6 account-authentication mode. The provider
objects in `v2/config.json` are a separate explicit API-key contract: Z.ai uses
`https://api.z.ai/api/anthropic`; BigModel uses
`https://open.bigmodel.cn/api/anthropic`. Both API-key providers are disabled
by default and must be enabled deliberately after their secret is configured.
Their `custom:*` identities never reuse ZCode-owned `builtin:*` provider IDs,
so rendering a setup cannot disable or replace the app-managed OAuth provider.

### Installer

The entry point is `cli-tools/scripts/install.sh`. Platform runners source the
shared libraries and execute the same lifecycle:

1. canonicalize absolute target and backup roots; require existing real
   immediate parents; reject files, symlink endpoints, nested roots,
   cross-filesystem transactions, and implicit replacement of an unstamped
   directory,
2. validate the selected marketplace and acquire an exclusive target lock plus
   an exclusive lock for the shared backup pool in deterministic order,
3. reject open task/session databases or SQLite recovery sidecars in apply mode,
   then create a private same-filesystem sibling stage and check the live ZCode
   runtime in apply mode through one canonical executable, a 3-second timeout,
   and a 64 KiB output cap,
4. copy source, structurally render JSON and MCP inputs, write a schema-2
   `BUILD-VERSION` bound to the selected `setup_id`,
   and selectively restore credentials, certificates, the desktop task index,
   legacy session snapshots, bot definitions, CLI session databases, and
   runtime artifacts into the stage,
5. reject a missing or inconsistent CLI model/provider bootstrap, reserved
   `builtin:*` identities on custom providers, unresolved placeholders in keys
   or values across active config/setting/provider/MCP/hook branches, symlinks,
   special files, and hardlink aliases; normalize private permissions, verify
   the complete staged result, and fsync it before commit,
6. hold any occupied rotation slot, move the previous live target into its
   backup, and atomically rename the verified stage into place,
7. roll back both the live target and held backup occupant on errors or handled
   signals, then release both locks. Every mutable stage/live/rollback/hold
   endpoint is bound to its recorded filesystem identity across abort and
   committed cleanup; an identity mismatch preserves foreign state, recovery
   paths, and locks instead of guessing ownership.

Plan mode describes the operation without writes or live `zcode` execution, but
still parses, substitutes, merges, and validates config/setting/provider/MCP/hook
inputs. Missing or empty active placeholders in keys or values fail in both
modes; only explicitly disabled provider/MCP nodes may remain dormant. An
existing unstamped directory is never replaced implicitly: initial adoption
requires `--adopt-unmanaged` together with an explicit `--target`.

Shared implementation:

- `lib/common.sh` owns logging, canonical path boundaries, backup naming,
  private permissions, safe dry-run operations, and structured template
  rendering.
- `lib/version.sh` owns the public build/runtime version contract and installed
  stamp, including setup identity and legacy schema compatibility.
- `lib/build.sh` owns selection, two-root locking, staging, backup rotation,
  fsync durability, rollback, build, restore, verification, and orchestration.
- `restore.sh` applies the explicit per-path restore modes.

### Bootstrap and CLI boundaries

Bootstrap accepts only the exact canonical CDN base recorded in
`build/version.json` and HTTPS-only redirects. It verifies size plus SHA-512
before native identity checks. The DEB path is fixed to
`/opt/ZCode/resources/glm/zcode.cjs`. Before the package transaction, private
extraction must find exactly one safe entry there and its CLI version must match
the pin; `dpkg --dry-run -i` must then pass. After installation, the exact
dpkg-owned path/version and SHA-512 equality with the verified payload entry are
required.

Deterministically ordered locks protect the installer-managed app endpoint and
the user launcher; dpkg owns the system package transaction on Debian systems.
App and launcher swaps retain rollback state until exact postconditions pass.
That point marks the bootstrap committed. Cleanup failure after commit remains
visible but does not roll back verified state; pre-commit errors and handled
signals recover the prior app/launcher when state is unambiguous. New and old
application/launcher endpoints are identity-bound in both abort and success
cleanup, and cleanup uses exclusive quarantine plus fd-relative deletion for
owned state.

Normal installs treat a missing, timed-out, failed, or over-limit runtime CLI
probe as advisory `not-installed`/`unknown`. Bootstrap treats the same bounded
probe as a strict version postcondition.

### Build contract

- `VERSION`, `build/version.json`, `build/manifest.json`, the `nddev-builder`
  marketplace `core` entry, and the core plugin manifest carry one strict
  SemVer for every repository release.
- `build/version.json` also pins the verified ZCode app, CLI, runtime model,
  launcher locations, and each CDN artifact's filename, byte size, SHA-512, and
  available platform-native identity metadata. Linux launcher entries are
  explicit for the DEB (`/opt/ZCode/resources/glm/zcode.cjs`) and the default
  AppImage extraction (`${HOME}/.local/opt/ZCode/resources/glm/zcode.cjs`).
- `build/manifest.json` defines public layout, artifact/bootstrap, command-option,
  runtime-probe, transaction, backup/restore, adoption, and secrets contracts.
- The release workflow validates every version source, requires the tagged
  commit to be reachable from fetched `origin/main`, and rejects publication
  before invoking the shared supply-chain workflow if any contract drifts.

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

The public product contract is `config/nddev-contract.json` version 3. It
defines setup discovery, selection, status, stamp identity, and legacy recovery
compatibility. It also keeps
the two MCP namespaces explicit: plugin `.mcp.json` inputs use `mcpServers`,
while the installed CLI configuration uses `mcp.servers`. The installer remains
independent of this descriptive metadata and implements the same mapping
directly.

## Public/private repository boundary

This repository is the public implementation module. It intentionally excludes
repository-local agent configuration, development memories, validation
implementations, tests, and benchmarks.

The private `nddev-harnesses` repository is the development control plane. It
pins this module under `modules/nddev-zcode-app`, owns cross-platform and release
gates, and validates a specific public commit before release. The dependency is
one-way: the harness knows the public module; the module never requires the
harness at runtime.
