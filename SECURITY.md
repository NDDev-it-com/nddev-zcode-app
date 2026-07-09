# Security Policy

## Supported surface

Security reporting covers the public implementation in this repository:

- marketplace sources under `zcode_tools/`,
- installer and lifecycle logic under `cli-tools/`,
- version, manifest, system, and secret-template data under `build/`,
- public references, documentation, and GitHub workflows.

## Supported versions

Only the current exact numeric release tag receives security fixes.

| Version | Supported |
| --- | --- |
| Current exact tag `2.0.0` | yes |
| Older tags | no; upgrade to the current exact tag |

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

Never include credentials, tokens, cookies, private keys, or sensitive runtime
logs in a report.

## Response targets

The maintainer aims to acknowledge reports within 5 business days, complete
triage within 10 business days, and provide a fix or mitigation plan for an
accepted report within 30 business days. These targets are best-effort.

## Baseline controls

- External GitHub Actions and reusable workflows are pinned to full commit SHAs.
- Workflow permissions follow least privilege.
- `main` requires verified signatures and linear history; SemVer tags cannot be
  updated or deleted.
- Repository-level release immutability is enabled for future releases.
- Generic CodeQL, dependency-review, secret-scan, and Scorecard checks run in
  this public repository.
- The maintainers' private `nddev-harnesses` control plane validates module
  boundaries, JSON and shell contracts, plan-mode purity, lifecycle behavior,
  restore safety, platform behavior, and release consistency.
- Secrets are rendered from a local, gitignored `build/.env`; only
  `build/.env.example` is tracked.
- Restore and remove refuse existing targets without the installer's
  `BUILD-VERSION` marker.

## Out of scope

- Downstream environments running independently modified versions.
- Problems caused by bypassing the documented installer lifecycle or manually
  deleting its backup pool.
- Availability or behavior of the upstream ZCode service, app, CDN, or model
  provider when the module itself does not cause the issue.
