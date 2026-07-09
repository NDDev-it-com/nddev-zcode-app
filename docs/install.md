# Install

`nddev-zcode-app` can install ZCode **from zero** and then configure it. Two phases:

1. **`bootstrap`** — downloads and installs the ZCode desktop app + CLI (macOS `.dmg`,
   Ubuntu `.deb`) at the pinned version, and wires the `zcode` CLI launcher.
2. **`install`** — builds a clean `~/.zcode` from a marketplace (config, plugins,
   skills). Backs up the current one first.

Both work on macOS (desktop) and Ubuntu (desktop/server).

## Prerequisites

- Git, Python 3 (`python3`), `curl`, and `node` (the CLI launcher runs the app's
  `zcode.cjs` through node).
- `build/.env` populated from `build/.env.example` (see [secrets.md](secrets.md)).
- If ZCode is already installed, `bootstrap` skips the download and only wires
  the CLI launcher.

## From zero (fresh machine)

```bash
# 1. Clone or download the repository.
# 2. Populate secrets:
cp build/.env.example build/.env
$EDITOR build/.env

# 3. Install the ZCode app + CLI (downloads ~150MB from the official CDN):
cli-tools/scripts/install.sh bootstrap --plan     # dry-run first
cli-tools/scripts/install.sh bootstrap --apply

# 4. Configure ~/.zcode from a marketplace:
cli-tools/scripts/install.sh list
cli-tools/scripts/install.sh install --marketplace nddev-builder --plan
cli-tools/scripts/install.sh install --marketplace nddev-builder --apply
```

After step 3, ZCode is installed and the `zcode` command is on PATH. After
step 4, `~/.zcode` is configured and ready to use.

Plan mode performs no writes, downloads, target mutation, or live `zcode`
execution. Runtime detection is deferred until apply mode.

## Usage

```bash
# List available setups (marketplaces):
cli-tools/scripts/install.sh list

# Install — plan (dry-run) first, then apply:
cli-tools/scripts/install.sh install --marketplace nddev-builder --plan
cli-tools/scripts/install.sh install --marketplace nddev-builder --apply

# Update — re-run install with the same marketplace (old ~/.zcode is backed up).
# Switch — install a different marketplace (the old setup is backed up).
# Remove — back up and delete the install:
cli-tools/scripts/install.sh remove --apply

# Inspect and restore numbered backup slots:
cli-tools/scripts/install.sh list --backups
cli-tools/scripts/install.sh restore --slot 3 --plan
cli-tools/scripts/install.sh restore --slot 3 --apply

# Custom install directory (default is ~/.zcode):
cli-tools/scripts/install.sh install \
  --marketplace nddev-builder --target /opt/my-zcode --apply
# ...or set it once in build/.env (ZCODE_TARGET=...) and skip --target.

# Force a platform (otherwise auto-detected from uname):
cli-tools/scripts/install.sh install \
  --marketplace nddev-builder --platform macos --apply
```

### Commands

| Command | What it does |
| --- | --- |
| `bootstrap` | Install the pinned ZCode app and CLI; defaults to plan mode. |
| `install` | Back up, build from one marketplace, and restore runtime state. |
| `remove` | Back up and delete a stamped target. |
| `restore` | Restore one backup slot into an empty or stamped target. |
| `list` | Show marketplaces; add `--backups` to show backup slots. |

### Target directory resolution

The install/remove target is resolved in this order:

1. `--target <dir>` flag (highest precedence)
2. `ZCODE_TARGET` in `build/.env`
3. `~/.zcode` (the standard ZCode location, default)

### Lifecycle: install → update → switch → remove

Every transition backs up the current install first into a rotating pool of
**10 slots** (`0-<VERSION>-old.zcode` … `9-<VERSION>-old.zcode`), so the total
never grows beyond 10 directories:

- **Install** — fresh build from a marketplace.
- **Update** — re-run `install` with the same marketplace (source changed).
- **Switch** — `install` with a different `--marketplace`.
- **Remove** — `remove` backs up and deletes.

Slot selection: the lowest free slot (0–9). When all 10 are full, the **oldest**
slot (by modification time) is overwritten — its old backup is removed first,
regardless of version. The version is in the filename; the timestamp is inside
each backup's `BUILD-VERSION` stamp.

## What happens on `install --apply`

1. **Backup** — the current target is moved to `<backups>/<N>-<VERSION>-old.zcode`,
   where `N` is a 0–9 rotation slot (lowest free slot; the oldest is overwritten
   when all ten are full, regardless of version). The pool never exceeds 10 backups.
2. **Build** — a clean target is rendered from the selected marketplace:
   - `AGENTS.md`, `skills/`, `commands/`, `agents/`, `plugins/` are copied as-is.
   - `cli/config.json`, `v2/config.json`, `v2/setting.json` are rendered from
     their `*.template.json`, with `${VAR}` secrets injected from `build/.env`.
   - Empty runtime directories ZCode expects are created.
3. **Version stamp** — `BUILD-VERSION` records the build version, ZCode
   runtime baseline, platform, and timestamp.
4. **Restore** — runtime state is selectively restored from the backup:
   - **Always restored**: `v2/credentials.json`, `v2/certs/`, `cli/agents/`
     (sessions), `cli/db/`, `cli/artifacts/`.
   - **Never restored** (regenerated by ZCode): `cli/log/`, `v2/logs/`,
     `v2/crash/`, `cli/plugins/cache/`.
5. **Verify** — the rendered JSON files are validated; `BUILD-VERSION` and
   `AGENTS.md` presence is checked.

## After install

Open the ZCode desktop app. `credentials.json` is restored from the backup, so
you stay logged in. If the auth token expired, re-authenticate in the app.

## Reverting

Use the guarded restore lifecycle instead of moving backup directories manually:

```bash
cli-tools/scripts/install.sh list --backups
cli-tools/scripts/install.sh restore --slot <N> --plan
cli-tools/scripts/install.sh restore --slot <N> --apply
```

If the target exists, restore first backs it up. The restore source is staged
before any backup rotation or target replacement so a full 10-slot pool cannot
invalidate the selected source.
