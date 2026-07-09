# nddev-zcode-app

`nddev-zcode-app` is a reusable build system and installer for complete,
version-stamped ZCode setups. It recreates `~/.zcode` from a selected local
marketplace on macOS or Ubuntu, backs up the previous installation, and
selectively restores runtime state so sessions and credentials survive setup
changes.

- **Author:** Danil Silantyev (github:rldyourmnd), CEO NDDev
- **License:** AGPL-3.0-or-later
- **Build version:** 2.0.0
- **Verified ZCode runtime:** app 3.3.3, CLI 0.15.0, model GLM-5.2

## What this repository contains

This public repository contains only the distributable implementation:

```text
zcode_tools/   Marketplace sources: complete editable ZCode setups
cli-tools/     Installer and lifecycle commands for macOS and Ubuntu
build/         Version contract, manifest, system files, and secret template
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
# Populate local secrets. build/.env is gitignored.
cp build/.env.example build/.env
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
binary. Apply mode checks the live runtime version, then performs the requested
lifecycle operation. See [docs/install.md](docs/install.md) for install, update,
switch, backup, restore, remove, and custom-target usage.

## Available setups

Each directory under `zcode_tools/marketplaces/` is a complete setup:

- `nddev-builder` provides a reusable 13-skill, 13-command toolkit for creating
  and managing ZCode marketplaces, plugins, and components.
- `nddev-designer` is the designer-oriented setup.
- `nddev-developer` is the software-development setup.

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

## Secrets

`build/.env.example` defines supported keys; the gitignored `build/.env` holds
local values. `${VAR_NAME}` placeholders in marketplace templates are rendered
only during installation. See [docs/secrets.md](docs/secrets.md).
