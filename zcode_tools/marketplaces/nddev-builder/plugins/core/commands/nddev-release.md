---
description: Prepare a new release of the nddev-zcode-app build — bump version, update changelog, validate, and tag.
---

Prepare a new versioned release of the `~/.zcode` build.

Follow the `release-build` skill exactly:

1. Determine the bump level (default: patch `+0.0.1`; minor/major only when the owner directs).
2. Bump BOTH version sources in sync:
   - `build/version.json` → `"build_version"`
   - `VERSION` (root)
3. Add a `## [X.Y.Z] - YYYY-MM-DD` section to `CHANGELOG.md` (Keep a Changelog format, Added/Changed/Fixed/Security subsections).
4. Validate:
   - both version files show the same number,
   - `cli-tools/scripts/install.sh install --marketplace <name> --platform macos --plan` passes,
   - `cli-tools/scripts/install.sh install --marketplace <name> --platform ubuntu --plan` passes,
   - all JSON files parse.
5. Stage and show the diff for approval. Do NOT commit, tag, or push without explicit confirmation — the tag triggers the release workflow.
