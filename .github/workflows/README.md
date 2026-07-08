# GitHub workflows

The free OSS security suite reuses public workflows from
[`NDDev-it-com/nddev-ci-workflows`](https://github.com/NDDev-it-com/nddev-ci-workflows)
@ `0.3.0` (`f4b2971...`), pinned by full SHA.

## Workflows

- **`validate.yml`** *(custom)* — JSON validation, secret-leak guard, ShellCheck,
  and the installer `--plan` dry-run. Runs on push/PR to `main`.
- **`codeql.yml`** — GitHub CodeQL analysis (Python + Actions, security-and-quality).
  Delegates to `nddev-ci-workflows/public-codeql.yml`. Runs on push/PR + weekly.
- **`dependency-review.yml`** — blocks PRs that introduce high-severity
  vulnerabilities or incompatible licenses. Delegates to `public-dependency-review.yml`.
- **`secret-scan.yml`** — scans tracked files for leaked credentials.
  Delegates to `nddev-ci-workflows/secret-scan.yml`.
- **`scorecard.yml`** — OpenSSF Scorecard analysis (JSON artifact/check mode).
  Delegates to `public-scorecard-json.yml`. Runs on push to `main` + weekly.
- **`cross-platform.yml`** — JSON validation + installer `--plan` on Ubuntu and
  macOS runners. Delegates to `cross-platform-smoke.yml`.
- **`security-static.yml`** *(custom)* — enforces all GitHub Actions are pinned to
  full commit SHAs. Runs on push/PR + weekly.
- **`release.yml`** *(custom)* — tag-driven: on a SemVer tag, verifies it matches
  `VERSION`, extracts the matching `CHANGELOG.md` section, publishes a GitHub Release.
- **`labeler.yml`** *(custom)* — applies area labels based on changed paths.

All external actions are pinned to full commit SHAs; `security-static.yml`
enforces this. The secret-leak guard in `validate.yml` fails CI if any `.env`
is ever tracked.
