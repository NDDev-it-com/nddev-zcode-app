# Secrets

Secrets never live in `zcode_tools/` (the source of `~/.zcode`) and are never
committed to the repository. They are rendered into the config files at install
time from a local, gitignored `build/.env`.

## Contract

- **`build/.env.example`** — committed. Lists every secret key the build needs,
  with empty values and a comment explaining each. This is the template.
- **`build/.env`** — gitignored (`build/.gitignore`). Holds the real values.
  Created by copying the example.
- **Placeholders** — config templates in `zcode_tools/` reference secrets as
  `${VAR_NAME}`. The installer substitutes each placeholder with the matching
  value from `build/.env` (or the process environment). Unknown placeholders are
  left as-is so a missing optional secret never breaks the build.

## Setup

```bash
cp build/.env.example build/.env
$EDITOR build/.env   # fill in real values
```

## Which templates use secrets

Templates live inside each marketplace directory:
`zcode_tools/marketplaces/<name>/`.

- `v2-config.template.json` — provider API keys:
  `${ZAI_API_KEY}`, `${BIGMODEL_API_KEY}`.
- `mcp.json` / `cli-config.template.json` — MCP server secrets:
  `${GITHUB_PERSONAL_ACCESS_TOKEN}`, `${CONTEXT7_API_KEY}`, etc.

## credentials.json is NOT a secret in this sense

`~/.zcode/v2/credentials.json` holds the ZCode desktop app auth tokens. It is
**restored from the backup** by the installer, never templated and never
committed. This is why backups live under `~/.zcode-backups/` (outside the repo),
not inside the repository tree.

## Repository guards

Public secret scanning checks tracked content for exposed credentials. The
maintainers' private harness also rejects any tracked `.env` file as a module
boundary violation. Keep real values only in your local `build/.env`.
