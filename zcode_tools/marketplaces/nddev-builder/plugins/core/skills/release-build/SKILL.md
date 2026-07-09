---
name: release-build
description: Cut a new release of the nddev-zcode-app build. Bumps build/version.json, VERSION, and pyproject.toml in sync, adds a CHANGELOG.md entry, validates the installer --plan runs clean, and prepares the SemVer tag. Use when releasing a new build version.
---

# release-build

Prepares a new versioned release of the `~/.zcode` build.

## Version sources (keep in sync)

Three files hold the build version and must always match:

- `build/version.json` → `build_version` field
- `VERSION` (root, single line)
- `pyproject.toml` → `[project]` → `version`

The installer reads `build/version.json`; the `release.yml` workflow refuses to publish
a tag that does not match `VERSION`; the version-parity test asserts all three agree.

## Procedure

1. **Decide the bump.**
   - **patch** `+0.0.1` — default, for any source/config/doc change after a release exists.
   - **minor** `+0.1.0` — new backward-compatible capability (e.g. a new plugin).
   - **major** `+1.0.0` — breaking change to the installer contract or `~/.zcode` layout.
   The owner directs minor/major; patch is the default.

2. **Bump all three files to the new version** (e.g. `1.0.0` → `1.0.1`):
   - `build/version.json` → `"build_version": "1.0.1"`
   - `VERSION` → `1.0.1`
   - `pyproject.toml` → `version = "1.0.1"` (under `[project]`)

3. **Add a CHANGELOG entry.** Under `## [Unreleased]` (or create it), add a new section:
   ```markdown
   ## [1.0.1] - YYYY-MM-DD
   ### Added
   - <what>
   ### Changed
   - <what>
   ```
   Use `Added` / `Changed` / `Fixed` / `Security` subsections as needed. Keep a Changelog format.

4. **Validate locally:**
   ```bash
   python3 -c "import json; print(json.load(open('build/version.json'))['build_version'])"
   cat VERSION
   python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
   cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan
   cli-tools/scripts/install.sh install --marketplace <name> --platform ubuntu --plan
   # Validate every marketplace manifest:
   for f in zcode_tools/marketplaces/*/marketplace.json; do
     python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f"
   done
   ```
   All version numbers must agree; both `--plan` runs must finish `[ok] all checks passed`.

5. **Commit** with `chore(release): prepare vX.Y.Z` (or `feat`/`fix` if the release
   carries a behavior change).

6. **Tag + push** (triggers `release.yml`):
   ```bash
   git tag X.Y.Z
   git push origin main --tags
   ```
   The tag must match `VERSION` exactly. `release.yml` verifies this, extracts the
   matching CHANGELOG section, and publishes the GitHub Release.

## Rules

- `build/version.json` and `VERSION` must be identical before tagging.
- SemVer tags only: `X.Y.Z` or `X.Y.Z-pre`.
- Never skip the `--plan` validation before tagging.
- The owner approves minor/major bumps; patch is the default.
