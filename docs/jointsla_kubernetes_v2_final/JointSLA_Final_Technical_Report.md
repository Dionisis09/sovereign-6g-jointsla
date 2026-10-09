# JointSLA final technical and experimental report

Completed Kubernetes comparison v2 and preserved local infrastructure evidence
9 October 2026

JointSLA reduces mean all-offered SLA failures to 49.89% from 61.43% for reactive scaling, 61.50% for static allocation and 62.39% for native HPA in the completed Kubernetes comparison v2. The primary paired difference is −11.54 percentage points, with a 95% block-bootstrap interval of [−13.98, −9.06] and Holm-corrected p = 3.725e−08.

This improvement uses more target replica-seconds than the main baselines. JointSLA averages 103.45 versus 65.12 for reactive scaling, a 58.84% increase. The evidence does not establish greater resource efficiency. The failure target below 15% remains unmet.

| Policy | SLA failure % | p95 ms | HTTP 503 % | Target replica s |
| --- | --- | --- | --- | --- |
| Static-2 / RR | 61.50 ± 7.85 | 320.99 ± 67.12 | 43.22 ± 8.03 | 61.90 ± 0.10 |
| Reactive / SQ | 61.43 ± 6.94 | 322.85 ± 55.60 | 43.16 ± 7.48 | 65.12 ± 3.39 |
| Native HPA / SQ | 62.39 ± 7.37 | 328.26 ± 58.23 | 43.76 ± 7.92 | 64.03 ± 4.65 |
| JointSLA | 49.89 ± 8.12 | 318.63 ± 47.74 | 33.98 ± 7.75 | 103.45 ± 14.60 |

The local prototype is complete within its audited single-host boundary. This means reproducible deployment, real inference, bounded scaling and verified operational recovery. It does not certify a production service, a multi-edge deployment or attainment of the research SLA target.

## How to read this report

The report covers research scope, historical audits, architecture, operation, paired evaluation, failure analysis, resource trade-off and reproducibility. All v2 numbers derive from canonical_results.json and preserved run/request records. Existing reports and experiments remain unchanged. This report integrates their final publication findings.

# Research scope and historical evidence

JointSLA couples deadline-aware request routing with replica headroom. The simulator evaluates broader CPU/GPU capacity, queues, scaling and placement. The Kubernetes prototype adapts unchanged joint_routing.router.choose and joint_sla_v2.policy.required_warm functions to one real CPU inference Deployment. This evaluation tests that adapter rather than the full simulator state machine.

The initial simulator explored five edge nodes and twenty applications. The later frozen JointSLA-v2 held-out study used ten simulated nodes, forty services and 100 slots of 100 ms, with seeds 31–60 and two load regimes. Its 180 simulations and 3,046,965 outcomes are separate from the Kubernetes evidence. Its overall success criterion failed because latency/resource safeguards were not jointly met. Simulator outcomes and hardware-derived parameters are not observations of a physical GPU or multi-edge cluster.

## The 1420 request infrastructure audit

| Cohort | Offered | Completed | SLA failures | p95 ms |
| --- | --- | --- | --- | --- |
| Calm | 60 | 60 | 0.00% | 188.23 |
| Burst | 1280 | 852 | 47.27% | 307.12 |
| Pod recovery | 80 | 80 | 0.00% | 41.47 |

These 1,420 outcomes validate functional serving and recovery. They are historical integration checks excluded from paired v2 statistics.

## Why 38.83 percent differs from 47.27 percent

The earlier burst has 497 failures out of 1,280: 160 late completions plus 337 HTTP 503 rejections, or 38.828125%. The final infrastructure audit has 605 failures: 177 late plus 428 rejected, or 47.265625%. Both use seed 23, but infrastructure revision and starting state differ. They are neither matched policy baselines nor independent replications of a frozen treatment. The increase of 8.4375 percentage points has no isolated causal explanation. Comparison v2 supplies the matched evaluation missing from those demonstrations.

# Architecture and Kubernetes deployment

