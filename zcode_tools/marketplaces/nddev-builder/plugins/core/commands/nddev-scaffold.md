---
description: Compose a complete ZCode plugin from an intent — a metadata-only manifest plus the needed skills, commands, agents, hooks, or MCP — and register it in the marketplace.
---

Compose a whole plugin from a described intent.

Follow the `scaffold-plugin` skill exactly: fix the plugin boundary and the
minimal component set, scaffold with `add-plugin`, add each component with its
`add-*` skill (keeping every basename repo-unique), wire only real dependencies,
and finish with `validate-components` and a clean `install.sh --plan`.
