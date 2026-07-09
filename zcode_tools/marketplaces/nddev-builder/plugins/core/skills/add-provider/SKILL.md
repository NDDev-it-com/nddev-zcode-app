---
name: add-provider
description: Add a model provider to a marketplace's v2-config template. Covers the provider shape (name, kind, options.apiKey, options.baseURL, enabled, source, models), secret placeholder handling, and both anthropic and openai-style providers. Use when adding a new LLM provider (e.g. OpenAI, Anthropic, a custom endpoint) to a ZCode setup.
---

# add-provider

Adds a model provider definition to `v2-config.template.json`.

## Provider shape

```json
{
  "provider": {
    "<provider-key>": {
      "name": "<Display Name>",
      "kind": "anthropic",
      "options": {
        "apiKey": "${API_KEY_VAR}",
        "baseURL": "https://api.example.com/v1"
      },
      "enabled": true,
      "source": "builtin",
      "models": {
        "<model-id>": {
          "limit": { "context": 200000 },
          "modalities": { "input": ["text"], "output": ["text"] }
        }
      }
    }
  }
}
```

### Fields

- **`<provider-key>`** — unique key, convention `builtin:<name>-<plan>`.
- **`name`** — human-readable display name.
- **`kind`** — `"anthropic"` (Anthropic-compatible API) or `"openai"`
  (OpenAI-compatible API). Determines the request format ZCode uses.
- **`options.apiKey`** — `${VAR_NAME}` placeholder (uppercase). The installer
  renders it from `build/.env` at install time.
- **`options.baseURL`** — the API endpoint URL.
- **`enabled`** — `true` to activate, `false` to define but disable.
- **`source`** — `"builtin"` (ZCode knows this provider natively) or
  `"custom"` (user-defined).
- **`models`** — map of model IDs to their limits. `limit.context` =
  max context window. `modalities.input`/`output` = supported types
  (`"text"`, `"image"`). Optional model fields: `limit.output` (max output
  tokens), `name` (upstream API model id if it differs from the map key),
  `reasoning` (`{enabled, variants, defaultVariant}` for reasoning-capable
  models — see `builtin:bigmodel-coding-plan` → `GLM-5-Turbo` in the builder
  template for a real example).

## Procedure

1. Ask the user for:
   - Provider display name and key (e.g. `builtin:openai-coding`).
   - API kind: `anthropic` or `openai`.
   - Base URL (the API endpoint).
   - API key env var name (e.g. `OPENAI_API_KEY`) — must be uppercase.
   - Model ID(s) and context window size(s).
   - Enabled or disabled by default.

2. Read `v2-config.template.json` and confirm the provider key is not already
   present. If it is, ask whether to overwrite.

3. Add the provider entry to the `provider` object.

4. Add the secret placeholder to `build/.env.example`:
   ```
   # <Provider display name> API key
   <API_KEY_VAR>=
   ```
   Place it under the `# ─── Provider secrets` section. If the var already
   exists, skip.

5. Remind the user to add the real value to `build/.env` (gitignored):
   ```
   cp build/.env.example build/.env  # if not done yet
   $EDITOR build/.env                 # fill in <API_KEY_VAR>
   ```

6. Validate:
   ```bash
   python3 -c "import json; json.load(open('zcode_tools/marketplaces/<mp>/v2-config.template.json'))"
   cli-tools/scripts/install.sh install --marketplace <mp> --platform macos --plan
   ```

## Rules

- API key is ALWAYS a `${VAR}` placeholder — never a real value in the template.
- The env var name must be uppercase (`[A-Z0-9_]`).
- Add the matching key to `build/.env.example` (committed, empty value).
- `credentials.json` (auth tokens) is restored from backup, NOT templated here.
- English only.
