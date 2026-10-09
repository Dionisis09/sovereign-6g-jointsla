# JointSLA Kubernetes comparative evaluation: registered protocol v2

Implementation and pilot acceptance completed on 8 October 2026. The main
experiment freezes this document, all benchmark sources and image identities
before its first block. Execution status is recorded separately in the immutable
main manifest/progress/completion files; this protocol remains unchanged.

## Current evidence and corrected interpretation

The local infrastructure passes its operational audit. Neither 306/310 tests,
1,420 request outcomes nor a dashboard proves algorithmic superiority.
The 38.83% and 47.27% bursts are separate runs at different infrastructure
revisions/start states, not two independent replications of a frozen treatment.
There is no matched Kubernetes static, reactive or native HPA comparator.

Reconstruction of the final 1,280-request burst:

| Tier | Offered | Within deadline | Completed late | Rejected 503 | SLA failures |
|---|---:|---:|---:|---:|---:|
| Gold | 427 | 112 | 177 | 138 | 315 (73.77%) |
| Silver | 427 | 258 | 0 | 169 | 169 (39.58%) |
| Bronze | 426 | 305 | 0 | 121 | 121 (28.40%) |
| Total | 1,280 | 675 | 177 | 428 | 605 (47.27%) |

All 428 rejected rows contain an inference endpoint address. All 177 late
completions are Gold; 176 remain over deadline even after subtracting measured
client concurrency wait. Gold late calls have mean client wait ~0.064 ms.
This points investigation toward request-path latency and backend rejection,
but does not separate backend queueing, execution, network, resource throttling
or cold-start effects. The original CSV discarded returned error reasons and
backend execution/queue timings. In particular, **503 is not synonymous with
queue-full**: draining/saturation and other rejection branches also exist.
These are descriptive observations, not causal attribution.

Sources: [failure audit](evidence/research_gap_audit/failure_audit.json),
[tier reconstruction](evidence/research_gap_audit/failure_by_tier.csv),
[per-request classification](evidence/research_gap_audit/request_classification.csv).
Reproduce: `python -m prototype.kubernetes.analyze_failure_gaps`.

## Isolated lab and trace acceptance

The primary infrastructure and frozen simulator remain unchanged. All interventions
use `kind-jointsla-validation`, explicit `.cache/kubernetes-validation/config`,
namespace `jointsla-prototype`, gateway port 18091, Prometheus 19091 and Grafana
13001. The lab has one virtual node on the same physical host, not five physical
edge sites. Historical 38.83%/47.27% runs are descriptive context, excluded from
these statistics. Fresh benchmark images fork the serving transport only to
expose policy hooks and trace metadata; original JointSLA planner/router functions
are imported unchanged. Fork differences are enumerated in gateway_provenance.json.

Six-arm seed-901 pilots and an additional 4,800-request seed-902 native-HPA
acceptance test are excluded from main. The latter must demonstrate scale-up.
Unit and real-HTTP tests verify explicit queue-full rejection, request identity,
completed queue/execution timings, missing-data handling and reset safety.
Existing infrastructure validation separately covers startup, drain and recovery.

Every offered request retains its tape/input seed, tier, deadline, absolute
scheduled/offer/dispatch/finish times, client scheduling delay, HTTP status,
returned error, routed endpoint, pod name/UID, echoed request ID, gateway and
backend duration, backend queue/execution time and pretrained/model-load metadata.
Missing fields remain unknown. Categories are mutually exclusive on-time/late,
explicit queue-full, draining, no fresh-ready endpoint, HTTP handler saturation,
backend/client transport failure, other HTTP failure and unknown rejection.
Queueing, cold readiness and throttling exposures can overlap; do not label all
503s as queue-full or infer a causal mechanism solely from correlation.

## Six predeclared treatments

