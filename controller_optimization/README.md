# Controller implementation optimization

This is a separate implementation adapter around the verified JointSLA engine.
All original source files and the three verified result trees are read-only.
Only ordered discovery, immutable metadata and synchronous snapshot observation
are optimized. The controller, route score, event generators, physical worker,
action feasibility, thresholds and configurations are imported unchanged.

Before writing the optimized implementation, cProfile ran seed 1 at all three
scales and nine full legacy golden traces were saved (SMALL 1/7/22, MEDIUM
1/4/16, LARGE 1/12/22). Exact equality includes candidate score inputs, action
and route order, every request float/flag/destination, all 200 snapshots, and
resource/lifecycle state. Timing fields alone are excluded.

## Benchmark protocol

One full warm-up run per implementation/scale, followed by seven fresh seed-1
replays per implementation/scale. Each replay performs the unchanged 100 control
invocations and actual action applications. Execution order alternates to reduce
order effects. Mean, median and linear p95 are reported for 700 live invocations
per implementation/scale. Snapshot plus policy/application is the full control
time; per-request routing is separately scoped. Existing perf_counter_ns timers
are retained; workload generation, constructors, cProfile, capture, exports and
plots are outside the timers. No parallel benchmark execution is used.

After golden equality, all 30 seeds at all three scales replay both the unchanged
legacy and optimized engines. Exact fresh trace and research-metric equality is
required, as is exact comparison with frozen CSV audit frames read using pandas
round-trip float parsing. No tolerance is allowed. Historical summary values
that traversed the legacy default CSV parser can differ by a few binary bits;
any such difference must be reproduced exactly by that parser, recorded, and
also pass exact raw-audit and fresh-legacy checks. Old summaries are not rewritten.

H4 alone is reassessed: optimized mean full controller <10 ms at each scale,
mean per-seed full-controller p95 <=100 ms and mean per-seed routing p95 <=1 ms.
The repeated benchmark must also meet the 10-ms mean budget. H1/H2/H3/H5 and
the scientific statistical methodology are not changed or rerun.

RSS is sampled in the replay benchmark; optional tracemalloc separately measures
the initial control snapshot and constructor-retained Python state. Tracemalloc
is never active during the wall-time benchmark. Its initial-state measurement
does not claim peak memory over the complete traffic horizon.

## Commands

```powershell
.venv\Scripts\python.exe run_controller_optimization.py --profile
.venv\Scripts\python.exe run_controller_optimization.py --validate-equivalence
.venv\Scripts\python.exe run_controller_optimization.py --benchmark
.venv\Scripts\python.exe run_controller_optimization.py --full-validation
.venv\Scripts\python.exe run_controller_optimization.py --all
.venv\Scripts\python.exe tools\verify_controller_optimization.py
.venv\Scripts\python.exe -m pytest -q
```

All new output goes to `results/controller_optimization/`. Stage commands run
their missing prerequisites and preserve existing golden references. `--profile`
produces before/after attribution, not performance budget measurements. `--all`
repeats equivalence, benchmark and full validation; it never writes into a
verified baseline tree. Reports/figures are generated when benchmark and full
validation outputs are both available. Optimized-source fingerprints accompany
validation and benchmark outputs; mixing fingerprints is rejected by verification.

The result is implementation performance engineering, not a new research
algorithm or additional algorithmic novelty.
