---
description: Run a deep consistency check on the entire repo — read the rule-skills, then verify versions, ZCode-spec, stale paths, broken commands, JSON, secrets, and installer plan.
---

Run the repository health check.

Follow the `doctor` skill exactly. This is a read-only audit — do NOT fix issues,
only report them.

1. **Read the rules first:** `repo-orientation` skill, `zcode-native-format.md`
   reference, `config/nddev-contract.json`, `build/manifest.json`.
2. **Run each step** (1-8) from the `doctor` skill: version parity, ZCode spec
   compliance, stale path detection, broken command detection, JSON validity,
   secrets safety, installer plan (`--plan` for both platforms), cross-reference
   integrity.
3. **Output** a `DOCTOR: PASS | FAIL` verdict with `[PASS|FAIL]` findings per step.
   Cite exact `file:line` for every FAIL.

Use Bash to run the grep/find/python checks. Be thorough — this is the check we
run after every change to catch drift.
