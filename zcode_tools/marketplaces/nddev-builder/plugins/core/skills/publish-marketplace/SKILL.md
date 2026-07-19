---
name: publish-marketplace
description: Distributes a ZCode marketplace so others can install it — via a GitHub repo, Git URL, local path, or ZIP URL added through the ZCode Marketplace tab — and explains the headless-flatten vs UI-install paths. Use when shipping a marketplace beyond this repo's installer.
---

# publish-marketplace

Turn an authored marketplace into something other people can install. This repo's
own installer uses the headless flatten path (`install.sh install --setup <mp>`);
publishing adds the ZCode-UI distribution path.

## Two ways a ZCode marketplace reaches a user

1. **Headless flatten (this repo).** `install.sh install --setup <mp>` builds
   `~/.zcode` and flattens each plugin's `skills/`, `commands/`, and `agents/` to
   user scope. This path requires **local** `./plugins/<name>` sources that exist
   on disk. See `nddev-builder-orientation`.
2. **ZCode UI Marketplace tab (distribution).** A user opens Plugin Management →
   Marketplace and adds a source: a **GitHub repo** (`owner/repo` or its URL), a
   **Git URL**, a **local path**, or a **ZIP URL** (supported since ZCode 3.3.5).
   ZCode fetches the marketplace, lists its plugins, and the user enables one with
   the toggle; the runtime auto-reloads. There is **no CLI `plugin add`** — this
   path is UI-driven.

## Procedure

1. **Validate first.** `validate-components` and `release-review` must pass.
2. **Make the marketplace self-describing.** The root `marketplace.json` carries
   `name`, `owner`, `description`, and `plugins[]`. For UI distribution a plugin
   `source` may be the local `./plugins/<name>` (when the repo itself is the
   source) or a remote object `{"source":"github","repo":"owner/repo"}`. **npm is
   not a supported source.**
3. **Ship portable manifests.** Keep `.zcode-plugin/plugin.json` at each plugin
   root; optionally add an identical `.claude-plugin/plugin.json` so the bundle
   also runs in Claude Code (ZCode reads `.zcode-plugin` first).
4. **Publish the source.** Push the marketplace tree to a public GitHub repo, or
   host a Git URL or a ZIP URL.
5. **Document install.** In the repo README, tell users to add the source via the
   ZCode Marketplace tab (GitHub / Git / ZIP URL) and enable the plugin.
6. **Version discipline.** One SemVer across the five version sources (see
   `add-plugin` step 8) and `CHANGELOG.md`; bump on every content change so a
   re-install picks up the new bytes.

## Rules

- English only. No secrets, tokens, or machine-local paths in any published file.
- Local `source` for the headless installer; remote `source` / marketplace URL for
  UI distribution — never claim a CLI `plugin add` exists.
- Publishing is git plus versioning; it never bypasses `validate-components` or
  `release-review`.
