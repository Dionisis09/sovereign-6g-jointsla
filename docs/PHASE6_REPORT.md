# Phase 6 Kubernetes/HAMi safe preview (2026-11-17)

## Repository facts discovered

The local action backend still writes only simulator records. Its deterministic `decide()` already checks action allowlists, simulated capacity, residency and prediction/recovery conditions. This host has no `kubectl`, Helm or Docker CLI, configured cluster URL, GPU or HAMi exporter. Phase 5's full Python suite is additionally blocked here by Windows Application Control on LangGraph's `ormsgpack` extension. The pre-existing JointSLA/research source and frozen results were not changed.

## Implemented

`sovereign_maas/kubernetes.py` adds:

- Strict `DeploymentBinding` (operator-owned tenant, service, namespace, deployment, node, region and HAMi requirement) and `ScalePlan` contracts. `plan_scale()` rechecks service/run identity, snapshot freshness, selected deterministic scale action, rejection state, allowed action, simulated node/capacity, residency and simulated verification. It produces original, canary, target and rollback replica counts. The adapter rechecks both plan and source snapshot freshness immediately before any cluster request.
- `simulate_canary()` with explicit success, canary failure, target failure and rollback states. Observations and traces are `SIMULATED`; no Kubernetes I/O is performed.
- `KubernetesDryRunAdapter`: HTTPS origin, bearer credential, CA bundle, five-second timeout, no redirects. It performs SelfSubjectAccessReview for Deployment get and Scale get/update, then reads a fixed Deployment and Scale, checks labels, namespace, UID, resourceVersion, current replicas, region selector and CPU/memory requests/limits. If requested, it validates explicit HAMi NVIDIA `nvidia.com/gpu`, `nvidia.com/gpumem` and `nvidia.com/gpucores` limits/requests. It sends `PUT` to the Scale subresource with `dryRun=All` and strict field validation for canary and target. The receipt says `persisted=false`; no commit endpoint exists.
- `HamiMetricsReader`: read-only scrape of a configured `/metrics` URL, exact allowed-node filter, bounded response and strict parsing of host GPU utilization and used-memory metrics. It returns scrape-time provenance, not per-service or per-Pod SLO evidence.
- `sovereign_maas/phase6_demo.py` for a local CPU success/rollback demonstration, `tests/test_sovereign_phase6.py` with HTTPX MockTransport, and `docs/phase6-rbac.example.yaml` for a named Deployment in one namespace. The example is not applied.

The request paths and behavior follow the official [Deployment Scale API](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/), [API server dry-run semantics](https://kubernetes.io/docs/reference/using-api/api-concepts/), and [SelfSubjectAccessReview authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/). HAMi's [NVIDIA resource example](https://github.com/Project-HAMi/HAMi/blob/master/README.md) and [host metric definitions](https://project-hami.io/docs/userguide/monitoring/real-time-device-usage) are the resource/metric contracts used. Kubernetes dry-run RBAC equals live RBAC; the example Role therefore grants `update` on the named Scale resource, even though this adapter can only issue dry-run requests. Admission success does not prove scheduling, readiness or SLO success.

## How to run

From the repository root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.phase6_demo
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase6.py
```

`KubernetesDryRunAdapter.preview(plan)` is the optional cluster-facing library boundary. A cluster operator must provide an HTTPS API origin, bearer token, CA path and a trusted `DeploymentBinding`; the target Deployment must carry `sovereign-maas/tenant-id` and `sovereign-maas/service-id` labels, a `sovereign-maas/region` Pod node selector, and explicit container resource requests/limits. Review the example RBAC before any separate application. No cluster command was executed here. For a HAMi exporter on HTTP inside an isolated cluster, `allow_plain_http=True` must be explicit; the default requires HTTPS.

## Tests actually executed

| Check | Outcome |
| --- | --- |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q tests/test_sovereign_phase6.py` | 11 passed; no external requests |
| `python -m sovereign_maas.phase6_demo` | Passed; simulated success and rollback, `cluster_called=false` |
| Ruff lint/format, mypy (21 package files), pip check, YAML parse and `git diff --check` | Passed after corrections |
| Repository-wide pytest | Failed at collection in five modules; same Windows `ormsgpack` Application Control block |
| Live Kubernetes dry-run, HAMi scrape, GPU/hardware rollout | Not executed: no cluster/credentials/GPU/exporter available |

Mock receipts use `MOCK_KUBERNETES_DRY_RUN` and mock GPU samples use `MOCK_HAMI_EXPORTER`. They are tests of request shape and fail-closed parsing, not live infrastructure evidence.

## Evidence and limitations

The adapter cannot make a live change: it has no request path without `dryRun=All`. The canary/rollback state machine is a simulation, not a proof of Kubernetes readiness or compensation. Deployment resource and HAMi shape checks do not prove that HAMi is installed, a GPU is schedulable or a Pod will meet latency. The HAMi reader returns host-level numbers only when an exporter is actually configured; no values were measured in this run. The repo-wide Python gate and Phase 5 end-to-end HTTP smoke remain outstanding because of the host DLL policy.

## Architecture decisions

The binding is trusted configuration, not a field accepted from intent text or an agent. We use the narrow Scale subresource, a named Deployment, API-server RBAC and admission dry-run, resourceVersion preconditions and no redirects. The lack of a live commit path avoids equating a mocked preview with rollout safety. A future live actuator needs separate approval, a fresh scale check, measured readiness and SLO observations, an idempotent state record and tested rollback behavior before it can write.

## What I should learn

1. Read a `ScalePlan` alongside its service/run and identify every local check that prevents cross-tenant or stale actions.
2. In the MockTransport test, change SelfSubjectAccessReview to deny `update`; verify no `PUT /scale` occurs. Then change the Deployment owner label and observe the different denial.
3. Compare a simulated canary trace with Kubernetes `dryRun=All`: explain which one tests state transitions, which one tests admission, and why neither proves Pod readiness.

## Next phase

First rerun the full repository suite and Phase 5 end-to-end smoke in a Python environment permitted to load `ormsgpack`. Cluster validation requires a provisioned test namespace, reviewed RBAC, compatible Deployment/HAMi installation, CA/token and exporter. With those gates recorded, Phase 7 can explore offline masked RL proposals and supervisor experiments without granting an agent cluster mutation authority.
