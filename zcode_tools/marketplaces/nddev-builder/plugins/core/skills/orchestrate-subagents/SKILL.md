---
name: orchestrate-subagents
description: Designs multi-subagent workflows for a ZCode plugin within the 3.3.6 limits — user-scope agents, foreground, parallel-yes/background-no — using Explore for recon and critic panels with on-disk evidence. Use when a plugin needs several agents to cooperate rather than one.
---

# orchestrate-subagents

Compose ZCode subagents into a reliable workflow. Author each agent with
`add-agent`; this skill is about how they cooperate given ZCode's real limits.

## ZCode 3.3.6 subagent constraints (design around these)

- Agents load from **user scope only** (`~/.zcode/agents/`) — the installer
  flattens `agents/`; a plugin-bundled agent is diagnostic-only until flattened.
- **Foreground and parallel are supported; background execution is not** (Beta). A
  subagent runs to completion in the foreground; several can run in parallel.
- Built-in agents: **General-Purpose** and **Explore** (read-only). Prefer
  `Explore` for recon before any write.
- Model per agent: `GLM-5.2`, `GLM-5-Turbo`, or inherit. Invoke with `@`, or let a
  focused `description` auto-select.

## Patterns

1. **Recon then act.** Run `Explore` (read-only) to map the code or surface, then a
   General-Purpose agent to make changes from that map — writes stay informed and
   cheap.
2. **Parallel fan-out.** Split independent work (per-file, per-dimension) across
   several foreground agents run in parallel; merge their results yourself.
3. **Critic panel with evidence.** For a quality gate, run N reviewer agents, each
   with a distinct lens and a **binary yes/no verdict written to an on-disk
   evidence file**; accept only on a majority. Evidence receipts make the gate
   reproducible.
4. **Single responsibility per agent.** Each agent's `description` names one job so
   auto-selection routes correctly; overlapping descriptions cause misrouting.

## Procedure

1. Choose the workflow shape (recon→act, fan-out, or critic panel) from the task.
2. Author each agent with `add-agent` — name, model, focused description, and
   read-only vs writable tools (least privilege).
3. Keep every agent basename unique across the marketplace (the flatten fails
   closed on a collision).
4. Validate with `validate-components`; behaviorally check with `devtest-plugin`.

## Rules

- Never design for background subagents on 3.3.6 — they run foreground.
- Read-only recon (`Explore`) before writes; least-privilege tools per agent.
- Reproducible gates write verdicts to disk, not only to chat.
