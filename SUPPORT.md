# Support

Use public GitHub Issues for this repository for:

- installer behavior defects (backup, build, restore, verify),
- rendered config drift or invalid JSON,
- documentation or version-stamp issues.

For security reports, use a private advisory at the repository security page.
Do **not** open public issue text for exploit details.

When filing an issue, include:

- environment details (OS, ZCode client version, Python version),
- the `--plan` output (or `--apply` output if it failed),
- the relevant `BUILD-VERSION` contents,
- sanitized logs and minimal repro steps.

Never attach `.env` files, rendered provider or MCP configs,
`v2/credentials.json`, certificates, or backup contents. Redact tokens, API
keys, paths containing private account information, and other sensitive values.
