# Secrets

Repository source and the installed ZCode home have different security
boundaries. Source templates contain placeholders only. The rendered ZCode
home can contain live API keys, tokens, credentials, MCP headers, certificates,
and session state and must be treated as sensitive runtime data.

## Source contract

- `build/.env.example` is committed and declares supported keys with empty
  values and explanatory comments.
- `build/.env` is local and gitignored. Copy the example only when explicit
  API-key providers, integrations, or custom target settings are needed.
- When present, `build/.env` must be a current-user-owned regular non-symlink
  file with no group or world permission bits (`0600` or stricter). The
  installer rejects the file before reading or copying it otherwise.
- Existing process-environment values take precedence. Only `ZCODE_TARGET` and
  `ZCODE_BACKUPS_DIR` expand an exact leading literal `$HOME`, `$HOME/`,
  `${HOME}`, or `${HOME}/` prefix. Every other value remains literal.
- Marketplace JSON inputs reference secrets as `${VAR_NAME}`. Every referenced
  key must be declared in `build/.env.example`; real values never belong in a
  source template.
- `build/.env` is key/value data, not a shell program. Do not execute it with
  `source`, `.`, or `eval`.

```bash
cp build/.env.example build/.env
chmod 600 build/.env
$EDITOR build/.env
```

## Authentication modes

Z.ai account authentication and explicit provider API keys are separate:

- `modelProviderFamilyModes.zai: oauth` in `v2/setting.json` is the verified
  ZCode 3.3.4 default for account login. It does not require `ZAI_API_KEY`.
- `ZAI_API_KEY` configures the explicit custom Z.ai provider at
  `https://api.z.ai/api/anthropic`. That provider is disabled by default; set
  its `enabled` field to `true` only after supplying the key.
- `BIGMODEL_API_KEY` configures the separate BigModel provider at
  `https://open.bigmodel.cn/api/anthropic`; that provider is also disabled by
  default and must be enabled deliberately after supplying the key.

Provider secrets are rendered into `v2/config.json`. MCP secrets referenced in
`mcp.json` are rendered before their entries are merged into `cli/config.json`.
Rendering is structured and JSON-escapes values; env text is never evaluated as
shell syntax. Placeholder-bearing object keys are never substituted and are
rejected instead. Missing and empty values remain visibly unresolved. Plan and
apply both parse, substitute, and merge config, setting, provider, MCP, and hook
inputs, then refuse unresolved placeholders in keys or values throughout every
active branch. Only explicitly disabled provider or MCP entries may remain
dormant.

## Sensitive runtime paths

The following installed or backup paths can contain secrets:

- `~/.zcode/.env` or the equivalent custom target path;
- `~/.zcode/v2/config.json`;
- `~/.zcode/cli/config.json`;
- `~/.zcode/v2/credentials.json`;
- `~/.zcode/v2/certs/` and other restored account/session state;
- `~/.zcode-backups/` or the configured backup directory.

An adopted-unmanaged backup also contains `NDDEV-BACKUP.json` with the original
canonical target path. Treat that path as private environment metadata and
redact it from shared diagnostics together with the envelope payload.

`v2/credentials.json` is unequivocally a secret: it holds ZCode desktop account
authentication tokens. The installer restores it from protected backup state
rather than templating it, but that does not make it safe to disclose.

Target and backup directories must be private to the current user (`0700`).
Installed secret-bearing files, including `.env`, rendered configs, and
credentials, must be owner-readable and owner-writable only (`0600`). The local
source `build/.env` may be stricter but may never grant group/world access.

## Handling rules

- Never print, trace, commit, upload, attach, or paste runtime secret files or
  their values into logs, issues, pull requests, screenshots, or diagnostics.
- Do not place backups inside a repository tree or a shared directory.
- Pass CLI-tool credentials through an approved process environment. Prefer a
  project-provided launcher, secrets manager, or non-evaluating parser with an
  explicit key allowlist; never shell-source an env file.
- Redact values before reporting configuration errors. It is safe to name a
  missing variable, but not to echo its value.
- Rotate any credential immediately if a runtime file or backup was exposed.

## Repository guards

Public secret scanning checks tracked content for exposed credentials. The
maintainers' private harness additionally enforces the module boundary and
rejects tracked local env files. Automated guards supplement, but do not
replace, the handling rules above.
