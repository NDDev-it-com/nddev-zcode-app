# nddev-zcode-app documentation

- **[install.md](install.md)** — how the installer works: plan vs apply, backup,
  build, selective restore, and the command-line usage.
- **[architecture.md](architecture.md)** — the three-layer design
  (`zcode_tools/` source → `cli-tools/` installer → `build/` artifacts) and how
  it maps to the ZCode native format.
- **[secrets.md](secrets.md)** — the `build/.env.example` → `build/.env` contract
  and how `${VAR}` placeholders are rendered at install time.