A client calls the gateway. The gateway hosts the existing JointSLA controller, polls backend state, selects ready non-terminating inference pods and patches the named Deployment scale subresource. Kubernetes creates, schedules and replaces pods. Prometheus scrapes cached serving/controller/pod metrics and persists them to a volume. Grafana queries Prometheus and persists configuration and annotations separately.

The primary local cluster is jointsla-prototype. The comparison uses the isolated kind-jointsla-validation lab and explicit kubeconfig, preserving the primary system. Namespace jointsla-prototype contains one gateway and one inference Deployment. Validation ports are gateway 18091, Prometheus 19091 and Grafana 13001. Historical primary ports are 8091, 9091 and 3001.

| Component | CPU request / limit | RAM request / limit |
| --- | --- | --- |
| Inference | 500m / 1 core | 1 / 2 GiB |
| Gateway | 100m / 1 core | 256 / 512 MiB |
| Prometheus | 100m / 500m | 128 / 512 MiB |
| Grafana | 100m / 500m | 128 / 512 MiB |

The host is Windows with Docker Desktop Linux amd64 and one virtual kind node. Kubernetes 1.36.4, kind 0.33.0, metrics-server 0.9.0 and serving image identities are recorded in the frozen manifest. Inference uses pretrained MobileNetV3-Large IMAGENET1K_V2 with CPU PyTorch 2.10 and torchvision 0.25. Inputs are synthetic 224 × 224 tensors. This is a serving study, not an accuracy evaluation.

Each inference pod has a serial worker and eight waiting slots plus one active request. HTTP concurrency is bounded at 128 handlers and eight auxiliary handlers. The gateway and monitoring share physical host resources. Extra replicas do not imply extra physical nodes. Frozen image identities, model metadata and pinned dependencies make the configuration inspectable.

# Lifecycle protection and failure recovery

## Probes and model warm-up

Inference startup and liveness use /live and readiness uses /ready. Model loading and warm-up complete before the HTTP listener opens. Gateway readiness requires fresh controller state and a ready backend. A backend outage alone does not fail gateway liveness. A stuck controller or inference execution beyond the watchdog bound does. Startup probes allow 150 failures at two-second intervals. Readiness checks every two seconds and withdraws after one failure. Liveness checks every ten seconds and allows three failures.

## Draining and scaling

The runtime samples serving state every two seconds, tracks arrivals over ten seconds and applies a thirty-second action cooldown. Scale patches include resourceVersion, so conflicts fail safely and reconcile later. New pods join routing after readiness. Both serving pods have 75 s termination grace, a two-second preStop delay and a sixty-second bounded drain. SIGTERM stops admission and waits for admitted work and full response writes. Body sizes, sockets and auxiliary handlers are bounded.

## Recovery and security boundary

A Deployment replaces failed inference pods. Kubernetes restarts a crashed or hung gateway. Forwarded requests are not automatically replayed because completion could be ambiguous. The inference PDB with minAvailable one constrains voluntary evictions but cannot guarantee availability during node loss, direct deletion or scale-in. Gateway Recreate updates avoid simultaneous scaling writers and incur a rollout gap.

Serving containers run non-root with dropped capabilities, RuntimeDefault seccomp, read-only root filesystems and no privilege escalation. Only the gateway mounts a service-account token. RBAC permits pod reads and get/patch of the named inference scale subresource, without Secret access or pod deletion. Host ports bind to loopback. Grafana anonymous access is Viewer-only. These are local isolation measures rather than an audited internet-facing security design.

# Observability and operational validation

Prometheus exposes offered/completed/late/rejected requests, tier deadlines, queues, target and ready replicas, action outcomes, controller freshness/timing, model readiness, handler saturation and pod restart/condition metrics. A read-only observer caches API snapshots. Scrapes do not query Kubernetes synchronously or influence decisions. Errors retain visibly stale snapshots and mark observer health false.

The final historical Grafana dashboard has 28 panels for target versus ready replicas, request load, latency, SLA failures, completions, actions, pod recovery, queues, CPU/RAM, controller health and alerts. GPU/VRAM indicators remain zero or unavailable in this CPU lab. Live histogram p95 differs from exact per-run CSV p95.

