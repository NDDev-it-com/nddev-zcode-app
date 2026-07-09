---
name: run-tests
description: Run the nddev-zcode-app test and validation suite. Tests live in the parent control-plane repo (rldyour-ai-cli-tools/validation/nddev-zcode-app/), NOT inside the module — this keeps the implementation clean. Runs pytest (30 tests covering marketplace structure, installer lifecycle, restore safety, backup rotation, config rendering, version parity) plus a fast validation lane (JSON + installer plan + ShellCheck). Use when you need to verify the system works correctly after changes, before a release, or to catch regressions.
---

# run-tests

Runs the nddev-zcode-app test suite from the parent control-plane repo.

## Where tests live

Tests are centralized in the **parent repo** (rldyour-ai-cli-tools), NOT inside
the nddev-zcode-app submodule. This is by design: the implementation stays
clean, and test internals are hidden from users.

```
rldyour-ai-cli-tools/
  validation/nddev-zcode-app/          ← test suite root
    conftest.py                        ← fixtures (module_root, temp_target, temp_backups)
    _helpers.py                        ← run_installer(), load_json()
    test_marketplace_structure.py      ← marketplace JSON shapes (8 tests)
    test_installer_lifecycle.py        ← install→update→switch→remove (6 tests)
    test_restore_safety.py             ← C1/C2/C3 hardening (5 tests)
    test_backup_rotation.py            ← 10-slot rotation (4 tests)
    test_config_rendering.py           ← ${VAR} + hooks/mcp merge (4 tests)
    test_version_parity.py             ← 5-source version consistency (3 tests)
    benchmarks/bench_lifecycle.py      ← timing benchmarks
    scripts/validate_fast.sh           ← quick lane (<60s)
    scripts/validate_release.sh        ← full lane (<300s)
```

## Procedure

1. Resolve the control-plane root. If you are inside the nddev-zcode-app
   submodule directory, go up 2 levels to reach rldyour-ai-cli-tools.

2. **Fast lane** (quick check, <60s):
   ```bash
   bash validation/nddev-zcode-app/scripts/validate_fast.sh
   ```
   This runs JSON validity, installer `--plan` for all marketplaces, and
   ShellCheck. Use this for rapid feedback during development.

3. **Full pytest suite** (~30s):
   ```bash
   cd <control-plane-root>
   python3 -m pytest -q validation/nddev-zcode-app/ -v --tb=short --rootdir=validation/nddev-zcode-app
   ```
   Runs all 30 tests. Each test shells out to the installer in temp dirs,
   so nothing touches the real `~/.zcode`.

4. **Release lane** (full validation, <300s):
   ```bash
   bash validation/nddev-zcode-app/scripts/validate_release.sh
   ```
   Runs the fast lane + the full pytest suite. Use before tagging a release.

5. Report results: passed/failed counts, any failures with details.

## Rules

- Tests always run in temp directories — never against the real `~/.zcode`.
- The test suite is the gatekeeper: no release without all tests passing.
- If a test fails, fix the root cause — do not skip or weaken the test.
- English only for all output.
