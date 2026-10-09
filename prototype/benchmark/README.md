# Isolated real-inference comparison

Run from the repository root on the existing audited local Docker/kind setup.
The primary lab and frozen research results are preserved. The validation lab
uses its own kubeconfig/context and ports 18091/19091/13001. Only this owned lab
is reset by the benchmark runner.

1. Deploy the isolated lab: `python -m prototype.kubernetes.deploy --lab validation --skip-build` (existing primary image lock required).
2. Build instrumented images and install pinned native resource metrics: `python -m prototype.benchmark.setup`.
3. Validate six arms and native HPA actuation: `python -m prototype.benchmark.experiment --pilot`.
4. Run tests, then freeze and execute: `python -m prototype.benchmark.experiment --run`.
5. Reconstruct outcomes and statistics: `python -m prototype.benchmark.analyze`.

Use the project Python environment; the exact host analysis package versions
are listed in requirements-analysis.txt. Container serving dependencies and image
identities are captured through the primary/benchmark image locks, and Kubernetes,
metrics-server and controller commands are frozen in the run manifest.

The main directory is immutable: `prototype/.cache/kubernetes_comparison_v2`.
Resuming skips only already verified trials under the same frozen hashes. Failed
trials stop execution and are retained. Do not remove a failed arm to rerun it.
Changing protocol/source/image requires a newly registered experiment directory.
Pilots are excluded. Run serially; do not perform other lab load/recovery tests
while comparison is active. Seeds reproduce offered inputs, not wall-clock hardware
timing. The protocol declares all six arms, order, reset and analysis rules.

Curated outputs are in `prototype/kubernetes/evidence/comparison_v1`, including
180 run rows, mean/std, paired intervals and Holm p-values, failure categories,
three figures, evidence hashes and COMPARATIVE_REPORT.md. Runtime progress is
recorded in the main progress.json; completion.json must report all 180 before
analysis accepts it. See ../kubernetes/RESEARCH_EVALUATION_PROTOCOL.md and
../kubernetes/COMPARATIVE_NOVELTY_SCOPE.md for assumptions and claim boundaries.

Use `python -m prototype.benchmark.pipeline` for serial registered execution,
automatic reconstruction and protected-file checks. Status is recorded in
`.cache/kubernetes-validation/comparison-pipeline-status.json`. The pipeline
stops on a failed trial and retains its evidence. See the runner overhead audit
at ../kubernetes/evidence/runner_optimization_v2/RUNNER_OPTIMIZATION.md.