| Arm | Scaling | Ready-only routing |
|---|---|---|
| static | Fixed two warm replicas | Round-robin |
| reactive | CPU >80% up / <20% down, one step, min 2/max 4 | Shortest queue |
| hpa | Native autoscaling/v2 CPU target 80%, min 2/max 4 | Shortest queue |
| joint | Unchanged JointSLA runtime warm-headroom planner | Unchanged JointSLA router |
| joint_sq | Same JointSLA planner | Shortest queue |
| reactive_joint | Same reactive scaler | JointSLA router |

JointSLA vs reactive is primary; static and HPA are secondary core comparisons.
Two mechanism arms are registered exploratory interventions. Each changes one
rule, but realized replica trajectories can change through feedback: they do not
hold the exact sequence of scaling actions constant. No static-4 arm or tuning
of the JointSLA policy is included.

All arms use pretrained MobileNetV3-Large CPU inference on identical synthetic
224x224 tensors; 500m CPU request / 1-core limit; 1Gi RAM request / 2Gi limit;
one serial worker, eight waiting requests, common probes/draining/transport and
monitoring. Global JointSLA control deadline remains 200 ms, cold allowance 10 s,
2 s gateway decisions and 30 s action cooldown. Per-request deadlines remain
Gold 200 / Silver 400 / Bronze 800 ms. Do not reinterpret CPU execution as GPU
performance or the synthetic input as an inference-accuracy experiment.

Reactive CPU is measured relative to the 500m request, averaged across ready
pods and smoothed over ten seconds of gateway polls. Resource API values are
already time-window averages and can repeat across polls; these are not ten
independent instantaneous measurements. Missing/stale (age >30 s) or incomplete
CPU data holds the target, including scale-in. Every arm makes identical resource
API queries to share instrumentation overhead.