| Validation record | Result |
| --- | --- |
| Original infrastructure audit | 306 tests passed; 1420 outcomes checked |
| Final dashboard extension | 310 tests passed including observer regressions |
| Comparison and pipeline additions | 330 tests passed in retained pre-run record |
| SIGTERM with queued work | 8 of 8 complete JSON responses |
| Inference replacement cohort | 80 of 80 requests completed |
| Gateway crash and hang | Restart and serving recovery observed |
| Monitoring restart | Prometheus history and Grafana annotation retained |
| Empty cluster and redeploy | Bootstrap succeeded; reapply retained pod UIDs |

Test counts describe dated stages, not conflicting results of one run. This publication task does not rerun Kubernetes traffic or change serving code. Comparative trace checks independently reconstructed all 230,400 outcomes. API conflicts, stale metrics, bounded scrapes, withdrawal and retry behavior have regression coverage in the existing suite.

Operational completeness covers the tested local prototype. It does not establish multi-host failover, an availability SLO, inference accuracy or scientific performance superiority.

# Registered paired experimental protocol

We compare six policies in 30 serial paired blocks using seeds 1001–1030. Each policy receives the same 1,280-request tape within a block at 120 requests/s with client concurrency 32. The completed design contains 180 trials and 230,400 offered outcomes. Gold, Silver and Bronze deadlines are 200, 400 and 800 ms. This Kubernetes workload is a deterministic paced burst of approximately 10.7 s. Seeds vary synthetic model tensors. It is distinct from the simulator’s stochastic traffic process.

| Arm | Scaling rule | Routing |
| --- | --- | --- |
| Static-2 | Fixed two warm replicas | Round-robin |
| Reactive | CPU >80% up or <20% down, one step | Shortest queue |
| Native HPA | CPU target 80%, native controller | Shortest queue |
| JointSLA | Frozen warm-headroom planner | Frozen SLA risk router |
| Joint scaler / SQ | Same JointSLA planner | Shortest queue |
| Reactive / Joint router | Same reactive rule | JointSLA router |

Before every arm we drain and stop the owned gateway, remove the benchmark HPA, return inference to two replicas and start a fresh policy process. We require two ready idle pods, no terminating pods and matching ready pod UIDs. Cycle histories reset, each backend receives eight identical direct preconditioning requests, and all arms settle for 35 s. The HPA arm also requires ScalingActive and valid CPU metrics. Actual scheduled, offered and dispatch timestamps remain in the traces. Every trial retains 20 s of follow-up after its last response.

Five randomized Latin cycles balance every arm into every position five times, with order seed 39107. Arms run serially. Native HPA is the sole actuator in its arm. Static and HPA disable gateway scaling. All arms make identical resource queries to share instrumentation overhead.

Reactive scaling averages CPU relative to the 500m request across ready pods and a ten-second trail of polls. API samples are already window averages and may repeat. Stale values older than thirty seconds or incomplete coverage hold the target. Bounds are two to four replicas. HPA targets 80% CPU without behavior overrides. Its native asynchronous timing and default 300 s downscale stabilization are preserved [4]. A short burst tests controller timescale response and cannot establish HPA performance on sustained traffic.

# JointSLA design and measurement definitions

Let q be queued requests, λ the recent arrival rate in requests/s, L the observed serial service-cycle duration, D the control deadline and R the cold-readiness allowance, all times in seconds. With h = max(D − L, 0), the frozen warm rule requests N = min(Nmax, max(floor, ceil(m × max(qL/h, (q + λR)L/(R + h))))). In this runtime the Gold multiplier m is 1.5, floor is two and Nmax is four. A nonpositive or unknown cycle requests the cap. If h is zero, zero demand keeps the floor and positive demand requests the cap. This is causal demand headroom, without a learned predictor.

The router estimates completion from observed waiting work, a busy service cycle and execution duration. It forms deadline slack and a variance-based risk proxy, then orders eligible candidates by risk, greater slack, lower estimated completion and deterministic replica identity. Nonpositive slack receives risk one. The proxy is not a calibrated probability or an SLA guarantee. The Kubernetes adapter supplies real ready-pod queues and service cycles. Simulator network/resource/migration terms are not physical multi-edge measurements in this adapter.

