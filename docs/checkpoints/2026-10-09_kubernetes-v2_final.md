# JointSLA checkpoint — 9 October 2026

Local Git reference: `codex/checkpoint-kubernetes-v2-final-2026-10-09`.
This checkpoint records the completed research package and updated research dashboard. It does not run experiments or change frozen observations or controller behavior.

## Completed state

- Kubernetes comparison v2 is complete: 30 paired blocks, seeds 1001–1030, six policies, 180 trials and 230,400 offered request outcomes.
- Final technical report, conference paper draft, 14-slide presentation, seven PNG/vector-PDF figure pairs, seven CSV tables, source scripts and consistency checks are in `docs/jointsla_kubernetes_v2_final/`.
- The Streamlit dashboard includes **Kubernetes Comparison v2**, policy results, per-tier failures, paired statistics, exploratory ablations, resource trade-offs and publication downloads.
- Last full test run: **335 passed in 27.77 s**. The finalized publication records an earlier, dated 330-test validation; that frozen record has not been rewritten.
- Preservation verification passed for 1,480 original v2 files and 24,364 historical result files. The archived v2 members also passed SHA-256 and ZIP integrity checks.
- Existing simulator studies, Kubernetes operational validation and repeated Kubernetes comparison remain distinct evidence tracks.

## Exact main findings

- JointSLA mean SLA failures: **49.890625%**; reactive: **61.4296875%**.
- Paired JointSLA-minus-reactive effect: **−11.5390625 percentage points**; 95% paired bootstrap CI **[−13.984375, −9.057291666666668]**; Holm-corrected p **3.725290298461914e−08**.
- Target replica-seconds: JointSLA **103.446944**, reactive **65.124512** (rounded means); ratio of policy means increases **58.8448662806198%**.
- JointSLA significantly reduces SLA failures in this registered CPU burst regime and uses more target replica-seconds. Greater resource efficiency is not established; the below-15% goal is unmet.
- Router ablation is inconclusive: CI crosses zero. Completed-request p95 excludes rejected requests. No confirmatory p95 superiority claim is supported.
- Historical 38.83% and 47.27% bursts and the 1,420-request operational audit are separate experiments, excluded from the v2 comparison.

## CPU configuration and limits

The completed experiment uses one physical Windows/Docker host and one virtual kind Kubernetes node, with real pretrained MobileNetV3-Large CPU inference on synthetic inputs. Each inference replica requests 500m CPU and has a 1-CPU quota, 1/2 GiB requested/limited RAM, one serial inference worker and eight waiting slots. The PyTorch default is two compute threads. Policies use two to four replicas; this is not the entire experiment confined to one physical CPU core. GPU execution and multi-host edge deployment have not been evaluated.

Increasing CPU per replica, changing thread counts or using all host CPU resources would constitute a new experimental configuration. No such experiment is part of this checkpoint. Preserve the completed comparison before any future capacity study.

## Resume commands

From the project root, in PowerShell:

```powershell
.venv/Scripts/python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/validate_publication.py
.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/verify_preservation.py --originals
```

Dashboard: <http://127.0.0.1:8501/?view=kubernetes-v2>.
Live Grafana requires the separately running local Kubernetes stack; archived comparison panels are not live counters.

## Preservation and restore scope

The local checkpoint folder beside the project contains a Git bundle, a copy of `JointSLA_Final_Research_Package_v2.zip`, validation receipts and a SHA-256 manifest. The Git commit/tag captures all currently tracked and non-ignored project additions. No checkpoint is pushed to GitHub automatically.

The publication ZIP includes the complete archived v2 evidence. Its SHA-256 is `ff32b3b3769f4eca43cecdadda4810c71e372b4c8372c11ac2af02bbdc46764e`.
The enclosed raw v2 evidence ZIP has SHA-256 `81462a18af99638c6f7ca68b8688632a71c72ef032eba1017fd5ccf9f5cbc580`.

Large historical traces, model weights, `.venv`, credentials, kubeconfigs, running containers and local runtime caches remain outside Git. Historical traces remain in the original local `results/` directory and are covered by the preserved hash seal; this checkpoint is not an additional backup copy of all those historical files. Reconstructing a live environment requires the documented deployment and dependency setup. Restoring files does not restore running processes.

To inspect the checkpoint safely, clone the bundle into a **new** directory and check out its tag. Do not reset or overwrite the current working tree to inspect it. The external checkpoint receipt supplies the absolute bundle path and commit ID. Preserve publication archives byte-for-byte; Git newline conversion can affect source/evidence file hashes across machines.

## Remaining publication work

Supply authors, affiliations and conference template before submission. Keep novelty claims conservative. Any expanded CPU-budget, sustained-load, GPU, matched-budget or multi-host study must have its own protocol and outputs; do not overwrite frozen results.
