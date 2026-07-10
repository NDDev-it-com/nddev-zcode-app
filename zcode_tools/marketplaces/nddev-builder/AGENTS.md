# Global Agent Instructions

<!-- nddev-builder:begin -->
## ZCode environment — nddev-builder

This ZCode home is produced from the `nddev-builder` marketplace in
`NDDev-it-com/nddev-zcode-app`. It is a focused environment for creating and
maintaining ZCode-native marketplaces, plugins, skills, commands, agents,
hooks, MCP servers, providers, references, and companion CLI tools.

The `core@nddev-builder` plugin is enabled by default. Use its components as
the primary workflow for changes to ZCode extension sources.

### Working contract

- Inspect the active repository and its instructions before proposing a
  component location or format.
- Prefer ZCode-native convention discovery: `skills/<name>/SKILL.md`,
  `commands/<name>.md`, `agents/<name>.md`, and metadata-only
  `.zcode-plugin/plugin.json` manifests.
- Keep marketplace registration, plugin manifests, enabled-plugin keys, and
  component paths synchronized in the same change.
- Reuse an existing component when its responsibility already matches. Avoid
  aliases, duplicate policy sources, and speculative abstractions.
- Make the smallest complete change, validate its syntax and discovery path,
  and report the exact files and checks used.

### Installed layout

- `AGENTS.md` provides these user-scope defaults.
- `skills/`, `commands/`, and `agents/` hold optional user-scope components.
- `marketplaces/nddev-builder/` contains the installed marketplace and its
  self-contained plugin bundles.
- `cli/config.json` contains the required secret-free model/provider bootstrap,
  plugin state, hooks, and MCP server definitions. ZCode supplies the restored
  OAuth credential at runtime.
- `v2/config.json` contains optional explicit API-key providers under
  `custom:*` identities; they never reuse ZCode-owned `builtin:*` identities.
- `v2/setting.json` contains desktop preferences, including the verified Z.ai
  account OAuth mode.
- `.env`, provider configs, MCP configuration, `v2/credentials.json`, and
  backups can contain credentials or tokens.

### Safety and quality

- Repository source must never contain real credentials. Use declared
  `${VAR_NAME}` placeholders and the local, gitignored `build/.env` contract.
- The rendered ZCode home does contain sensitive values. Never print, commit,
  upload, or include its `.env`, configs, credentials, or backups in examples
  and diagnostics.
- Treat `credentials.json` as a secret. It is restored runtime state, not a
  source template.
- Do not hand-edit rendered files as the durable fix. Edit the marketplace
  source and re-run the installer.
- Keep code, identifiers, documentation, and commit messages in English. Use
  Conventional Commits when committing repository changes.
<!-- nddev-builder:end -->
