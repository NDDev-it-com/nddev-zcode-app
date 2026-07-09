# Pull request

## Scope

Describe the `zcode_tools/`, `cli-tools/`, `build/`, or documentation surface changed.

## Validation

- [ ] JSON files validate with Python's standard library
- [ ] Installer plan runs clean for the affected marketplace on macOS and Ubuntu
- [ ] No `.env` tracked (`git ls-files | grep -E '(^|/)\.env$'` returns nothing)
- [ ] No development-only agent, test, validation, benchmark, or runtime
      artifacts added
- [ ] Targeted smoke/checks for the touched scope

## Release

- [ ] The three build-version sources match for release behavior changes
- [ ] Core-plugin versions match between `marketplace.json` and `plugin.json`
- [ ] `CHANGELOG.md` entry added for release behavior changes
