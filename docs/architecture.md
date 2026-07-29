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
  toolkit with 22 skills, 22 matching commands, and one reviewer agent.
- `nddev-designer` is a production-ready minimal design profile. Its empty
  extension maps are intentional; project-specific design tools come from the
  active workspace.
- `nddev-developer` is a production-ready minimal engineering profile. Its
  empty extension maps are intentional; language, framework, and repository
  tools come from the active workspace.

All preference templates keep `modelProviderFamilyModes.zai` set to `oauth`,
which is the verified ZCode account-authentication mode. The provider
objects in `v2/config.json` are a separate explicit API-key contract: Z.ai uses
`https://api.z.ai/api/anthropic`; BigModel uses
`https://open.bigmodel.cn/api/anthropic`. Both API-key providers are disabled
by default and must be enabled deliberately after their secret is configured.
Their `custom:*` identities never reuse ZCode-owned `builtin:*` provider IDs,
so rendering a setup cannot disable or replace the app-managed OAuth provider.

### Installer

The entry point is `cli-tools/scripts/install.sh`. It validates the trusted
system `/usr/bin/python3` interpreter, requires Python 3.9 or newer, scrubs
Python injection variables, and runs `cli-tools/nddev_zcode.py` with `-I -B`.
The Python manager owns setup lifecycle transactions; no fallback path bypasses
it.

Target-bound commands perform host and lexical option checks before filesystem
observation, then use monotonic product and canonical-target coordination
anchors in a fixed same-UID system temporary namespace. Read-only status and
plan commands do not create anchors. A cold read is permitted only when the
product anchor is absent and the existing product namespace is boundedly empty;
if the namespace changes during the uncoordinated body, the result is discarded
and the read is recomputed under coordination.

The apply lifecycle:

1. validates canonical target and backup endpoints, selected setup identity,
   runtime quiescence, and active placeholder requirements,
2. drains any valid pending cleanup journal before active mutation,
3. builds a private same-filesystem stage, writes a schema-2 `BUILD-VERSION`
   bound to `setup_id`, and selectively restores credentials, certificates,
   task indexes, session snapshots, bot definitions, CLI databases, and
   artifacts,
4. verifies the complete staged tree, normalizes private permissions, and
   fsyncs it before commit,
5. moves any previous target into a numbered backup slot, preserving exact
   object identity for rollback, and atomically publishes the verified stage,
6. promotes irreversible retired-slot cleanup through a durable prepare intent
   and immutable cleanup journal before destructive drain.

If post-commit cleanup cannot finish, the command returns success with explicit
cleanup-pending state in machine-readable contexts and read-only commands expose
the same state without repairing it. Malformed or incoherent cleanup state
fails closed with exit code 2 before mutation.

Plan mode describes the operation without writes or live `zcode` execution, but
still parses, substitutes, merges, and validates config/setting/provider/MCP/hook
inputs. Missing or empty active placeholders in keys or values fail in both
modes; only explicitly disabled provider/MCP nodes may remain dormant. An
existing unstamped directory is never replaced implicitly: initial adoption
requires `--adopt-unmanaged` together with an explicit `--target`.

Live implementation:

- `cli-tools/nddev_zcode.py` owns setup selection, target coordination, status,
  plan, install, remove, restore, backup rotation, rollback, cleanup journals,
  and rendering.
- `cli-tools/scripts/install.sh` is the trusted public compatibility shim.
- `cli-tools/scripts/bootstrap.sh` retains native app/CLI bootstrap behavior and
  still sources `lib/common.sh` and `lib/version.sh`.

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
