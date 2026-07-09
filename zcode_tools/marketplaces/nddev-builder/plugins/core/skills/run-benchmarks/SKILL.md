---
name: run-benchmarks
description: Run performance benchmarks for the nddev-zcode-app installer. Measures timing for install --plan, install --apply, remove --apply across all marketplaces. Reports min/mean/max over multiple runs. Tests live in the parent control-plane repo (rldyour-ai-cli-tools/validation/nddev-zcode-app/benchmarks/). Use when checking installer performance, comparing before/after optimizations, or establishing baseline timings.
---

# run-benchmarks

Runs performance benchmarks for the installer lifecycle.

## Where benchmarks live

```
rldyour-ai-cli-tools/validation/nddev-zcode-app/benchmarks/bench_lifecycle.py
```

## What it measures

- **install --plan**: dry-run latency per marketplace (no writes).
- **install --apply**: full lifecycle (backup → build → restore → verify).
- **remove --apply**: backup + delete timing.

Each operation runs N times (default 3) and reports min/mean/max in seconds.

## Procedure

1. Resolve the control-plane root (parent of the nddev-zcode-app submodule).

2. Run the benchmark script:
   ```bash
   python3 validation/nddev-zcode-app/benchmarks/bench_lifecycle.py
   ```
   For machine-readable output:
   ```bash
   python3 validation/nddev-zcode-app/benchmarks/bench_lifecycle.py --json
   ```
   For more runs (more stable averages):
   ```bash
   python3 validation/nddev-zcode-app/benchmarks/bench_lifecycle.py --runs 5
   ```

3. Report the results as a table:
   ```
   Benchmark                          min      mean     max   (seconds)
   plan/nddev-builder/macos          0.123    0.130    0.140
   apply/install/builder/macos       1.234    1.300    1.400
   ```

4. If comparing before/after a change, run benchmarks on both versions and
   report the delta. A >10% regression should be investigated.

## Rules

- Benchmarks run in temp dirs — never against the real `~/.zcode`.
- Results are machine-specific; compare only relative deltas, not absolute values.
- The first run is often slower (cold cache); prefer `--runs 3` minimum.
- English only.
