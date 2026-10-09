# Local Kubernetes validation

The [unified final report](../../JOINTSLA_FINAL_REPORT.md) combines architecture,
operational validation and both recorded bursts (38.83% earlier; 47.27% final
audit). The final Grafana view has 28 panels, with dated 306-test/1,420-outcome
evidence clearly separated from live telemetry. The full suite now passes 310
tests. Request/action headline totals are exact counters since gateway startup;
they reset on restart. CPU/RAM panels measure serving processes. Kubernetes
restart counts and readiness are observed using the existing read-only RBAC.

After the documented 96-request demo, run
`python -m prototype.kubernetes.validate_dashboard` for query/provisioning,
observer, CSV and freeze checks. Its compact record is in
`evidence/final_dashboard/dashboard_verification.json`, separate from the audit.

The first real actuator test runs in `kind-jointsla-prototype`, using its own
ignored `.cache/kubernetes/config`. It does not use or modify the user's global
kubeconfig. The cluster has **one virtual Kubernetes node on one physical
Windows/Docker host**, CPU inference, a bounded serial queue and one model service.
It is not a physical multi-edge or GPU scheduling experiment.

## Verified behavior

- Bootstrap one inference pod; JointSLA automatically repairs the Gold warm floor to two.
- Offer a paced 120 requests/s burst; JointSLA scales from two to four pods.
- Confirm new ready replicas actually serve requests.
- After the burst and 30-second cooldown, automatically return to two warm pods.
- Delete one inference pod; withdraw its endpoint on a transport failure or
  draining response, without retrying the failed request. Kubernetes replaces
  the pod and the gateway resumes routing to two healthy endpoints.
- A queue-full 503 stays a rejection and does not quarantine a healthy replica.

See [VALIDATION.md](VALIDATION.md) for observations. No SLA target or scientific
superiority claim follows from this single-host integration test. CPU/memory
placement belongs to the Kubernetes scheduler. GPU VRAM/edge-node placement
and the complete simulator-specific JointSLA state machine are not ported.

## Reproduce on Windows

Prerequisites: Windows, Python 3.12 (or the existing project virtual environment),
Docker Desktop with a Linux amd64 daemon, Docker Compose v2 and kubectl. From the
repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File prototype/kubernetes/deploy.ps1 -Validate
```

The script installs pinned host dependencies into `.cache/infra-venv`, downloads
checksum-verified kind v0.33.0 if absent, creates/reuses the owned cluster with a
pinned Kubernetes node image, builds the existing pretrained inference and
controller images, loads an amd64 archive, applies manifests and monitoring,
waits for startup, and executes live validation. No registry push or global
kubeconfig change occurs. Internet is needed for the initial build and official
image pulls. Images have recorded local identities; monitoring images and the
Python base are pinned by digest and transitive Python dependencies by version.

Use `-SkipBuild` to reuse the last built application images. Omit `-Validate` for
deployment plus smoke checks only. Reapplying preserves the controller-owned
replica count instead of resetting it to one. A new Deployment starts with one
replica, then the unchanged Gold warm rule repairs it to two. The gateway uses
Recreate updates to avoid overlapping controllers; updates have an availability
gap because this local prototype has one gateway.

The full validator deletes an owned inference pod, kills and hangs the gateway
process, and restarts monitoring. Expect several minutes and deliberate local
service interruptions. Run it outside an interactive load session. It exports
request outcomes and machine-readable evidence under `prototype/.cache`.

```powershell
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.validate_runtime
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.validate_infrastructure
```

For a separate fresh-cluster bootstrap check, with the primary demo untouched:

```powershell
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.deploy --lab validation --skip-build
.cache/bin/kind.exe delete cluster --name jointsla-validation
```

This test lab uses isolated `.cache/kubernetes-validation/config` and loopback
ports 18091/19091/13001. It is restricted to the two named local labs. See the
final [infrastructure audit](../../INFRASTRUCTURE_VALIDATION.md) for verified
scenarios, resource/probe settings, source integrity and remaining boundaries.

## Live links

- Kubernetes gateway: http://127.0.0.1:8091/state
- Kubernetes Prometheus: http://127.0.0.1:9091
- Kubernetes Grafana: http://127.0.0.1:3001/d/jointsla-runtime

The original Compose demo remains at 8090/9090/3000. These are separate metrics
and controllers. Kind exposes the new NodePorts only on host loopback. Pod IPs,
API credentials and image archives remain local, under ignored caches.

## Evidence and operational boundaries

Each `prototype/.cache/kubernetes_<UTC timestamp>/` run contains request outcomes
and summaries for baseline/burst/failure, a replica timeline, gateway action log,
pod/Deployment snapshots and verification JSON. CSV outcomes include client
queue time for paced submissions, HTTP status, per-request deadline and SLA
failure. Dropped or failed traffic remains in the offered denominator. The first
unpaced stress test and its poor failure behavior are preserved locally; the
validated run follows the endpoint-withdrawal fix and uses paced burst traffic.
These workload changes mean the runs are not a paired algorithm comparison.

Controller decisions use only completed observations and current queue/readiness.
No load-generator schedules are supplied to the controller. There is no HPA
acting on the inference Deployment. The service account can read pods in the
prototype namespace and patch only the `inference` scale subresource.
Kubernetes performs pod replacement; JointSLA performs routing and replica target
reconciliation. Pending pods are not removed merely because no replica is ready.

The failure test permits at most four unsuccessful requests out of 80; it is
not a guarantee of lossless failover. No retries prevents duplicate inference.
The integration script checks target increase, traffic reaching newly ready
replicas, warm-floor return and replacement of the deleted pod UID. It remains
separate from regular pytest, so tests do not create/delete infrastructure.

Optional cleanup, when the local demo is no longer needed:

```powershell
.cache\bin\kind.exe delete cluster --name jointsla-prototype
```

The frozen research inputs, profiles, policy sources and paper results are unchanged.
