---
description: Isolated install-and-verify loop for a marketplace using temporary HOME/ZCODE_HOME, proving components flatten and load without touching live ~/.zcode.
---

Behaviorally test a marketplace in throwaway state.

Follow the `devtest-plugin` skill exactly: static-gate with
`validate-components`, isolate `HOME` and `ZCODE_HOME` in a temporary directory,
run `install.sh --plan` then `--apply`, assert each basename flattened once into
`~/.zcode/{skills,commands,agents}` (references and tools are not flattened),
restart to reload, then tear down. Never touch live `~/.zcode`. ZCode has no
`plugin add`, cache, or dev-mode reload.
