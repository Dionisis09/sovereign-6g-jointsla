# Controller optimization delivery

H4 is SUPPORTED under the fixed mean <10-ms budget at all three tested scales.
This is software implementation optimization; scientific decisions/results,
configurations and H1/H2/H3/H5 remain unchanged.

## Verification

- All 160 tests passed: the existing 138 plus 22 new differential tests.
- Nine golden runs pass exact trace hashes and all 200 snapshots per run.
- All 90 optimized full replays pass exact equality against 90 fresh unchanged
  legacy runs and frozen raw CSV audits.
- 1,225,366 request outcomes and 1,277,566 routing assignments verified.
- No numerical tolerance is used; timing fields are the only excluded observables.
- 4,265 pre-existing source/result files remain byte-identical, including all
  three verified result trees.

293 historical summary scalar representations differ in their last bits after
the old default CSV parser. Each exact parser transformation is reproduced and
logged; fresh legacy and optimized metrics and frozen raw request/resource audits
are exactly equal. No old summary is modified. This distinction is documented
in the report, rather than accepting an epsilon-based scientific comparison.

## Performance

One full warm-up per scale/implementation followed by seven seed-1 replays,
alternating order. Each provides 700 live controller invocations; no generation,
constructor, profiling, trace capture, file output or plotting enters the timers.

| Scale | Legacy mean ms | Optimized mean ms | Full speedup | Snapshot speedup | Optimized mean over all 30 seeds ms |
|---|---:|---:|---:|---:|---:|
| SMALL | 2.6329 | 1.2336 | 2.13x | 7.25x | 0.9787 |
| MEDIUM | 7.5251 | 2.6924 | 2.79x | 8.92x | 2.1839 |
| LARGE | 29.8741 | 7.5046 | 3.98x | 9.97x | 5.7203 |

The 10-ms budget is a mean budget. LARGE benchmark p95 is 12.8411 ms; the
original separate p95 <=100-ms screen also passes. Routing-attempt optimized
means are 0.0258, 0.0212, 0.0258 ms; p95s are 0.0444, 0.0356, 0.0418 ms.
These include candidate observation/scoring/counterfactuals, not audit JSON.

At LARGE, policy/action application now accounts for about 67% of full control
time (5.0259 ms), with snapshot 2.4787 ms. No virtual scoring, deepcopy, score,
feasibility, action budget or lifecycle behavior was changed.

Initial-snapshot traced Python peak increases from 1.3672 to 1.5359 MB at LARGE
(+0.1687 MB). Retained constructor state rises by 0.3746 MB; transient snapshot
allocation decreases. These initial-state measurements are separate from wall
timing and do not measure full-run peak Python memory. Sampled mean process RSS
in repeated LARGE runs is 245.06 vs 245.54 MiB; allocator retention and prior
benchmark observation buffers prevent interpreting this as isolated policy RAM.

## New files

- `optimized.py`: ordered replica/store indexes, immutable metadata and
  snapshot-local node cache; unchanged inherited controller/physical engine.
- `reference.py`: before profiling, frozen hashes and original golden traces.
- `validation.py`: golden and full exact replay comparison.
- `benchmark.py`: repeated timing, memory observation and H4-only reassessment.
- `presentation.py`: 16-section report and five figures.
- `audit.py`: exported-trace, timing, figure and hash verification.
- Root `run_controller_optimization.py`: requested stage commands and `--all`.
- `tests/test_controller_optimization.py`: 22 additional correctness tests.
- `tools/verify_controller_optimization.py`: standalone verification command.

Use `OptimizedRoutedSimulator(config, workload, "joint_sla").run()` as the
optimized engine, or `OptimizedMeasured` for the existing measurement scope.
The original runners continue to reproduce their frozen original implementation.

## Outputs and reproduction

All requested profiles, equivalence tables, before/after timings, H4 reassessment
and report are under `results/controller_optimization/`. Five figures have PNG
300-dpi, SVG and PDF exports. Golden JSON and optimized per-run gzip audits,
timing samples, memory table, test log and artifact/source SHA-256 manifests are
included. See [README.md](README.md) for definitions and protocol.

```powershell
.venv\Scripts\python.exe run_controller_optimization.py --profile
.venv\Scripts\python.exe run_controller_optimization.py --validate-equivalence
.venv\Scripts\python.exe run_controller_optimization.py --benchmark
.venv\Scripts\python.exe run_controller_optimization.py --full-validation
.venv\Scripts\python.exe run_controller_optimization.py --all
.venv\Scripts\python.exe tools\verify_controller_optimization.py
```