## Outcome and resource definitions

SLA failure percentage = 100 × (non-200 outcomes + late 200 completions) / all offered requests. Rejected and late classes are disjoint. Completion means successful HTTP execution and does not imply SLA success. Completed latency includes measured client concurrency wait and request-path time. Per-run p95 is conditional on completion and does not assign artificial latency to rejected requests.

Target replica-seconds integrate desired replicas from burst start through the last response and fixed 20 s follow-up. Ready replica-seconds integrate ready replicas over the same window. Target cost includes pending capacity. It is a deployment-time proxy, not a bill, energy or actual CPU consumption. Ready-only cgroup deltas can omit startup and retired-pod use. Pod timelines sample every 0.5 s while gateway caches refresh every two seconds.

## Statistical analysis

Each block is the unit of replication. We report means and sample standard deviations over 30 run-level measurements. Paired JointSLA-minus-comparator SLA differences use 10,000 percentile block-bootstrap resamples with seed 39108. Two-sided Wilcoxon tests use Pratt zero handling. Holm corrects the family of three core comparisons against reactive, static and HPA. The two registered mechanism comparisons remain exploratory with uncorrected p-values. The intervals are pointwise, not simultaneous coverage guarantees. Individual requests are not independent replications.

The frozen comparison table is copied exactly. New resource trade-off intervals are descriptive paired bootstrap calculations from the same trials with 10,000 resamples and seed 271830. They introduce no treatment, tuning or new traffic and have no confirmatory corrected-p family.

# Main Kubernetes SLA result

JointSLA reduces mean all-offered SLA failures to 49.89% from 61.43% for reactive scaling, 61.50% for static allocation and 62.39% for native HPA in the completed Kubernetes comparison v2. The primary paired difference is −11.54 percentage points, with a 95% block-bootstrap interval of [−13.98, −9.06] and Holm-corrected p = 3.725e−08.

![Figure 1  All-offered SLA failures. Bars show mean ± sample standard deviation across thirty blocks, not confidence intervals.](figures/01_sla_failures.png)

| Policy | SLA failure % | p95 ms | HTTP 503 % | Target replica s |
| --- | --- | --- | --- | --- |
| Static-2 / RR | 61.50 ± 7.85 | 320.99 ± 67.12 | 43.22 ± 8.03 | 61.90 ± 0.10 |
| Reactive / SQ | 61.43 ± 6.94 | 322.85 ± 55.60 | 43.16 ± 7.48 | 65.12 ± 3.39 |
| Native HPA / SQ | 62.39 ± 7.37 | 328.26 ± 58.23 | 43.76 ± 7.92 | 64.03 ± 4.65 |
| JointSLA | 49.89 ± 8.12 | 318.63 ± 47.74 | 33.98 ± 7.75 | 103.45 ± 14.60 |
| Joint scaler / SQ | 51.99 ± 7.14 | 329.54 ± 54.15 | 34.87 ± 6.74 | 112.84 ± 12.79 |
| Reactive / Joint router | 60.95 ± 7.27 | 323.45 ± 49.01 | 45.07 ± 7.34 | 65.44 ± 4.01 |

All three core comparisons are statistically significant under the registered Holm family. The claim applies to this CPU burst regime and registered baselines. JointSLA still fails nearly half of offered deadlines and has substantial unmet service demand.

# Completed latency and HTTP rejection

![Figure 2  Mean of per-run completed-request p95 values with sample standard deviation.](figures/02_p95_latency.png)

![Figure 3  HTTP 503 rate over all offered requests with sample standard deviation.](figures/03_http503.png)

JointSLA completed p95 is 318.63 ± 47.74 ms versus 322.85 ± 55.60 ms for reactive scaling. Mean completed latency is 222.00 ms versus 268.14 ms. HTTP 503 falls descriptively from 43.16% to 33.98%. Confirmatory tests address SLA failures. These secondary endpoints do not establish a significant p95 improvement and exclude rejected requests from latency.

