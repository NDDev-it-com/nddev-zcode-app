---
description: Statically pre-check a marketplace's components before install (frontmatter, names, cross-plugin collisions).
---

Validate a marketplace's components before install.

Follow the `validate-components` skill exactly: check skill/command/agent
frontmatter and name patterns, description length (≤1024), JSON validity, and —
most importantly — that no two plugins share a skill/command/agent basename
(the installer flattens to user scope and fails closed on a collision). Finish
with `install.sh install --setup <mp> --plan` as a non-mutating gate.
