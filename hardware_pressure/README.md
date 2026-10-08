# Hardware-grounded pressure sweep and factorial diagnostics

Uses existing frozen model profiles; never runs PyTorch profiling. Existing requirements and `.venv` are sufficient. All algorithms and historical outputs are read-only. New code lives in `hardware_pressure/`; results in the two requested output directories.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_hardware_pressure_sweep.py --pilot
.venv\Scripts\python.exe run_hardware_pressure_sweep.py --loads 0.5,0.75,1.0,1.25,1.5,1.75,2.0 --seeds 1:30 --force
.venv\Scripts\python.exe run_hardware_causal_decomposition.py --regimes D0,D1,D2,D3,D4,D5,D6,D7 --seeds 1:10 --force
```

`--reuse-results` reuses completed run exports for analysis; `--force` reruns only the new study. `--pilot` on the sweep first verifies exact DIRECT reproduction and then runs extreme loads 0.5/2.0 on seeds1/2/3. Pilot is safely reused on subsequent calls. Config/source hashes freeze after the successful pilot and are checked before subsequent execution. Causal `--pilot` runs seeds1/2/3 separately. Partial load/seed/regime runs produce auditable raw data but full publication analysis requires the predefined complete study.

The protected hash baseline was captured before implementation, after independently verifying all old artifact hashes and profiles. In a fresh checkout, use the delivered guard and unchanged old output trees. Do not regenerate the protected hash baseline to conceal altered old files.

Traffic scaling: conditional compound-Poisson intensity λ_m=mλ, shared original noise/burst schedule, whole-batch thinning below1× and independent superposition above1×. Original service rates and reservation demands remain fixed. Expected tier/model proportions remain fixed; realized request shares fluctuate.1× is identity. Per-policy tapes have identical hashes. New keyed RNG streams never alter original streams. Controllers see only past/current state.

D0–D7 form the full factorial of execution times, memory and cold readiness. Execution/cold also supply measured aggregate values to the original global controller interface, matching the frozen DIRECT definition. All other parameters are unchanged. Factorial contrasts and Shapley attribution are exploratory with ten paired seeds, not real-world causal proof. No optional 30-seed decomposition extension is selected solely from favorable outcomes.

Definitions, selection rules, hypotheses and four Holm families are in `PLAN.md`. Every run exports request outcomes, nodes, queues, reservations, actions, lifecycle intervals, routing candidates/scores, controller timing and read-only per-service/node pressure snapshots. Outcomes are validated in memory and independently reconstructed from CSV. Primary SLA/p95 Holm family14, secondary mean/p99 family14, tier SLA family21, model SLA family21. Seed-level bootstrap10000, paired Wilcoxon and RBC retain the previous statistical implementation.

Burst recovery is retrospective and may be censored by the next burst/horizon. Conditional delay means must be read with censoring fractions. Headroom captures both free physical tokens and free reserved capacity. Representative examples are best/lower-median/worst by paired DIRECT SLA gap. Frontier lines connect observed load points, not optimization solutions.
