# GitHub workflows

The public repository keeps release automation, repository labeling, and generic
security checks. Implementation validation, platform matrices, tests, and
benchmarks run from the maintainers' private `nddev-harnesses` control plane
against a pinned submodule revision.

Reusable workflows are sourced from
[`NDDev-it-com/nddev-ci-workflows`](https://github.com/NDDev-it-com/nddev-ci-workflows)
release `0.3.0`, pinned to commit
`1acba687361415b3f5942acceb40b228bb0387fd`.

## Workflows

- **`codeql.yml`** runs CodeQL for GitHub Actions on pushes, pull requests, and
  the weekly schedule through `public-codeql.yml`.
- **`dependency-review.yml`** checks pull-request dependency changes through
  `public-dependency-review.yml`.
- **`secret-scan.yml`** scans tracked content for exposed credentials through
  `secret-scan.yml`.
- **`scorecard.yml`** runs the public OpenSSF Scorecard JSON workflow on pushes
  and the weekly schedule.
- **`release.yml`** verifies a SemVer tag against all three build-version
  sources, checks core-plugin version parity, extracts the matching changelog
  section, and publishes the GitHub Release.
- **`labeler.yml`** labels pull requests from `.github/labeler.yml`.

All external actions and reusable workflows are pinned to immutable commit SHAs.
The private harness validates those pins and the public/private repository
boundary before a module revision is released.
