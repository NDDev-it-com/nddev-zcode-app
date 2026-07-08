# Security Policy

## Supported Surface

Security reporting covers this repository's `~/.zcode` source tree
(`zcode_tools/`), the installer (`cli-tools/`), build artifacts and secret
templates (`build/`), and CI/CD workflows (`.github/`).

## Supported Versions

Only the current exact numeric release tag receives security fixes.

| Version | Supported |
|---|---|
| Current exact tag `1.0.0` | yes |
| Older tags | no; upgrade to current exact tag |

## Reporting a Vulnerability

Please report vulnerabilities privately. Do not open public issues or pull
requests describing them.

Preferred channel: GitHub Security Advisories.

- https://github.com/NDDev-it-com/nddev-zcode-app/security/advisories/new

Alternative channel: contact the maintainer through their GitHub profile at
https://github.com/rldyourmnd and request a private disclosure handle.

Include:

- affected path, file, installer step, or workflow,
- reproduction steps,
- expected impact and threat scenario,
- non-sensitive logs or command output,
- a suggested fix when known.

Do not paste credentials, tokens, cookies, private keys, or sensitive logs into
reports. If a report requires sharing sensitive material, request a secure
channel before sending.

## Response Targets

The maintainer aims for:

- acknowledgement within 5 business days,
- triage and severity assessment within 10 business days,
- a fix or mitigation plan for accepted reports within 30 business days,
  depending on complexity.

These targets are best-effort and not contractual.

## Baseline Controls

- External GitHub Actions are pinned to full commit SHAs.
- CI uses least-privilege `GITHUB_TOKEN` permissions by default.
- The `validate` workflow fails if any `.env` file (including `build/.env`) is
  tracked by git.
- Secrets are rendered from a local, gitignored `build/.env` at install time;
  no secret values are committed.

## Out Of Scope

- Findings against downstream environments running modified versions of this
  software.
- Issues stemming from running the installer's `--apply` mode (which wipes and
  rebuilds `~/.zcode`) without keeping the automatic backup. The installer
  always creates a backup before applying; reverting is documented in
  [docs/install.md](docs/install.md).
