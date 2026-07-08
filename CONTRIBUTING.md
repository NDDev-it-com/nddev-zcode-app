# Contributing

This repository is `nddev-zcode-app`, a build system + installer that recreates
a complete, version-stamped `~/.zcode` from source on macOS and Ubuntu. It is
maintained by [@rldyourmnd](https://github.com/rldyourmnd). Contributions are
welcome under the project's AGPL-3.0-or-later license, but the maintainer keeps
final authority on direction, plugin boundaries, the installer contract, and the
backup/restore policy.

By submitting a pull request, you certify that you have the right to license the
contribution under AGPL-3.0-or-later.

Participants must follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

This project is licensed under the GNU Affero General Public License v3.0 or
later. See [LICENSE](LICENSE). Contributions are accepted under the same
license; downstream operators that run modified versions over a network must
comply with AGPL-3.0 Section 13.

## Local Setup

Required tools: Git, Python 3.13, and the ZCode client.

```bash
cp build/.env.example build/.env   # then fill in real values
cli-tools/scripts/install.sh install --marketplace nddev-builder --plan   # dry-run
cli-tools/scripts/install.sh install --marketplace nddev-builder --apply  # back up, build, restore
```

## Branches

- `main`: primary integration branch.
- `feat/<topic>`, `fix/<topic>`, `chore/<topic>`: feature/fix/chore branches.
  Open a pull request targeting `main`.

## Pull Requests

- Open a pull request against `main` with a clear, scope-limited change.
- Title format: Conventional Commits (`type(scope): description`). Types:
  `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `style`, `ci`,
  `build`. Scope is the area, lowercase.
- Description must include intent, surface touched, evidence (installer
  `--plan` output, validation logs), and risks.
- Keep commits atomic. Do not rewrite already-pushed history without explicit
  maintainer approval.

## Change Rules

- Keep repository artifacts in English.
- Never commit credentials, tokens, cookies, private keys, or `build/.env`.
  The `validate` workflow enforces this.
- Bump `build/version.json` and `VERSION`, and add a `CHANGELOG.md` entry for
  release behavior changes.
- When adding ZCode components, follow the native format: plugin components are
  convention-discovered (`skills/<n>/SKILL.md`, `commands/<n>.md`,
  `agents/<n>.md`); MCP servers use `{"mcpServers":{}}` in
  `plugins/<mcps>/.mcp.json`; hooks and the MCP registry live in
  `cli/config.json`.
