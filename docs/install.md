# Install

`nddev-zcode-app` can install ZCode **from zero** and then configure it. Two phases:

1. **`bootstrap`** — downloads and verifies the exact pinned ZCode artifact,
   installs the desktop app and embedded CLI, and atomically writes the local
   `zcode` launcher. macOS uses a DMG; Ubuntu uses a DEB when the complete dpkg
   toolchain is available and a locally extracted AppImage otherwise.
2. **`install`** — builds a clean `~/.zcode` from a setup (config, plugins,
   skills). Backs up the current one first.

Both work on macOS (desktop) and Ubuntu (desktop/server).

## Prerequisites

- Git, Python 3.10+ (`python3`), `curl`, and `node` (the CLI launcher runs the
  app's `zcode.cjs` through node).
- A local `build/.env` copied from `build/.env.example` only when explicit
  API-key providers, MCP integrations, or custom target settings are needed
  (see [secrets.md](secrets.md)). When present, it must be a current-user-owned
  regular non-symlink with mode `0600` or stricter. Z.ai account OAuth remains
  the default.
- macOS bootstrap additionally requires the system `hdiutil`, `codesign`, and
  `spctl` tools; it prefers current `diskutil image attach`/`eject` operations
  and retains `hdiutil` attach/detach only as a compatibility fallback. Ubuntu
  DEB installation requires `dpkg`, `dpkg-deb`, `dpkg-query`, and `sudo` when
  not running as root.

## From zero (fresh machine)

```bash
# 1. Clone or download the repository.
# 2. Optional: configure explicit API-key providers or local target settings.
# Skip this step when using the default Z.ai account OAuth flow.
cp build/.env.example build/.env
chmod 600 build/.env
$EDITOR build/.env

# 3. Verify and install the ZCode app + CLI from the official CDN:
cli-tools/scripts/install.sh bootstrap --plan     # dry-run first
cli-tools/scripts/install.sh bootstrap --apply

# 4. Configure ~/.zcode from a setup:
cli-tools/scripts/install.sh list
cli-tools/scripts/install.sh install --setup nddev-builder --plan
cli-tools/scripts/install.sh install --setup nddev-builder --apply
```

After step 3, ZCode is installed and the `zcode` command is on PATH. After
step 4, `~/.zcode` is configured and ready to use.

The installed ZCode home contains sensitive runtime state. Do not print,
commit, upload, or attach its `.env`, rendered provider/MCP configs,
`v2/credentials.json`, or backup contents.

Plan mode performs no writes, downloads, target mutation, or live `zcode`
execution. It does parse, substitute, and merge config/setting/provider/MCP/hook
inputs and fails if an active key or value contains a missing or empty
placeholder. Runtime detection is deferred until apply mode.

## Bootstrap integrity and installed paths

Bootstrap does not trust an existing installation or an unverified download.
Apply mode performs these checks in order:

1. Select the platform/architecture artifact object from `build/version.json`.
2. Require the canonical CDN base to be exactly
   `https://cdn-zcode.z.ai/zcode/electron/releases`, construct a
   credential-free artifact URL, and allow HTTPS-only redirects.
3. Verify the exact byte size and SHA-512 digest before opening the artifact.
   Both must match independently; equal size never excuses digest drift.
4. On macOS, verify the DMG, mount it read-only (preferring `diskutil image`
   operations), and verify Gatekeeper assessment, code signature, Team ID,
   bundle ID, app version, and bundle version before and after installation.
5. On Ubuntu DEB systems, verify package name, architecture, and exact Debian
   package version. Extract the payload privately before installation; require
   exactly one safe `/opt/ZCode/resources/glm/zcode.cjs` entry and verify its
   pinned CLI version. A privileged `dpkg --dry-run -i` preflight must then
   succeed before the real `dpkg -i`. After installation, require the same exact
   dpkg-owned path and CLI version, and require its SHA-512 to match the verified
   payload entry. Installation failure is fatal and never falls through to
   another format.
6. When complete dpkg tooling is absent, extract the already verified AppImage,
   verify its embedded CLI, and replace its managed install directory through a
   same-filesystem stage.
7. Hold deterministic locks for every installer-managed app endpoint and the
   user launcher (with dpkg owning its system package transaction), then stage
   and swap the app and launcher with rollback state.
8. Require exact app/package, entrypoint, launcher, and CLI postconditions.
   These postconditions define the commit point. Cleanup failure after commit
   is reported as an error without rolling back verified committed state.

Default runtime paths are:

| Platform/package | Embedded CLI entry |
| --- | --- |
| macOS DMG | `/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs` |
| Ubuntu DEB | `/opt/ZCode/resources/glm/zcode.cjs` |
| Ubuntu AppImage | `${HOME}/.local/opt/ZCode/resources/glm/zcode.cjs` |

All three use `${HOME}/.local/bin/zcode` as the user-facing launcher. The
AppImage path can be changed with `NDDEV_APPIMAGE_INSTALL_DIR`; the macOS app
root can be changed with `NDDEV_APPLICATIONS_DIR` for isolated environments.

## Usage

```bash
# List available setups for people or automation:
cli-tools/scripts/install.sh list
cli-tools/scripts/install.sh list --json

# Install — plan (dry-run) first, then apply:
cli-tools/scripts/install.sh install --setup nddev-builder --plan
# Quit the ZCode desktop app before every apply-mode target mutation.
cli-tools/scripts/install.sh install --setup nddev-builder --apply

# Inspect the selected setup and validated installed-state stamp:
cli-tools/scripts/install.sh status
cli-tools/scripts/install.sh status --json

# Explicitly adopt an existing unstamped ZCode home for the first time.
# Both --adopt-unmanaged and an explicit existing --target are required:
cli-tools/scripts/install.sh install --setup nddev-builder \
  --target "$HOME/.zcode" --adopt-unmanaged --plan
cli-tools/scripts/install.sh install --setup nddev-builder \
  --target "$HOME/.zcode" --adopt-unmanaged --apply

# Update — re-run install with the same setup (old ~/.zcode is backed up).
# Switch — install a different setup (the old setup is backed up).
# Remove — back up and delete the install:
cli-tools/scripts/install.sh remove --apply

# Inspect and restore numbered backup slots:
cli-tools/scripts/install.sh list --backups
cli-tools/scripts/install.sh restore --slot 3 --plan
cli-tools/scripts/install.sh restore --slot 3 --apply

# Custom install directory (default is ~/.zcode):
cli-tools/scripts/install.sh install \
  --setup nddev-builder --target "$HOME/.zcode-work" --apply
# ...or set it once in build/.env (ZCODE_TARGET=...) and skip --target.

# Force a platform (otherwise auto-detected from uname):
cli-tools/scripts/install.sh install \
  --setup nddev-builder --platform macos --apply
```

### Commands

| Command | What it does |
| --- | --- |
| `bootstrap` | Install the pinned ZCode app and CLI; defaults to plan mode. |
| `install` | Back up, build from one setup, and restore runtime state. |
| `remove` | Atomically move a stamped target into the backup pool. |
| `restore` | Restore one backup slot into an empty or stamped target. |
| `list` | Show setups; add `--json` for automation or `--backups` for backup slots. |
| `status` | Validate and report missing, unmanaged, legacy-managed, or setup-aware managed state. |

### Command option matrix

The installer rejects unknown options, options that do not apply to the chosen
command, and simultaneous `--apply` plus `--plan`/`--dry-run`. It never silently
ignores a recognized flag.

| Option | bootstrap | install | remove | restore | list | status |
| --- | --- | --- | --- | --- | --- | --- |
| `--setup` (`--marketplace` alias) | — | yes | — | — | — | — |
| `--target` | — | yes | yes | yes | — | yes |
| `--platform` | yes | yes | — | — | — | — |
| `--apply`, `--plan`, `--dry-run` | yes | yes | yes | yes | — | — |
| `--keep-backup` | — | — | yes | — | — | — |
| `--slot` | — | — | — | yes | — | — |
| `--adopt-unmanaged` | — | yes | — | — | — | — |
| `--allow-target-relocation` | — | — | — | yes | — | — |
| `--backups` | — | — | — | — | yes | — |
| `--json` | — | — | — | — | yes (setups only) | yes |

Use `list`, `-l`, or `--list` to select the list command. `-h`/`--help` prints
usage without executing a command.

### Target directory resolution

The install, remove, restore, or status target is resolved in this order:

1. `--target <dir>` flag (highest precedence)
2. `ZCODE_TARGET` in `build/.env`
3. `~/.zcode` (the standard ZCode location, default)

The env parser performs no shell expansion. For portability, only
`ZCODE_TARGET` and `ZCODE_BACKUPS_DIR` support an exact leading literal
`$HOME`, `$HOME/`, `${HOME}`, or `${HOME}/` prefix; other values remain literal.

Target and backup roots must be canonical absolute paths with existing real
immediate parent directories. They must be non-root, disjoint, and on one
filesystem. Existing files and symlink endpoints are always refused. The
current user must be able to create and replace entries in both parents; a path
such as `/opt/...` therefore requires permissions prepared by an administrator.
An existing unstamped directory is also refused unless `install` receives both
`--adopt-unmanaged` and an explicit existing `--target`; this prevents a typo
from silently replacing an unrelated directory.

### Lifecycle: install → update → switch → remove

Every transition backs up the current install first into a rotating pool of
**10 slots** (`0-<VERSION>-old.zcode` … `9-<VERSION>-old.zcode`), so the total
never grows beyond 10 directories:

- **Install** — fresh build from a setup.
- **Update** — re-run `install` with the same setup (source changed).
- **Switch** — `install` with a different `--setup`.
- **Remove** — `remove` backs up and deletes.

Slot selection: the lowest free slot (0–9). When all 10 are full, the **oldest**
slot (by modification time) is selected regardless of version. Its prior
occupant is held until the new transaction commits and is restored on failure.
Managed backups carry the version in the filename and a validated timestamp in
`BUILD-VERSION`.

An explicitly adopted unstamped target is stored as
`<N>-unmanaged-old.zcode/`, containing an owner-only `NDDEV-BACKUP.json`
envelope and the original content tree under `payload/`. Adoption normalizes
directory and file permissions to private owner-only modes, so original mode
metadata is intentionally not preserved. The envelope binds the backup to its
original canonical target.

## What happens on `install --apply`

1. **Boundaries and locks** — target and backup roots are validated, then the
   installer acquires exclusive target and shared backup-pool locks. Concurrent
   operations cannot race the same live tree or rotation pool. Apply mode also
   rejects open task/session databases and SQLite recovery sidecars; quit ZCode
   cleanly before install, switch, remove, or restore.
2. **Stage** — a private sibling staging directory is created on the same
   filesystem. A clean target is rendered there from the selected marketplace:
   - `AGENTS.md` and user-scope `skills/`, `commands/`, and `agents/` are copied
     as-is; the complete selected marketplace, including its plugins, is copied
     under `marketplaces/<name>/`.
   - `cli/config.json`, `v2/config.json`, `v2/setting.json` are rendered from
     their JSON inputs, with `${VAR}` values structurally substituted and
     JSON-escaped. Placeholder-bearing object keys are rejected. Rendered MCP
     entries are merged into `cli/config.json`.
   - Empty runtime directories ZCode expects are created.
3. **Version stamp** — schema-2 `BUILD-VERSION` records the selected `setup_id`,
   build version, ZCode runtime baseline, platform, and timestamp. Legacy
   schema 0/1 stamps remain readable for recovery, but their setup identity is
   reported as unknown.
4. **Restore into stage** — selected runtime state is copied from the current
   target before any live replacement:
   - **Always restored**: `v2/credentials.json`, `v2/certs/`, the desktop
     `v2/tasks-index.sqlite`, legacy `v2/sessions/`, current and legacy bot
     definition files, `cli/agents/`, `cli/db/`, and `cli/artifacts/`. The task
     index and CLI session database are restored together so their cross-store
     session references stay consistent.
   - **Never restored** (regenerated by ZCode): `cli/log/`, `v2/logs/`,
     `v2/crash/`, `cli/plugins/cache/`, transient `cli/exec/`, model I/O
     `cli/rollout/`, telemetry, and model/plan caches.
5. **Verify** — managed stamp and JSON schemas, exact stamp/setup identity, marketplace presence,
   unresolved active config/setting/provider/MCP/hook placeholders in keys or
   values,
   symlink/special-file/hardlink absence, and private permissions are checked;
   the verified stage is fsynced before commit. Only explicitly disabled
   provider/MCP entries may keep dormant placeholders.
6. **Commit or rollback** — an occupied backup slot is held, the previous
   target moves into its backup, and the verified stage is atomically renamed
   into place. A failed commit, handled signal, or pre-commit finalization step
   restores the previous target and backup-slot occupant. Housekeeping failure
   after a verified commit is reported without discarding committed state.
   Stage, live, rollback, adoption-envelope, and occupied-slot endpoints remain
   bound to their recorded filesystem identities through abort and success
   cleanup. If any endpoint is replaced, foreign state is left untouched and
   recovery paths plus locks are preserved for explicit inspection.

## After install

Open the ZCode desktop app. `credentials.json` is restored from the backup, so
you stay logged in. If the auth token expired, re-authenticate in the app.

The verified preference uses Z.ai account OAuth. To use an explicit Z.ai API
key instead, populate `ZAI_API_KEY`, set that custom provider's `enabled` field
to `true`, reinstall, and select the provider backed by
`https://api.z.ai/api/anthropic`. BigModel API-key access remains a separate,
disabled-by-default provider backed by `https://open.bigmodel.cn/api/anthropic`;
enable it only after populating `BIGMODEL_API_KEY`.

### Runtime version probe

A setup install in apply mode resolves and canonicalizes the `zcode` executable
once, then invokes `--version` with no stdin, a 3-second timeout, and a 64 KiB
output cap. A missing binary reports `not-installed`; timeout, nonzero exit,
oversized output, or probe error reports `unknown`. Those values are advisory
and nonfatal during a normal setup install. Bootstrap uses the same bounded
probe as a strict postcondition and refuses unknown or mismatched CLI state.

## Reverting

Use the guarded restore lifecycle instead of moving backup directories manually:

```bash
cli-tools/scripts/install.sh list --backups
cli-tools/scripts/install.sh restore --slot <N> --plan
cli-tools/scripts/install.sh restore --slot <N> --apply
```

If the target exists, restore first backs it up. The restore source is copied
to and verified in a private same-filesystem stage before backup rotation or
target replacement, so a full 10-slot pool cannot invalidate the selected
source.

Typed adopted-unmanaged envelopes restore only to their recorded original
target by default. Relocation is a separate explicit action:

```bash
cli-tools/scripts/install.sh restore --slot <N> \
  --target /absolute/new/path --allow-target-relocation --plan
cli-tools/scripts/install.sh restore --slot <N> \
  --target /absolute/new/path --allow-target-relocation --apply
```

## Interrupted operations and upstream limits

Ordinary errors and handled termination signals trigger deterministic rollback
and lock cleanup. An uncatchable `SIGKILL` or power loss can leave a sibling
stage, recovery hold, or lock directory. The installer then fails closed rather
than guessing that the transaction owner is dead. Inspect the lock's `owner`
metadata and reconcile the live target, backup slot, and held state before
removing recovery artifacts; preserve uncertain state for manual recovery.
The locks are advisory against cooperative installer processes; filesystem
identity checks additionally prevent cleanup from deleting a same-path object
that another process substituted before a guarded mutation.

Ubuntu DEB installation delegates the system package transaction to `dpkg`.
Before the real transaction, the installer verifies the privately extracted
payload and runs `dpkg --dry-run -i`. It detects package-manager and
postcondition failures, but it cannot transactionally undo changes made inside
a real dpkg transaction. Repair the system package-manager state before
retrying; bootstrap never masks a failed DEB by falling through to AppImage.

The current upstream macOS app is accepted by Gatekeeper as
`source=Notarized Developer ID`, and the installer requires that exact result,
but the DMG does not contain a stapled notarization ticket. If Gatekeeper cannot
establish that assessment, bootstrap fails closed before installation.
