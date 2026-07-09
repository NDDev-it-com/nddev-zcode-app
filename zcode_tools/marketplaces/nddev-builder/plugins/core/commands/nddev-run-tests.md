---
description: Run the nddev-zcode-app test suite (30 pytest tests + fast validation lane) from the parent repo.
---

Run the nddev-zcode-app test suite.

Follow the `run-tests` skill exactly:

1. Resolve the control-plane root (parent of the nddev-zcode-app submodule).
2. Run the fast lane: `bash validation/nddev-zcode-app/scripts/validate_fast.sh`.
3. Run the full pytest suite: `python3 -m pytest -q validation/nddev-zcode-app/ -v --rootdir=validation/nddev-zcode-app`.
4. Report passed/failed counts and any failures.
