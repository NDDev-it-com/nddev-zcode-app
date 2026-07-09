# nddev-zcode-app

`nddev-zcode-app` is a reusable build system and installer for complete,
version-stamped ZCode setups. It recreates `~/.zcode` from a selected local
marketplace on macOS or Ubuntu, backs up the previous installation, and
selectively restores runtime state so sessions and credentials survive setup
changes.

- **Author:** Danil Silantyev (github:rldyourmnd), CEO NDDev
- **License:** AGPL-3.0-or-later
- **Build version:** 2.0.1
- **Verified ZCode runtime:** app 3.3.3, CLI 0.15.0, model GLM-5.2

## What this repository contains

This public repository contains only the distributable implementation:

```text
zcode_tools/   Marketplace sources: complete editable ZCode setups
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

# Inspect and install a setup.
cli-tools/scripts/install.sh list
cli-tools/scripts/install.sh install --marketplace nddev-builder --plan
cli-tools/scripts/install.sh install --marketplace nddev-builder --apply
```

Plan mode performs no writes and does not invoke a locally installed `zcode`
binary. It still parses and merges config, setting, provider, MCP, and hook
inputs and rejects unresolved active placeholders in keys or values. Setup
installation in apply mode performs a bounded live runtime probe before it
changes the target.
See [docs/install.md](docs/install.md) for install, update, switch, backup,
restore, remove, and custom-target usage.

## Available setups

Each directory under `zcode_tools/marketplaces/` is a complete setup:

- `nddev-builder` enables its reusable 13-skill, 13-command `core` toolkit for
  creating and managing ZCode marketplaces, plugins, and components.
- `nddev-designer` is a deliberately lean product-design profile focused on
  design-system consistency, accessibility, responsive states, and
  implementation-ready decisions.
- `nddev-developer` is a deliberately lean software-engineering profile focused
  on root-cause changes, explicit contracts, proportionate verification, and
  clean delivery.

The designer and developer profiles intentionally ship without global plugins,
hooks, MCP servers, or user-scope components. They take project-specific tools
and policy from the active workspace, which keeps the profiles portable and
their permanent context surface small.

The installer copies exactly one selected marketplace into the target ZCode
home. Marketplace content is ordinary source and can be adapted independently.

## Backup and restore contract

Apply operations rotate at most 10 backups under `~/.zcode-backups/`:

```text
<N>-<VERSION>-old.zcode    N = 0..9
```

Credentials, certificates, sessions, databases, and runtime artifacts are
selectively restored during an update or switch. Logs, crash data, and plugin
caches are regenerated. Destructive restore/remove operations refuse targets
that are not marked by this installer with `BUILD-VERSION`.

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