# Failure attribution and tier outcomes

![Figure 4  Deadline-specific failure rates with sample standard deviation. Gold has the strictest deadline.](figures/05_tier_failures.png)

| Policy | Gold % | Silver % | Bronze % |
| --- | --- | --- | --- |
| Static-2 / RR | 96.42 ± 1.41 | 43.79 ± 13.54 | 44.26 ± 9.43 |
| Reactive / SQ | 96.49 ± 1.32 | 44.99 ± 14.15 | 42.76 ± 7.75 |
| Native HPA / SQ | 96.64 ± 1.45 | 46.17 ± 13.51 | 44.33 ± 8.96 |
| JointSLA | 79.63 ± 12.84 | 35.94 ± 11.62 | 34.06 ± 8.44 |
| Joint scaler / SQ | 84.18 ± 5.06 | 37.28 ± 11.34 | 34.47 ± 7.76 |
| Reactive / Joint router | 89.06 ± 13.10 | 46.30 ± 11.67 | 47.44 ± 7.56 |

JointSLA produces 19,158 failures among 38,400 requests: 13,050 explicit queue-full HTTP 503 outcomes plus 6,108 late completions. Reactive produces 23,589 failures: 16,575 queue-full rejections plus 7,014 late completions. V2 error fields identify queue-full branches. No observed v2 failure belongs to other retained categories. This attribution cannot be applied retroactively to earlier unclassified 503 responses.

JointSLA Gold fails 10,201 of 12,810 requests, Silver 4,604 of 12,810 and Bronze 4,353 of 12,780. Gold failures remain 79.63%. FIFO admission and tighter deadlines matter to interpretation. Queue timing and CPU throttling are measured exposures, but their causal shares require interventions that this experiment does not provide.

# Paired effects and corrected significance

![Figure 5  Paired JointSLA-minus-comparator effects. Negative values favor JointSLA. Mechanism arms remain exploratory.](figures/06_paired_and_ablations.png)

| Comparison | Difference pp | 95% interval pp | p value |
| --- | --- | --- | --- |
| JointSLA minus reactive | -11.54 | [-13.98, -9.06] | 3.725e-08 |
| JointSLA minus static | -11.61 | [-13.79, -9.33] | 2.794e-08 |
| JointSLA minus hpa | -12.50 | [-15.18, -9.99] | 2.351e-06 |
| JointSLA minus joint_sq | -2.10 | [-4.84, 0.73] | 0.158844 raw |
| JointSLA minus reactive_joint | -11.05 | [-13.73, -8.30] | 3.14787e-07 raw |

The first three p-values are Holm-corrected across core comparisons. The last two are raw exploratory values. Intervals use paired block differences rather than treating 230,400 requests as independent samples. The router ablation interval crosses zero, so a distinct routing benefit is unsupported.

Balanced order, identical tapes, common instrumentation, reset checks and frozen sources reduce avoidable confounding. They cannot remove host contention, timing variation or dependence from serial execution on one machine.

# Performance and replica-time trade-off

This improvement uses more target replica-seconds than the main baselines. JointSLA averages 103.45 versus 65.12 for reactive scaling, a 58.84% increase. The evidence does not establish greater resource efficiency. The failure target below 15% remains unmet.

![Figure 6  Trial points and policy means jointly show failures and target replica-time. Lower failures use more replica-time than the main baselines.](figures/07_performance_cost.png)

| Comparator | Additional replica s | 95% descriptive interval | Increase of mean cost |
| --- | --- | --- | --- |
| Reactive / SQ | 38.32 | [33.37, 43.38] | 58.84% |
| Static-2 / RR | 41.55 | [36.58, 46.65] | 67.12% |
| Native HPA / SQ | 39.42 | [34.06, 44.92] | 61.57% |

Against reactive the additional target cost is 38.32 replica-seconds, with descriptive interval [33.37, 43.38]. Mean on-time requests increase from 493.70 to 641.40. Target replica-seconds per on-time request, as a ratio of means, increase from 0.13 to 0.16. The marginal descriptive ratio is 0.25946 extra replica-seconds per additional on-time request in this window. This is not an economic price or a matched-budget comparison.

