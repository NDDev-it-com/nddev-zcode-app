# GitHub workflows

- **`validate.yml`** — JSON validation, secret-leak guard, ShellCheck, and the
  installer `--plan` dry-run. Runs on push/PR to `main`.
- **`security-static.yml`** — action-pin enforcement (full SHA) and tracked-secret
  scan. Runs on push/PR to `main` and weekly.
- **`cross-platform.yml`** — JSON validation + installer `--plan` on Ubuntu and
  macOS runners. Runs on push/PR to `main`.
- **`codeql.yml`** — GitHub CodeQL analysis (Python + Actions). Runs on push/PR
  to `main` and weekly. Delegates to `nddev-ci-workflows`.
- **`dependency-review.yml`** — blocks PRs that introduce high-severity
  vulnerabilities or incompatible licenses. Delegates to `nddev-ci-workflows`.
- **`scorecard.yml`** — OpenSSF Scorecard analysis (JSON artifact/check mode).
  Runs on push to `main` and weekly. Delegates to `nddev-ci-workflows`.
- **`release.yml`** — tag-driven: on a SemVer tag, verifies it matches `VERSION`,
  extracts the matching `CHANGELOG.md` section, and publishes a GitHub Release.
- **`labeler.yml`** — applies area labels based on changed paths.

All external actions are pinned to full commit SHAs; `security-static.yml`
enforces this. The secret-leak guard fails CI if any `.env` is ever tracked.

The `codeql`, `dependency-review`, and `scorecard` workflows reuse public
workflows from [`NDDev-it-com/nddev-ci-workflows`](https://github.com/NDDev-it-com/nddev-ci-workflows)
(the estate's shared CI library), pinned by full SHA.