Native HPA is the sole scale actuator in its arm; gateway actuation is disabled
for static/HPA. Kubernetes 1.36.4 and metrics-server 0.9.0 are pinned by image
identity. Metrics-server's kubelet-insecure-tls flag is confined to the local kind
lab. HPA has no behavior override: its asynchronous controller/metric collection,
tolerance and stabilization use this Kubernetes version's defaults. Controller
command flags and HPA spec are captured in the frozen manifest. Default downscale
stabilization is 300 s and typical controller synchronization is 15 s; those timings
are not silently replaced with the gateway's cooldown. A short burst is a timescale
comparison, not evidence that native HPA fails on all sustained workloads.
[Official HPA documentation](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/),
[metrics-server 0.9.0](https://github.com/kubernetes-sigs/metrics-server/releases/tag/v0.9.0).

## Reset, workload and immutable execution

Run 30 serial paired blocks, seeds 1001-1030, six arms each: 180 trials and
230,400 offered outcomes. A block—not an individual request—is a replication.
Five randomized Latin cycles balance every arm into every position five times;
order seed 39107. Save the schedule and SHA-256 workload/source/image manifest
before running. Each block replays the same generated workload tape in all arms;
actual offers/dispatches are measured because wall-clock schedules can differ.

Before each arm delete the owned benchmark HPA, drain/stop its gateway, return
inference to two replicas, start a fresh policy/controller process, wait for two
ready idle pods with no terminating pods, reset serving cycle-history counters,
and send eight identical direct preconditioning requests to each backend. Keep
real loaded models warm, then settle for 35 s (past metric windows/cooldown).
HPA arms additionally wait for ScalingActive and a valid resource metric. Verify
two ready idle replicas, expected policy and available CPU before the burst.

Primary tape: 1,280 requests at 120 requests/s, concurrency 32, cyclic tiers and
fixed 200/400/800 ms deadlines, approximately 10.7 s. Retain a fixed 20 s follow-up
after the final response. A primary run is not replaced with the longer HPA pilot.
Do not execute competing validation arms concurrently. Existing idle primary
monitoring/services remain running; other host background activity is uncontrolled
and is a limitation of single-host measurements.

Failed trials are retained and stop the runner. Completed validated trials may
resume only with matching frozen source/image/workload hashes. No selective
reruns for better SLA, optional stopping or outcome-dependent parameter changes.

## Metrics, analysis and limitations

Primary endpoint is per-run all-offered SLA failure percentage: every non-200
response or completed request after its deadline counts as a failure. Export
rejections, late completions, transport/unknown failures, completions and each
tier separately. Completed latency mean/p95/p99 is conditional on completion
and cannot replace the all-offered endpoint.

Sample pod lifecycle/HPA status and target/ready counts every 0.5 s plus common
read-only cgroup telemetry. Integrate target and ready replica-seconds over burst
start to last response plus 20 s; readiness deficit integrates max(target-ready,0).
Report target changes, logged controller actions, new-pod creation-to-ready delays,
cgroup CPU counter deltas, throttled-period fraction and observed inference RAM.
Cgroup counters cover observed ready backends; startup or retired-pod CPU can be
missed. Cached gateway telemetry is collected every two seconds. The sampled
control-step gauge includes collection/reconciliation; deduplication by snapshot
timestamp is an approximation, not a separate profiler of pure planner runtime.

Reconstruct every outcome independently from CSV and reconcile counts/tape hashes.
Report 30 values, mean/sample standard deviation per arm, and paired JointSLA-minus-
comparator effects with 95% percentile block-bootstrap intervals (10,000 resamples,
seed 39108). Bootstrap block-level paired differences. Two-sided paired Wilcoxon
p-values use Pratt zero handling; apply Holm across the three core comparisons.
The two mechanism-arm comparisons remain explicitly exploratory, outside that
family. Pointwise intervals do not guarantee simultaneous coverage. Thirty blocks
are a starting design, not a power certificate or an independent population of
physical deployments.

No gain is assumed. Report failure categories, resource/latency trade-offs and
negative findings. Neither operational completeness nor favorable comparison
establishes literature novelty. Unsupported previous citations remain excluded;
prior-work comparison must use verifiable primary sources. Conclusions are limited
to this CPU single-model local prototype and registered burst regime.

## Version-2 engineering correction

The initial v1 attempt retained two verified trials and then stopped before its
third burst because the final one-shot preflight found incomplete CPU metrics.
Its complete source snapshot, CSVs and failure record remain in
`prototype/.cache/kubernetes_comparison_v1/`; none is pooled into v2.

Version 2 uses bounded persistent Kubernetes API clients for reset/readiness
instead of repeated kubectl processes, and waits for complete CPU data rather
than asserting that one snapshot is valid. During preflight only, endpoint
propagation errors are awaited; burst requests are never replayed. Require
actual target=2 and matching ready pod UIDs before starting. Failed preparation
checks are retained outside main. Gateway processes still restart;
workload, model, policy functions, metric freshness rule, preconditioning and
35/20-second windows are unchanged. All six preparation paths are revalidated.
The prior full six-arm/HPA-actuation pilot can be reused only if serving and
workload hashes match exactly; its checksum is captured. A new manifest precedes
all 180 v2 trials. Performance improvement is measured, not assumed.

## Commands and deliverables

```powershell
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.deploy --lab validation --skip-build
.venv/Scripts/python.exe -m prototype.benchmark.setup
.venv/Scripts/python.exe -m prototype.benchmark.experiment --pilot
# Or, after an accepted unchanged-serving v1 pilot:
.venv/Scripts/python.exe -m prototype.benchmark.experiment --preflight
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m prototype.benchmark.experiment --run
.venv/Scripts/python.exe -m prototype.benchmark.analyze
# Serial execution plus automatic reconstruction/protected-file verification:
.venv/Scripts/python.exe -m prototype.benchmark.pipeline
```

Raw immutable trials: `prototype/.cache/kubernetes_comparison_v2/`.
Curated statistics/figures/report: `prototype/kubernetes/evidence/comparison_v2/`.
The local infrastructure was already functionally complete; this separate research
evaluation addresses matched baselines, statistical repetitions and measured
failure attribution. Its manifest/completion/report establish what actually ran.
