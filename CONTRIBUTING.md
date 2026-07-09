# Contributing

`nddev-zcode-app` is the public, reusable implementation of the NDDev ZCode
setup installer. Contributions are welcome under AGPL-3.0-or-later. The
maintainer retains final authority over installer contracts, ZCode-native
format, setup boundaries, and backup/restore safety.

By submitting a pull request, you certify that you can license the contribution
under AGPL-3.0-or-later. Participants must follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Repository boundary

Keep this repository limited to code and public documentation required to use
or distribute the module. Do not add repository-local agent instructions,
development memories, test suites, validation implementations, benchmarks, or
generated development artifacts.

The maintainers keep those control-plane concerns in the private
`nddev-harnesses` repository, where this module is pinned as a submodule. Public
contributors are not expected to have access to that harness; maintainers run
its full validation and platform matrix before merging or releasing changes.

## Local setup

Required tools are Git, Bash, and Python 3.10+. A local ZCode installation is not
required for plan-mode validation.

```bash
cli-tools/scripts/install.sh list
cli-tools/scripts/install.sh install \
  --marketplace nddev-builder --platform macos --plan
cli-tools/scripts/install.sh install \
  --marketplace nddev-builder --platform ubuntu --plan
```

Plan mode performs no writes and does not invoke a local `zcode` binary. Never
use `--apply` against a real target merely to validate a pull request.

## Pull requests

- Target `main` from a scope-limited feature or fix branch.
- Use a Conventional Commit title such as `fix(installer): preserve plan purity`.
- Explain intent, affected public contract, plan-mode evidence, and risks.
- Keep implementation, documentation, and version changes consistent.
- Do not rewrite pushed shared history without maintainer approval.

## Change rules

- Keep repository artifacts in English.
- Never commit credentials, tokens, cookies, private keys, `build/.env`, runtime
  state, caches, or generated ZCode output.
- Treat an installed target and its backups as sensitive: never print, attach,
  or commit `.env`, rendered provider/MCP configs, `v2/credentials.json`,
  certificates, or backup contents.
- Preserve ZCode convention discovery: plugin components live under
  `skills/`, `commands/`, `agents/`, and `references/`; metadata stays in
  `.zcode-plugin/plugin.json`.
- For a release, use one strict SemVer in `VERSION`, the `build_version` fields
  in `build/version.json` and `build/manifest.json`, the `nddev-builder`
  marketplace `core` entry, and the core `.zcode-plugin/plugin.json` manifest.
  The release workflow rejects drift.
- Add a `CHANGELOG.md` entry for release behavior changes.
- Treat backup, restore, remove, target resolution, and plan purity as safety
  contracts. Changes to them require regression coverage in the private harness.

## License

This project is licensed under GNU AGPL v3.0 or later. See [LICENSE](LICENSE).
Downstream operators that run modified versions over a network must comply with
AGPL-3.0 Section 13.
