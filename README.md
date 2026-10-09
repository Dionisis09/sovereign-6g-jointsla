# CATALYST: runtime cross-layer contracts, Phase 0

The separate [real-inference infrastructure prototype](prototype/README.md)
adds Docker, real PyTorch serving, Prometheus/Grafana and a scoped Kubernetes
adapter. Frozen simulator/paper results remain unchanged.

Final local prototype deliverables: [unified JointSLA report](JOINTSLA_FINAL_REPORT.md)
and [live infrastructure dashboard](http://127.0.0.1:3001/d/jointsla-runtime).
The dated audit verified 306 tests / 1,420 outcomes; the dashboard extension
passes 310 tests. The report keeps the 38.83% and 47.27% burst runs separate.

The statistical paper evaluation is documented in
[paper_evaluation/README.md](paper_evaluation/README.md). Run
`python run_paper_experiments.py --seeds 1:30 --reuse-results` to reproduce the
analysis of the saved 120 policy runs. Results, 95% confidence intervals,
paired tests, figures and generated report are in `results/paper_30seeds`.

The dynamic extension is documented in [dynamic_placement/README.md](dynamic_placement/README.md).
Run `python -m dynamic_placement.runner` for 30 paired seeds, 100 slots,
explicit queues, scaling and migrations. Outputs are in `results/dynamic`.

Run `python -m dynamic_placement.scenarios` for the follow-up predictive,
extra-capacity and admission-control comparisons; see
[SCENARIOS.md](dynamic_placement/SCENARIOS.md).

The newer five-node service-placement experiment is documented in
[placement_experiment/README.md](placement_experiment/README.md). Run it with
`python -m placement_experiment.runner`; its outputs are separate in `results/placement`.

New research branch: `codex/catalyst-phase0`. One configurable synthetic service
engine, B0 PLAIN_LOCAL, B1 STRONG_LOCAL_SAFE, CATALYST RUNTIME_CONTRACT, and only
the two requested ablations. See [the protocol](docs/protocol.md) and
[the code reuse audit](docs/reuse-audit.md).

The previous **6g 1** artifacts were found at
`C:/Users/dioni/Documents/Codex/2026-10-06/kan/outputs`. Generic helpers are
extracted into this repository with [exact provenance](docs/reuse-provenance.json).
The previous artifacts remain untouched; their controllers, claims and tuned
parameters are not imported. That old directory had no Git repository.

## Run

The supplied `.venv` inherits the desktop's bundled Python 3.12 packages. For a
fresh environment, use Python >=3.12 and install the pinned project dependencies:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[test]"
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage all --output results/reproduction
```

To follow the prescribed sequence separately:

```powershell
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage negative
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage stress
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage ablations
& .\.venv\Scripts\python.exe -m catalyst.experiment --stage analyze
```

Final artifacts: [report](results/phase0-v1/report.md),
[interpreted findings](docs/phase0-findings.md),
[decision and paired intervals](results/phase0-v1/analysis.json),
[seed-level metrics](results/phase0-v1/runs.csv),
[secondary metrics](results/phase0-v1/summary.csv), and
[plot](results/phase0-v1/breach_seconds.png).

Independent metric reconstruction: `python -m tools.verify_results`.

The initial failed S0 at 40 rps is preserved in `results/phase0`; the corrected
10-rps S0 with an overly strict draft B0 equality check is in `results/phase0-final`.
These are validation pilots, not extra stress experiments. The protocol and report
disclose both corrections. No S1–S3 parameters or hypothesis thresholds were tuned.

## Inspect and replay

Each case retains a frozen workload tape and compressed policy evidence, including
all request outcomes, public snapshots, clause predictions, lifecycle actions,
breach samples and bounded counterfactual false-block audits. Seeds are the units
of statistical replication. Source/config/protocol hashes are frozen before the
first stage. Changed files require a fresh output directory; old runs are not mixed.

For a single run:

```python
from catalyst.scenario import load_config, matrix, workload
from catalyst.engine import Engine
c = load_config()
s = next(s for s in matrix(c) if s.family == "S3" and s.level == 2)
tape = workload(c, s, seed=0)
run = Engine(c, s, tape, "CATALYST").run()
print(run.summary())
```

No request rejection, autonomous agents, deployment infrastructure, RL, digital
twin, extra baselines, or broad policy language is implemented. Quality scores
and service profiles are stipulated. This experiment can reject the mechanism's
Phase 0 hypothesis; it cannot establish real-world performance or novelty.


## Real Kubernetes comparative validation

The unchanged JointSLA runtime is being evaluated against static, CPU-reactive
and native HPA policies plus two registered scaling/routing controls. The isolated
lab preserves historical experiments and the primary dashboard. See the
[benchmark instructions](prototype/benchmark/README.md),
[frozen evaluation protocol](prototype/kubernetes/RESEARCH_EVALUATION_PROTOCOL.md),
and [contribution scope](prototype/kubernetes/COMPARATIVE_NOVELTY_SCOPE.md).
The main experiment has 30 paired seeds, 180 trials and 230,400 offered requests.
Progress is recorded in `prototype/.cache/kubernetes_comparison_v2/progress.json`;
only completion plus independently reconstructed analysis supports final findings.
