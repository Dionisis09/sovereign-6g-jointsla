# JointSLA infrastructure validation

Audit date: 8 October 2026. Scope: the dedicated local Kubernetes real-inference
prototype, with the frozen research simulator, policy functions and results preserved.

## Completion boundary

**Complete for the bounded local Kubernetes prototype: yes. General production-ready: no.**
The final one-command build/deployment/validation run passed, as did all 306 tests
(285 existing plus 21 new). Probes, resource bounds, admission/draining, warm-up,
recovery, monitoring persistence and clean/idempotent deployment are verified.
The operational boundaries below still apply; this is not an internet-facing,
high-availability deployment or proof of the paper's <15% SLA target.

## Architecture

```text
Client -> loopback NodePort -> one gateway/controller
                                |  unchanged choose / required_warm functions
                                |  bounded HTTP forwarding, no automatic request replay
                                v
                       Ready, non-terminating inference pods
                       existing pretrained MobileNetV3, CPU, serial worker
                                ^
                                | namespace-scoped deployment scale API (1β€“4)
                      Kubernetes scheduler / Deployment replacement

Gateway + inference metrics -> Prometheus (PVC, bounded retention) -> Grafana (PVC)
```

One physical Windows/Docker host and one virtual node in the main kind cluster.
The simulator remains the source of frozen scientific experiments. The runtime
adapter continues using the existing routing and warm-headroom functions; it
does not port or redesign the complete simulator-specific state machine.
Kubernetes places CPU/memory workloads. There is no new AI/ML controller,
prediction model, optimization method, multi-edge placement or GPU scheduler.

## Reproduction commands

