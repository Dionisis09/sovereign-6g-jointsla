# JointSLA repository: clone, read, run

This private repository contains the implementation, configurations, unit tests,
research dashboard, local Kubernetes prototype, curated documents, aggregate
results, figures and the archived inputs needed by dashboard simulation replays.

## Read the project

Start with [JointSLA/README.md](JointSLA/README.md). It points to one complete
100-slide presentation, the mathematical scaler/router Word, the main technical
report and paper. Supporting simulation and infrastructure reports describe
distinct experiments. Their original frozen artifacts remain under `docs/` and
`results/`, with manifests and hashes preserved.

## Clone and launch the dashboard

Use Python 3.12 or newer. On Windows, from a terminal with GitHub access:

```powershell
git clone https://github.com/Dionisis09/sovereign-6g-jointsla.git
cd sovereign-6g-jointsla
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-research.txt
.venv\Scripts\python.exe run_dashboard.py
```

The default dashboard address is `http://127.0.0.1:8501/`. Its frozen research
views work without Docker or PyTorch. See [dashboard/README.md](dashboard/README.md)
for the separate simulation replay and live MaaS pages.

## Real model serving and Kubernetes

The MaaS page calls the existing local Kubernetes gateway at port 8091; it needs
Docker Desktop running with Linux containers, kubectl, and the local prototype:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File prototype/kubernetes/deploy.ps1
```

The initial build downloads model weights and official images. The deployment
uses its own kubeconfig; no running cluster or credentials are shipped in Git.
Details: [prototype/README.md](prototype/README.md) and
[Kubernetes setup](prototype/kubernetes/README.md). Native PyTorch serving, if
desired, uses `prototype/requirements-inference.txt` separately.

## Checks and scientific reproduction

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Read the [final publication package instructions](docs/jointsla_kubernetes_v2_final/README.md)
for reproducing the analysis of saved Kubernetes aggregates. Unit tests use fake
backends and isolated fixtures; they do not start or mutate a real cluster.

## Included and excluded data

Included: source, configs, summaries, figures, per-run aggregates, publication
tables, compressed visualization trajectories, held-out replay input tapes,
Word/PowerPoint documents and provenance/hash records. No Git LFS is required.

Excluded: `.venv`, caches, secrets, Docker/Kubernetes local state, model weights,
bulk request/routing/event traces and large ZIP experiment archives. These remain
local. This is the requested compact research repository, not the complete raw
data archive. The raw preservation receipts document the original local archive;
verifying every raw-file hash requires that archive. Repo-only aggregate analysis
and the dashboard do not require it. The prebuilt full-package ZIP download is
optional and is not included in Git; individual report/figure downloads remain
available.

The observed Kubernetes result is 49.89% versus 61.43% reactive SLA failures, with
58.84% more target replica-time. Simulation results, historical infrastructure
audits and this controlled comparison remain separate. Live MaaS requests do not
modify frozen research results.

## Delivery validation (9 October 2026)

The clean staged-file export passed **345 tests**. The 33 curated artifacts match
their original hashes, and the 54 included publication/source files checked
against frozen manifests match byte for byte in Git. The excluded complete raw
evidence ZIP remains local. No credentials, environments or runtime caches were
included; no tracked file exceeds 95 MB. These checks do not rerun or modify the
frozen scientific experiments.
