---
description: Design a multi-subagent workflow for a plugin within ZCode 3.3.6 limits (user-scope, foreground, parallel-yes/background-no).
---

Design how several subagents cooperate in a plugin.

Follow the `orchestrate-subagents` skill exactly: choose a shape (recon→act with
`Explore`, parallel fan-out, or a critic panel with on-disk evidence receipts),
author each agent with `add-agent` (focused description, least-privilege tools,
unique basename), and validate. Never design for background subagents — they run
foreground on 3.3.6.
