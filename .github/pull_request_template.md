## Scope

Describe the `zcode_tools/`, `cli-tools/`, `build/`, or documentation surface changed.

## Validation

- [ ] JSON files valid (`python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('**/*.json', recursive=True)]"`)
- [ ] `cli-tools/scripts/install.sh --plan` runs clean
- [ ] No `.env` tracked (`git ls-files | grep -E '(^|/)\.env$'` returns nothing)
- [ ] Targeted smoke/checks for the touched scope

## Release

- [ ] `build/version.json` and `VERSION` bumped when release behavior changes
- [ ] `CHANGELOG.md` entry added for release behavior changes
