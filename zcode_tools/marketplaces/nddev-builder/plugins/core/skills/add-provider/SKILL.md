---
name: add-provider
description: Adds a model provider to a marketplace's config template. Use when adding or configuring an LLM provider — OpenAI, Anthropic, or a custom OpenAI-compatible endpoint — or wiring provider models, base URL, or API-key placeholders into a ZCode setup.
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
      "source": "custom",
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

- **`<provider-key>`** — unique key. Use the repository's established key when
  updating an existing provider; use `custom:<name>` for a new API-key provider.
  A custom provider must never reuse a ZCode-owned `builtin:*` identity.
- **`name`** — human-readable display name.
- **`kind`** — `"anthropic"` (Anthropic-compatible API) or `"openai"`
  (OpenAI-compatible API). Determines the request format ZCode uses.
- **`options.apiKey`** — `${VAR_NAME}` placeholder (uppercase). The installer
  renders it from `build/.env` at install time.
- **`options.baseURL`** — the API endpoint URL.
- **`enabled`** — `true` to activate, `false` to define but disable.
- **`source`** — use `"custom"` for every user-defined or explicit API-key
  provider. Use `"builtin"` only when a verified ZCode-native definition
  explicitly requires it; never infer it from the provider's brand name.
- **`models`** — map of model IDs to their limits. `limit.context` =
  max context window. `modalities.input`/`output` = supported types
  (`"text"`, `"image"`). Optional model fields: `limit.output` (max output
  tokens), `name` (upstream API model id if it differs from the map key),
  `reasoning` (`{enabled, variants, defaultVariant}` for reasoning-capable
  models — see `custom:bigmodel-api-key` → `GLM-5-Turbo` in the builder
  template for a real example).

### Documented providers (ZCode 3.3.6)

Beyond OpenAI and Anthropic, ZCode 3.3.6 documents **GLM Coding Plan (Z.ai and
BigModel), OpenRouter, Moonshot, MiniMax, and Xiaomi MiMo**, plus custom
Anthropic/OpenAI-compatible endpoints. Author each as a `custom:*` provider with
the matching `kind` (`anthropic` or `openai`) and its base URL. Verified GLM
endpoints: Z.ai `https://api.z.ai/api/anthropic`, BigModel
`https://open.bigmodel.cn/api/anthropic`; models `GLM-5.2` and `GLM-5-Turbo`.
Account authentication ("Continue with Z.ai / BigModel") uses the OAuth preference
(`modelProviderFamilyModes.zai: oauth`); explicit API keys are `custom:*`
providers. Never reuse a ZCode-owned `builtin:*` identity for a custom provider.

## Procedure

1. Ask the user for:
   - Provider display name and key (e.g. `custom:openai-coding`).
   - API kind: `anthropic` or `openai`.
   - Base URL (the API endpoint).
   - API key env var name (e.g. `OPENAI_API_KEY`) — must be uppercase.
   - Model ID(s) and context window size(s).
   - Enabled or disabled by default.

2. Read `v2-config.template.json` and confirm the provider key is not already
   present. If it is, ask whether to overwrite.

3. Add the provider entry to the `provider` object.

   For an explicit Z.ai API-key provider, use kind `anthropic`, source
   `custom`, an identity such as `custom:zai-api-key`, and base URL
   `https://api.z.ai/api/anthropic`. Do not replace the separate
   `modelProviderFamilyModes.zai: oauth` account preference or the secret-free
   `builtin:zai-coding-plan` bootstrap in `cli-config.template.json`. BigModel
   API-key providers use an identity such as `custom:bigmodel-api-key` and base
   URL `https://open.bigmodel.cn/api/anthropic`.

4. Add the secret placeholder to `build/.env.example`:

   ```dotenv
   # <Provider display name> API key
   <API_KEY_VAR>=
   ```

   Place it under the `# ─── Provider secrets` section. If the var already
   exists, skip.

5. Remind the user to add the real value to `build/.env` (gitignored):

   ```bash
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
- Custom API-key providers use `custom:*` identities and never shadow
  ZCode-owned `builtin:*` providers.
- `cli-config.template.json` must retain an explicit `provider/model` main
  model reference plus a matching secret-free provider/base-URL/model
  declaration; OAuth credentials are mounted by ZCode at runtime.
- `credentials.json` contains account auth tokens and is restored from backup,
  not templated. Treat it as a secret.
- English only.