# Ablations and mechanism interpretation

![Figure 7  Target replica-time across all six arms. Bars show mean ± sample standard deviation.](figures/04_replica_cost.png)

Replacing the JointSLA router with shortest queue gives 51.99% failures and 112.84 target replica-seconds. JointSLA minus this arm is −2.10 percentage points, with interval [−4.84, +0.73] and raw exploratory p = 0.158844. The interval crosses zero, so a separate routing advantage is unsupported.

Reactive scaling with the Joint router gives 60.95% failures and 65.44 target replica-seconds. JointSLA minus this arm is −11.05 points, with interval [−13.73, −8.30] and raw exploratory p = 3.147870e−07. This is consistent with scaling/headroom contributing to the combined system’s advantage.

Rule replacement changes feedback and can change realized replica trajectories. We cannot partition the gain uniquely into routing, cold-start avoidance, availability or contention. No static-four or matched-replica-time comparator was registered.

A user-requested pause interrupted preparation of the first block’s Joint-scaler/shortest-queue arm after its preconditioning calls and before its burst. The idle interval was 5,498.868465 s, approximately 91.65 minutes. No benchmark requests were offered during the pause. Resume checks verified unchanged sources, process identity and two ready idle backends. All 180 trials remain in the analysis. The extra idle period affects one exploratory arm and is a possible host-temperature/time-order limitation. Trial preparation and wall-time summaries include it and must not be interpreted as algorithm runtime.

# Limitations reproducibility and conclusion

The evaluation uses one CPU model, synthetic inputs, one virtual Kubernetes node and one physical host. It does not measure a 6G data plane, physical GPU/VRAM, multi-model placement, accuracy or multi-host failures. Background activity remains. Thirty blocks are an initial repeated design, not independent physical deployments or a power certificate. The user pause affects one exploratory preparation interval. HPA retains native timescales.

## Preservation and reproducibility

evidence/Kubernetes_v2_complete_evidence.zip contains 1,480 selected raw, curated and frozen-source files. V2_SOURCE_SEAL.json records each SHA-256 and the archive hash. HISTORICAL_RESULTS_SEAL.json records 24,364 result-file hashes, sizes and timestamps. Every archive member was verified against source. Original results, prior reports and frozen policy sources retain their original locations. This is a local archival copy, not an off-device backup.

The package README gives offline verification and analysis commands. canonical_results.json supplies shared claims. Tables retain all 180 runs, tier counts, exact paired comparisons and cost analysis. Seven figures have PNG and vector PDF versions. The original protocol and main manifest are archived. Image availability is required for reconstruction; wall-clock measurements remain variable.

## Conclusion

The local prototype is operationally complete within its audited boundary. JointSLA significantly reduces SLA failures against the registered reactive, static and native HPA baselines, while using more target replica-seconds. It does not meet the less-than-15% failure goal. These findings support an empirical trade-off and reproducible prototype contribution without general resource-efficiency or first-in-literature novelty claims.

## Verified sources

[1] D. Crankshaw et al. InferLine: ML Prediction Pipeline Provisioning and Management for Tight Latency Objectives. arXiv:1812.01776v2, 2020. https://arxiv.org/abs/1812.01776v2

[2] F. Romero, Q. Li, N. J. Yadwadkar and C. Kozyrakis. INFaaS: Automated Model-less Inference Serving. USENIX ATC 2021, pp. 397–411. https://www.usenix.org/conference/atc21/presentation/romero

[3] A. Gujarati et al. Serving DNNs like Clockwork: Performance Predictability from the Bottom Up. USENIX OSDI 2020, pp. 443–462. https://www.usenix.org/conference/osdi20/presentation/gujarati

[4] Kubernetes. Horizontal Pod Autoscaling. Official documentation accessed 9 October 2026. https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/

[5] Kubernetes SIGs. Metrics Server v0.9.0 release. https://github.com/kubernetes-sigs/metrics-server/releases/tag/v0.9.0
