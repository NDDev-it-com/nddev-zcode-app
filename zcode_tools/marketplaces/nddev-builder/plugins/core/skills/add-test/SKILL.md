---
name: add-test
description: Scaffold a new test file for the nddev-zcode-app test suite. Tests live in the parent control-plane repo (rldyour-ai-cli-tools/validation/nddev-zcode-app/), NOT inside the module. Creates a test file using the existing fixtures (module_root, temp_target, temp_backups, marketplaces) and the run_installer helper. Use when adding a new test case for a feature, bugfix, or regression.
---

# add-test

Scaffolds a new test file in the centralized test suite.

## Where tests live

```
rldyour-ai-cli-tools/validation/nddev-zcode-app/test_<name>.py
```

## Procedure

1. Ask the user for:
   - The test name (snake_case, e.g. `test_custom_target`, `test_switch_all_marketplaces`).
   - What the test should verify (one sentence).

2. Create the test file at
   `validation/nddev-zcode-app/test_<name>.py`.

3. Use the established patterns:
   ```python
   """<One-sentence description of what this test verifies>."""
   from _helpers import run_installer, load_json

   def test_<name>(installer, temp_target, temp_backups):
       """<What this test checks>."""
       run_installer(installer, "install", "--marketplace", "nddev-builder",
                     "--platform", "macos", "--apply",
                     target=temp_target, backups=temp_backups)
       assert (temp_target / "BUILD-VERSION").is_file()
   ```

4. Available fixtures (from `conftest.py`):
   - `module_root` — Path to `modules/nddev-zcode-app/` (session-scoped).
   - `installer` — Path to `cli-tools/scripts/install.sh` (session-scoped).
   - `temp_target` — Fresh temp dir for `--target` (function-scoped, auto-cleanup).
   - `temp_backups` — Fresh temp dir for backups (function-scoped, auto-cleanup).
   - `marketplaces` — List of all marketplace names (session-scoped).

5. Available helpers (from `_helpers.py`):
   - `run_installer(installer, *args, target=None, backups=None, expect_success=True)` —
     runs install.sh with the given args, returns CompletedProcess.
   - `load_json(path)` — loads and parses a JSON file.

6. Run the test to verify it passes:
   ```bash
   python3 -m pytest validation/nddev-zcode-app/test_<name>.py -v --rootdir=validation/nddev-zcode-app
   ```

## Rules

- Tests always use temp dirs — never the real `~/.zcode`.
- Each test should verify ONE behavior (single assertion focus).
- Use `expect_success=False` when testing error cases (guard rejections, etc.).
- English only.

## After creating

- Run the full suite to verify no regressions:
  `python3 -m pytest -q validation/nddev-zcode-app/ --rootdir=validation/nddev-zcode-app`.
- Bump the build version if this is a release behavior change (follow `release-build`).
