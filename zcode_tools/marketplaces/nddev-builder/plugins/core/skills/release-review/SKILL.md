---
name: release-review
description: Reviews a whole ZCode marketplace for release readiness across all plugins — identity and version-lockstep presence, cross-plugin basename safety, inert-field and secret scans, English-only, and a clean install plan. Use before shipping a marketplace, after per-artifact review and static validation.
---

# release-review

A whole-marketplace, cross-artifact readiness gate. `nddev-native-reviewer`
reviews one artifact and `validate-components` runs mechanical static checks;
this skill reviews the **bundle** for release coherence. It is an authoring-time
gate only — it never sets version pins, tags, or release evidence, which are
owned by the repository's private release process.

## What to review (whole marketplace)

1. **Static gate first.** `validate-components` must pass: frontmatter, name
   patterns, JSON validity, cross-plugin basename uniqueness, and a clean
   `install.sh install --setup <mp> --plan`.
2. **Per-artifact quality.** Each new or changed skill, command, and agent passes
   `nddev-native-reviewer` (ZCode-native format plus an actionable trigger
   description).
3. **Identity coherence.** Every plugin's `.zcode-plugin/plugin.json` `name`
   equals its directory and its `marketplace.json` entry; each `source` is a
   local `./plugins/<name>` that exists; descriptions match between the manifest
   and the catalog entry.
4. **Version-lockstep presence.** If the marketplace ships in this release, the
   five version sources agree (see `add-plugin` step 8). Flag any drift; do not
   set pins here.
5. **Execution-boundary hygiene.** No inert `lspServers`/`outputStyles`/
   `channels`/`settings` fields and no manifest component arrays (ZCode 3.3.6
   records but never executes them).
6. **Safety and language.** No secrets, credentials, or machine-local absolute
   paths in any tracked file; English only across code, docs, and manifests.
7. **Install proof.** The `--plan` gate is clean; for a behavioral pass, run
   `devtest-plugin` into isolated state.

## Result

Return PASS only when the static gate, every per-artifact review, and the
whole-bundle coherence checks all succeed. Otherwise return FAIL with the
plugin or component path, the coherence risk, and the correction. Never return a
green result while any check is unproven.
