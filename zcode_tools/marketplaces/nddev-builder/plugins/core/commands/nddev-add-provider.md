---
description: Add a model provider (LLM endpoint) to a marketplace's v2-config template — covers anthropic/openai-style providers, API key placeholders, and model definitions.
---

Add a model provider to a marketplace.

Follow the `add-provider` skill exactly:

1. Ask the user for: provider name, API kind (anthropic/openai), base URL, API key env var name, model ID(s), and enabled status.
2. Add the provider entry to `v2-config.template.json` under `provider`.
   Explicit API-key providers use `source: custom`. For Z.ai, use
   `https://api.z.ai/api/anthropic` and preserve the separate `zai: oauth`
   account preference; BigModel uses `https://open.bigmodel.cn/api/anthropic`.
3. Add the `${API_KEY_VAR}` placeholder to `build/.env.example` (empty value).
4. Remind the user to fill the real value in `build/.env` (gitignored).
5. Validate JSON and run `install --plan`.
