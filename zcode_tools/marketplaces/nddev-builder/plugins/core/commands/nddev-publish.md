---
description: Distribute a ZCode marketplace via a GitHub repo, Git URL, local path, or ZIP URL for install through the ZCode Marketplace tab.
---

Distribute a marketplace beyond this repo's installer.

Follow the `publish-marketplace` skill exactly: pass `validate-components` and
`release-review`, make the root `marketplace.json` self-describing (local `source`
for the headless installer, remote `{source:"github",repo:...}` for UI install),
ship portable `.zcode-plugin` (+ optional `.claude-plugin`) manifests, push to a
GitHub repo / Git URL / ZIP URL, and document adding it via the ZCode Marketplace
tab. There is no CLI `plugin add`.
