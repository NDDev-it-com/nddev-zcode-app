# GitHub workflows

- **`validate.yml`** — JSON validation, secret-leak guard, ShellCheck, and the
  installer `--plan` dry-run. Runs on push/PR to `main`.
- **`security-static.yml`** — action-pin enforcement (full SHA) and tracked-secret
  scan. Runs on push/PR to `main` and weekly.
- **`cross-platform.yml`** — JSON validation + installer `--plan` on Ubuntu and
  macOS runners. Runs on push/PR to `main`.
- **`labeler.yml`** — applies area labels based on changed paths.

All external actions are pinned to full commit SHAs; `security-static.yml`
enforces this. The secret-leak guard fails CI if any `.env` is ever tracked.
