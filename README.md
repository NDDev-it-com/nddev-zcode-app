# nddev-zcode-app

`nddev-zcode-app` is a reusable build system and installer for a complete,
version-stamped ZCode setup. It recreates `~/.zcode` from the managed
`nddev-builder` marketplace on macOS or Ubuntu, backs up the previous installation, and
selectively restores runtime state so sessions and credentials survive setup
changes.

- **Author:** Danil Silantyev (github:rldyourmnd), CEO NDDev
- **License:** AGPL-3.0-or-later
- **Build version:** 0.1.1
- **Verified ZCode runtime:** app 3.5.3, CLI 0.15.2, model GLM-5.2

## What this repository contains

This public repository contains only the distributable implementation:

```text
zcode_tools/   Marketplace source: the complete editable nddev-builder setup
cli-tools/     Installer and lifecycle commands for macOS and Ubuntu
build/         Version, artifact-integrity, manifest, and secret contracts
config/        Public product and native-format contract metadata
references/    Public ZCode compatibility baseline
docs/          Public architecture, installation, and secrets documentation
```

Development-only agent context, validation code, tests, and benchmarks are kept
outside this repository in the maintainers' private `nddev-harnesses` control
plane. This boundary keeps the public module directly reusable and free of
workspace-specific artifacts.

See [docs/architecture.md](docs/architecture.md) for the component and repository
boundaries.

## Quick start

```bash
# Optional: configure explicit API-key providers or custom local settings.
# Z.ai account OAuth remains the default; build/.env is gitignored.
cp build/.env.example build/.env
chmod 600 build/.env
$EDITOR build/.env

# Install the pinned ZCode app and CLI, if needed.
cli-tools/scripts/install.sh bootstrap --plan
cli-tools/scripts/install.sh bootstrap --apply

# Inspect and install the managed setup.
cli-tools/scripts/install.sh list
cli-tools/scripts/install.sh list --json
cli-tools/scripts/install.sh install --plan
# Quit the ZCode desktop app before apply-mode target changes.
cli-tools/scripts/install.sh install --apply
cli-tools/scripts/install.sh status
cli-tools/scripts/install.sh status --json
```

Plan mode performs no writes and does not invoke a locally installed `zcode`
binary. It still parses and merges config, setting, provider, MCP, and hook
inputs, requires the explicit CLI model/provider bootstrap expected by ZCode
0.15.2, rejects custom providers that reuse reserved `builtin:*` identities,
and rejects unresolved active placeholders in keys or values. Setup installation
in apply mode performs a bounded live runtime probe and rejects open
task/session databases or SQLite recovery sidecars before it changes the target.
See [docs/install.md](docs/install.md) for install, update, posture, backup,
restore, remove, and custom-target usage.

## Managed Setup

The public catalog installs one managed setup by default:

- `nddev-builder` enables its reusable 22-skill, 22-command `core` toolkit for
  creating and managing ZCode marketplaces, plugins, and components.

`install` uses `nddev-builder` when no setup flag is supplied. `--setup
nddev-builder` is still accepted, and `--marketplace nddev-builder` remains a
compatibility alias for the underlying ZCode-native storage format. `--posture
full-auto` is the default; `--posture safe` renders the same managed setup with
a stricter interaction posture. Every new `BUILD-VERSION` schema-2 stamp records
`setup_id` and `posture`, and `status` validates and reports both.

## Backup and restore contract

Apply operations rotate at most 10 backups under `~/.zcode-backups/`:

```text
<N>-<VERSION>-old.zcode    N = 0..9
```

Credentials, certificates, the desktop task index and legacy session snapshots,
bot definitions, CLI session databases, and runtime artifacts are selectively
restored during an update. Logs, crash data, transient execution
data, model I/O rollouts, telemetry, and caches are regenerated. Destructive
restore/remove operations refuse targets that are not marked by this installer
with `BUILD-VERSION`.

Install also refuses an existing unstamped target unless the user supplies both
`--adopt-unmanaged` and an explicit existing `--target`. Adoption stores the
original content tree in a typed, target-bound backup envelope that the guarded
restore lifecycle can recover. Its filesystem permissions are normalized to
private owner-only modes during adoption. Rendering and verification happen in
a private sibling stage; exclusive target and backup-pool locks plus
identity-bound commit rollback prevent partial live installs and rotation races.

## Secrets

`build/.env.example` defines supported keys; the gitignored `build/.env` holds
optional local values for explicit API-key providers and integrations. It must
be a current-user-owned regular non-symlink with mode `0600` or stricter. The
installer never evaluates it as shell code; only the two documented target-path
keys support a narrow leading `$HOME`/`${HOME}` expansion.

`${VAR_NAME}` placeholders in marketplace JSON values are rendered during plan
validation and installation; placeholder-bearing object keys are rejected.
Missing or empty placeholders in active config/setting/provider/MCP/hook
branches fail closed. Explicitly disabled provider/MCP entries may stay dormant.

The installed ZCode home contains sensitive runtime data: its `.env`, rendered
provider and MCP configs, `v2/credentials.json`, and backups can contain tokens
or API keys.
Never print, commit, upload, or include them in diagnostic evidence. See
[docs/secrets.md](docs/secrets.md).