Prerequisites: Windows, Docker Desktop using Linux amd64 containers, Docker
Compose v2, kubectl and Python 3.12 (the existing project environment also works).
Run from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File prototype/kubernetes/deploy.ps1 -Validate
```

This creates an isolated host environment, downloads checksum-verified kind
v0.33.0 if needed, creates/reuses `jointsla-prototype`, builds/loads the application
images, provisions monitoring, waits for startup, checks real inference, and runs
traffic, recovery and persistence validation. `-SkipBuild` reuses the last built
images. Omit `-Validate` for deployment and smoke checks only. The full run causes
deliberate local interruptions: deletion of an inference pod, gateway kill/hang,
and monitoring restarts. It is not a background or non-disruptive health check.

All kubectl commands explicitly select `.cache/kubernetes/config` and
`kind-jointsla-prototype`; the global kubeconfig/context is never changed.
Reapplying preserves the controller-owned inference replica count. Recreate
gateway updates prevent overlapping writers and have a brief availability gap.
Do not add an HPA or a second controller to the same inference Deployment.

```powershell
.venv/Scripts/python.exe -m pytest -q
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.validate_runtime
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.validate_infrastructure
```

For a separate fresh bootstrap, with primary data and services untouched:

```powershell
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.deploy --lab validation --skip-build
.cache/bin/kind.exe delete cluster --name jointsla-validation
```

The second lab has its own kubeconfig and ports 18091/19091/13001. Only these two
explicitly owned labs are accepted. Initial builds and official monitoring image
pulls need internet access. Python/Kubernetes bases and monitoring images are
digest-pinned; Python dependencies include pinned transitive versions. Local
application tags identify loaded image IDs; `.cache/kubernetes/image-lock.json`
records identities. This is a reproducible version/configuration workflow,
not a claim of bit-identical wall-clock timings or an offline supply chain.

## Serving, warm-up and shutdown

| Component | Startup | Readiness | Liveness | CPU request / limit | Memory request / limit |
|---|---|---|---|---|---|
| Inference | `/live`, 2 s Γ— 150 failures | `/ready`, 2 s, 1 failure | `/live`, 10 s Γ— 3 failures | 500m / 1 | 1 GiB / 2 GiB |
| Gateway | `/live`, 2 s Γ— 150 failures | `/ready`, 2 s, 1 failure | `/live`, 10 s Γ— 3 failures | 100m / 1 | 256 MiB / 512 MiB |
| Prometheus | `/-/healthy`, 2 s Γ— 60 failures | `/-/ready`, 2 s | `/-/healthy`, 10 s Γ— 3 failures | 100m / 500m | 128 MiB / 512 MiB |
| Grafana | `/api/health`, 2 s Γ— 60 failures | `/api/health`, 2 s | `/api/health`, 10 s Γ— 3 failures | 100m / 500m | 128 MiB / 512 MiB |

Inference loads and executes its existing model warm-up before opening the HTTP
listener. Startup probes protect that initialization; cold and terminating pods
are excluded from discovery/routing. Gateway readiness requires fresh telemetry
and a ready backend; missing backends do not themselves fail gateway liveness.
Liveness detects a stalled control loop or inference execution stuck beyond 60 s.

Admission and draining share an application lock. SIGTERM/SIGINT withdraw
readiness and stop new admissions, then wait for admitted application work and
HTTP response writes, bounded by a 60 s drain deadline. A two-second preStop
delay allows endpoint withdrawal to propagate; the pod grace is 75 s. Reads and
writes have socket timeouts, bodies and backend responses have size limits, and
HTTP serving handlers are bounded at 128, with eight bounded auxiliary handlers
for rejection and health/metrics access. Auxiliary reads time out after one
second. Consuming bounded POST bodies before 503 avoids unread-body TCP resets;
connections exceeding both pools can still close before a response. Connections close explicitly.
Requests exceeding handler capacity receive a separately counted transport
rejection before tier/body parsing. A client disconnect, forced kill, OOM or
deadline expiry cannot guarantee delivery of an already executed inference.

Kubernetes API calls have bounded connection/read timeouts and no hidden retries.
The control loop retries reconciliation on its next step. Resource-version
conflicts do not count as applied actions. No-ready/pending replicas are protected
from speculative scale-in. An inference PDB retains one pod for voluntary
evictions; it does not cover direct deletion, Deployment scale-in or node loss.

## Security and observability

All Deployments use non-root identities, RuntimeDefault seccomp, dropped Linux
capabilities, read-only root filesystems and disabled privilege escalation.
Only the gateway mounts a service-account token. RBAC permits reading pods and
reading/patching the named inference scale subresource; it denies secrets, pod
deletion and scaling another Deployment. Docker excludes local secrets/caches
and packages runtime modules rather than reports, results or deployment tools.

Host mappings listen only on loopback. Grafana anonymous access is Viewer-only;
its administrator password is randomly generated, stored in an ignored local
file and projected from a Kubernetes Secret. Do not publish that file/kubeconfig.
Administrator-password rotation requires updating both the stored Grafana
credential and deployment Secret; changing the startup variable alone does not
rotate an existing Grafana database password.

Prometheus scrapes every 2 s and evaluates four infrastructure alerts every 5 s:
gateway unavailable, stale telemetry, no ready inference, and reconciliation
failure. Alerts are visible locally; no external Alertmanager receiver is set up.
Prometheus retains at most seven days / 1500 MB in a 2 GiB PVC; Grafana uses a
1 GiB PVC. Both use Recreate updates for their single persistent instances.

Grafana contains the original eight serving panels plus four infrastructure
panels: process CPU, resident memory, telemetry/scrape health and HTTP saturation.
These are serving-process measurements, not cgroup-wide or physical node metrics.
CUDA VRAM remains zero in CPU mode. Latency histograms contain completed
requests; finalized SLA failure rates include late/rejected/failed application
requests. Pre-parse transport rejections have a separate counter, and exported
client outcomes retain every offered request, including these failures.

Live local links:

- [Gateway state](http://127.0.0.1:8091/state)
- [Prometheus](http://127.0.0.1:9091)
- [Prometheus alerts](http://127.0.0.1:9091/alerts)
- [Grafana](http://127.0.0.1:3001/d/jointsla-runtime)

## Scenarios, evidence and results

Final command exited successfully; traffic and infrastructure validators both
reported `passed`. The illustrative traffic run used 60 baseline requests,
1280 requests at a paced 120 requests/s burst, and 80 requests during deletion
of one owned inference pod. It is one controlled integration run, not a paired
Monte Carlo algorithm comparison or production load acceptance.

| Scenario | Offered / completed | SLA failures | Rejected | Mean completed latency (ms) | p95 completed latency (ms) |
|---|---:|---:|---:|---:|---:|
| baseline (seed 11) | 60 / 60 | 0.00% | 0.00% | 124.15 | 188.23 |
| burst (seed 23) | 1280 / 852 | 47.27% | 33.44% | 204.57 | 307.12 |
| failure (seed 31) | 80 / 80 | 0.00% | 0.00% | 29.93 | 41.47 |

The controller increased actual desired replicas from two to four, new replicas
served requests, and it returned to the unchanged warm floor of two. Every one
of the **1420 exported client outcomes** was reconciled against IDs, completed
counts, deadlines, failure flags and summaries. Mean/p95 latency in this table
uses completed requests only; SLA/rejection percentages use all offered traffic.
Transport errors were zero in these three cohorts. The stress SLA failure rate
of **47.27%** remains above 15%; no performance improvement or capacity sufficiency
is certified.

| Infrastructure scenario | Result |
|---|---|
| Model warm-up and discovery | Cold and terminating replicas excluded; real replacement observed before readiness |
| SIGTERM with queued work | 8/8 complete HTTP responses; admission/readiness withdraw; regression covers delayed response writes |
| Gateway process crash | Actual ancestor-namespace SIGKILL; restart count increased and serving recovered |
| Hung gateway | Actual ancestor-namespace SIGSTOP; outage alert fired and liveness restarted the container |
| API outage / scale conflict | Regression tests verify next-step recovery, fresh-state gating and no blind conflict replay |
| Least privilege | Own inference scale allowed; gateway scale, secrets and pod deletion denied |
| Monitoring restart | Historical Prometheus samples and a Grafana annotation survived both Deployment restarts |
| Observability | Healthy live scrape targets, valid four-rule alert group and 12 provisioned Grafana panels |
| Empty-cluster bootstrap | Separate owned cluster created; automatic one-to-two warm repair and pretrained response |
| Idempotent redeploy | Controller replica count and all pod UIDs preserved in test lab; lab removed afterward |
| Dependencies | Both application images passed `pip check` |
| Frozen integrity | 12 frozen sources/configuration verified; 20,769 historical and 439 additional hashes unchanged; 24,364 result file sizes/mtimes unchanged |
| Deployed source identity | Runtime modules and imported policy/router hashes match local files |

SIGKILL/SIGSTOP are sent from the kind node's ancestor PID namespace after
validating namespace, pod UID, container identity and PID. A child `kubectl exec`
cannot reliably deliver those signals to namespace PID 1. Tests assert actual
restarts and alert observation rather than treating signal-command success as
recovery proof. See [Linux PID namespace signal semantics](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html).

Curated evidence is in [evidence/infrastructure](prototype/kubernetes/evidence/infrastructure/):
[verdict](prototype/kubernetes/evidence/infrastructure/verdict.json),
[summary](prototype/kubernetes/evidence/infrastructure/summary.csv),
[all request outcomes](prototype/kubernetes/evidence/infrastructure/request_outcomes.csv),
[infrastructure checks](prototype/kubernetes/evidence/infrastructure/infrastructure_verification.json),
[traffic checks](prototype/kubernetes/evidence/infrastructure/runtime_verification.json),
[frozen integrity](prototype/kubernetes/evidence/infrastructure/frozen_integrity.json),
[fresh bootstrap](prototype/kubernetes/evidence/infrastructure/fresh_bootstrap.json),
[deployed configuration](prototype/kubernetes/evidence/infrastructure/deployed_configuration.json),
[deployed source hashes](prototype/kubernetes/evidence/infrastructure/deployed_source_hashes.json),
and [pytest output](prototype/kubernetes/evidence/infrastructure/pytest.txt).

Raw traces and command logs remain under ignored `prototype/.cache` and
`.cache/kubernetes`. Earlier failed validation attempts are retained locally:
RBAC syntax, rollout-cache timing, waiting for a terminating UID, Linux PID-1
signal delivery, and a persistence timestamp before counter creation were
corrected. A saturation regression then exposed the unread-body reset fixed in
the final transport. The final green run includes these fixes; older measurements
are not substituted for it. The separate bootstrap/idempotence check used the
same deployment workflow before the final overload-response fix; final rebuilt
images passed the complete primary-cluster validation afterward.

Research sources/configuration and frozen outputs were not rewritten. Serving
rolling telemetry and cooldown are in memory and reset on gateway restart; this
runtime limitation does not change the frozen simulation or policy.


## Limitations for a general production deployment

This is a local infrastructure prototype. Internet-facing or multi-tenant
production still needs authenticated/TLS ingress, an enforced network policy
with a suitable CNI, durable external backups/restore drills, image vulnerability
and provenance verification, secret rotation/management, external alert delivery,
and site-specific capacity and load acceptance. One gateway and one host provide
no high availability; restart/rollout and host failure create availability gaps.
PVC data survives pod restarts, not deletion/loss of the kind node or cluster.
There is no multi-service or physical multi-edge/GPU deployment validation.
Crash recovery cannot promise exactly-once execution or lossless failover, and
the bounded stress workload can still violate SLAs. These require a deployment
target and operational acceptance criteria; they are not silently certified here.

## Technical references

- [Kubernetes probe semantics](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Lifecycle hooks and grace-period accounting](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
- [kind image loading and local cluster setup](https://kind.sigs.k8s.io/docs/user/quick-start/)
