# Security Policy

## Supported surface

Security reporting covers the public implementation in this repository:

- marketplace sources under `zcode_tools/`,
- installer and lifecycle logic under `cli-tools/`,
- version, artifact-integrity, manifest, and secret-template data under `build/`,
- public references, documentation, and GitHub workflows.

## Supported versions

Only the current exact numeric release tag receives security fixes.

| Version | Supported |
| --- | --- |
| Latest numeric release tag | yes |
| Older tags | no; upgrade to the latest release |

## Reporting a vulnerability

Report vulnerabilities privately. Do not open a public issue or pull request
that contains exploit details or sensitive material.

Preferred channel: [GitHub Security Advisories](https://github.com/NDDev-it-com/nddev-zcode-app/security/advisories/new).

Alternatively, contact the maintainer through
[@rldyourmnd](https://github.com/rldyourmnd) and request a private disclosure
channel.

Include:

- affected path, installer step, or workflow,
- reproduction steps and expected impact,
- the relevant threat scenario,
- non-sensitive logs or output,
- a suggested fix, if known.

Never include credentials, tokens, cookies, private keys, rendered provider or
MCP configs, `.env` files, `v2/credentials.json`, backup contents, or sensitive
runtime logs in a report.

## Response targets

The maintainer aims to acknowledge reports within 5 business days, complete
triage within 10 business days, and provide a fix or mitigation plan for an
accepted report within 30 business days. These targets are best-effort.

## Baseline controls

- External GitHub Actions and reusable workflows are pinned to full commit SHAs.
- Workflow permissions follow least privilege.
- The privileged pull-request labeler does not check out or execute contributor
  code. Runner hardening starts first, egress is allowlisted, and concurrency is
  isolated per pull-request number.
- `main` requires verified signatures and linear history; SemVer tags cannot be
  updated or deleted.
- Repository merges are squash-only with the pull-request title as the commit
  title and an empty generated body. Branch updates are allowed, merged branches
  are deleted automatically, and unused wiki/projects surfaces are disabled.
- Repository-level release immutability is enabled; numeric releases publish
  checksum-bound canonical release notes, an SPDX SBOM, build provenance, and
  an SBOM attestation through the SHA-pinned shared supply-chain workflow.
- Release verification requires strict SemVer equality across the tag, module
  build contracts, and both core-plugin version sources. The tagged commit must
  also be an ancestor of a freshly fetched `origin/main`.
- Generic actionlint, pedantic zizmor SARIF, CodeQL, dependency-review,
  secret-scan, and Scorecard checks run in this public repository.
- The maintainers' private `nddev-harnesses` control plane validates module
  boundaries, JSON and shell contracts, plan-mode purity, lifecycle behavior,
  restore safety, platform behavior, and release consistency.
- Secrets are rendered from a local, gitignored `build/.env`; only
  `build/.env.example` is tracked. The real file must be a current-user-owned
  regular non-symlink with mode `0600` or stricter. It is parsed without shell
  evaluation; only target/backup path keys support narrow leading HOME-prefix
  expansion.
- Plan and apply both reject missing or empty placeholders in keys or values
  across active config, setting, provider, MCP, and hook branches. Only
  explicitly disabled provider/MCP nodes may retain dormant placeholders.
- The installed target and backups are private to the current user; rendered
  secret-bearing files and restored credentials use owner-only permissions.
- Downloaded ZCode artifacts are verified against pinned byte sizes and SHA-512
  digests before platform-native package or signing identity checks. The
  current pins were revalidated against repeated current CDN downloads; a digest
  mismatch is fatal even when the byte size still matches.
- Bootstrap requires the exact canonical CDN base, locks each installer-managed
  app endpoint and user launcher, and retains rollback state until strict
  postconditions define a commit. Post-commit cleanup failure is visible but
  never rolls back verified committed state.
- DEB bootstrap privately extracts the payload and requires one safe
  `/opt/ZCode/resources/glm/zcode.cjs` entry with the pinned CLI version before
  a successful privileged `dpkg --dry-run -i`. After installation, the exact
  dpkg-owned path/version and SHA-512 equality with that verified entry are
  required.
- Runtime CLI probing resolves one canonical executable and limits execution to
  3 seconds and 64 KiB of output. Normal install treats probe failure as
  advisory unknown state; bootstrap rejects it as a failed postcondition.
- Lifecycle mutations use canonical/disjoint path checks, target and backup-pool
  locks, same-filesystem staging, pre-commit verification, atomic rename, and
  rollback of both live state and a displaced rotation slot. Managed inputs
  reject symlinks, special files, and hardlink aliases, and verified stages are
  fsynced before commit.
- Restore and remove require a fully validated managed stamp. Install refuses
  an unstamped existing target unless explicit adoption names that target;
  adopted state is stored in a typed, target-bound backup envelope.
- Errors and handled signals clean up transaction state. Uncatchable termination
  or power loss can leave fail-closed locks or recovery holds for operator
  inspection; the installer never silently steals or deletes them.

## Out of scope

- Downstream environments running independently modified versions.
- Problems caused by bypassing the documented installer lifecycle or manually
  deleting its backup pool.
- Availability or behavior of the upstream ZCode service, app, CDN, or model
  provider when the module itself does not cause the issue.
