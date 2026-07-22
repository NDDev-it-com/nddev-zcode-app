# GitHub workflows

The public repository keeps release automation, repository labeling, and generic
security checks. Implementation validation, platform matrices, tests, and
benchmarks run from the maintainers' private `nddev-harnesses` control plane
against a pinned submodule revision.

Reusable workflows are sourced from
[`NDDev-it-com/ci-workflows`](https://github.com/NDDev-it-com/ci-workflows)
release `0.12.0`, pinned to commit
`2ccb80e96f5771b6a6b4eae63a4f47e232906dc7`.

## Workflows

- **`actionlint.yml`** validates every public workflow's syntax and expressions
  through the checksum-verified shared `actionlint.yml` workflow.
- **`codeql.yml`** runs CodeQL for GitHub Actions on pushes, pull requests, and
  the weekly schedule through `public-codeql.yml`.
- **`dependency-review.yml`** checks pull-request dependency changes through
  `public-dependency-review.yml`.
- **`secret-scan.yml`** scans tracked content for exposed credentials through
  `secret-scan.yml`.
- **`scorecard.yml`** runs the public OpenSSF Scorecard JSON workflow on pushes
  and the weekly schedule.
- **`zizmor.yml`** performs pedantic GitHub Actions security analysis, publishes
  SARIF to code scanning, and fails on low-or-higher findings. GitHub permits
  code-scanning result upload for workflows triggered by `pull_request`,
  including fork and Dependabot pull requests.
- **`release.yml`** requires strict SemVer equality across the tag, every build
  contract, and both core-plugin version sources. The tagged commit must be an
  ancestor of freshly fetched `origin/main`. It then calls the shared
  supply-chain workflow to publish one immutable release with two attested
  artifacts -- a deterministic source archive (including the root
  secret-boundary `.gitignore`) and the minimal runtime bundle -- plus
  canonical checksum-bound release notes, an SPDX SBOM, build provenance, and
  SBOM attestations.
- **`labeler.yml`** labels pull requests from `.github/labeler.yml` without
  checking out contributor code. Its hardened runner uses minimal egress and
  per-pull-request concurrency.

All external actions and reusable workflows are pinned to immutable commit SHAs.
The private harness validates those pins and the public/private repository
boundary before a module revision is released.
