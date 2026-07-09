---
description: Run performance benchmarks for the installer (install, remove, plan timing).
---

Run installer performance benchmarks.

Follow the `run-benchmarks` skill exactly:

1. Resolve the control-plane root.
2. Run `python3 validation/nddev-zcode-app/benchmarks/bench_lifecycle.py`.
3. Report the timing results as a table.
