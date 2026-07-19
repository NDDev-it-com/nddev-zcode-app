---
description: Review a whole marketplace for release readiness — identity and version-lockstep presence, cross-plugin basename safety, inert-field and secret scans, and a clean install plan.
---

Review a whole marketplace for release readiness.

Follow the `release-review` skill exactly: run `validate-components`, pass each
new or changed artifact through `nddev-native-reviewer`, then check bundle
coherence — plugin identity, version-lockstep presence, no inert fields, no
secrets, English only, and a clean `install.sh --plan`. Authoring-time gate only;
never set pins, tags, or evidence.
