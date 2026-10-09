# Purpose

Position the completed JointSLA study as a **hardware-grounded systems characterization of coupled placement, scaling and queue-aware request routing for heterogeneous edge-AI services**. Intent is the upstream source of requirements, not the contribution under evaluation. This document proposes conceptual architectural integration; it implements no new interface or simulator feature.

Research question: **Under which operating conditions does coupled placement, scaling, and queue-aware request routing improve edge-AI performance, and when do resource consolidation, limited warm capacity, and cold-start recovery reverse those benefits?**

The experimental and algorithmic phase is closed. JointSLA-v1, JointSLA-v2, SLA-aware, parameters, historical reports, plots and verified results remain frozen.

# What SOVEREIGN-6G Provides Conceptually

The [SOVEREIGN-6G project partner overview](https://www.iquadrat.com/rd/sovereign-6g/) describes a Digital Service Orchestrator (DSO) for SLA assurance across heterogeneous compute, network and GPU resources in a telco cloud continuum. This provides the architectural motivation for the mapping.

The proposed chain is business/service intent → Intent Management Function → structured technical requirements → DSO → orchestration decisions → resource execution → monitoring feedback. This chain is a **proposed conceptual placement of this study**, not a verified implementation diagram of the SOVEREIGN platform. The public overview does not establish the specific Intent Management Function wiring or a production TMF921 binding assumed in the example.

[TM Forum's Intent Management API overview](https://www.tmforum.org/open-digital-architecture/open-apis/intent-management-api-TMF921/v4.0) concerns intent expression, reporting and negotiation. Its role here is a conceptual upstream interface. No TMF921 schema, endpoint, ontology validator or conformance claim is supplied by this work.

# Intent-to-Orchestration Boundary

The research boundary begins **after** an upstream function has translated an intent into technical SLA and resource requirements. In the repository those requirements are generated or loaded as immutable workload records and configuration; they are not produced by an intent translator.

An eventual DSO adapter would bind validated requirements to existing service/configuration objects, construct telemetry snapshots, invoke the existing decisions and dispatch accepted actions. That adapter, business-intent interpretation and external execution integration are conceptual only. The research implementation consists of the simulator and decision functions behind this boundary.

# Existing JointSLA Inputs

The following source locations establish the mapping:

- [Service, Request and Workload records](../dynamic_placement/workload.py): service metadata, resource reservations, generated arrivals and node GPU execution units.
- [Configuration](../dynamic_placement/config.py): replica ceiling, lifecycle costs, control budget, cooldown and execution timings.
- [Node and topology records](../placement_experiment/data_generation.py): CPU/GPU/bandwidth capacities and pairwise latency matrix.
- [Base telemetry and action enforcement](../dynamic_placement/simulator.py): `snapshot`, `apply`, resource reservations and request outcomes.
- [SLA-aware decisions and capacity feasibility](../dynamic_placement/policies.py): `risk_score`, `_fits`, `sla_aware` and `Action`.
- [JointSLA-v1 controller](../joint_routing/controller.py): `joint_actions` and `deployment_quality`.
- [Routing candidates and snapshots](../joint_routing/simulator.py) and [routing selection](../joint_routing/router.py): `nominal`, `candidates`, `snapshot`, `estimate` and `choose`.
- [Hardware calibration](../hardware_grounded/calibration.py): `model_class`, `CLASS_MODELS`, `service_config` and `configs_for_services`.
- [JointSLA-v2 guard and repair](../joint_sla_v2/policy.py) and [observed history](../joint_sla_v2/simulator.py): `required_warm`, `headroom_rows`, `actions` and `recent_rates`.
- [Held-out frozen configuration](../results/jointsla_v2_heldout/frozen_config.json) and [verified report](../results/jointsla_v2_heldout/report.md): scope and outcome evidence.

Service requirements, platform inventory, telemetry and controller settings are distinct inputs. Only the first category corresponds directly to service requirements; describing inventory or control constants as translated business intent would be inaccurate.

# Mapping Intent-Derived Requirements to Simulator Fields

| Existing field or mechanism | Intent-derived concept or architectural role | Actual meaning and boundary |
|---|---|---|
| `Service.service_id` | Service identity | Integer identity in the workload; no business catalogue identity resolver. |
| `Service.tier` | SLA/service priority tier | Gold, Silver or Bronze. Current generator assigns by service ID modulo 3; no intent classification. |
| `Service.deadline_ms` | End-to-end latency requirement | Physical millisecond deadline. Generated base requirement is multiplied by tier factors 1, 1.8 or 3. Request breach is `latency_ms > deadline_ms`. |
| `Service.priority` | Relative orchestration priority | Integer weights 3, 2, 1 for Gold, Silver, Bronze, used in risk/ranking and deployment scoring. Not a guarantee of preemptive priority scheduling. |
| `Service.cpu_cores` | CPU resource requirement | Per-replica reservation and execution resource demand in simulated cores. |
| `Service.gpu_vram_gb` | GPU memory requirement | Per-replica VRAM reservation; hardware-grounded values are measured peak allocated memory converted to GiB. The legacy field suffix `gb` does not change those documented units. |
| `Service.bandwidth_mbps` | Bandwidth resource requirement | Per-replica bandwidth reservation in Mbps. It is not an independently guaranteed network SLA. |
| `Service.ingress` | User-side attachment/locality input | Node index from which network delay is estimated. No region, distance, tenant or explicit edge-preference policy. |
| `Service.payload_mbit` | Request transfer requirement | Megabits per request, used with node bandwidth in transmission estimates. |
| `Service.base_rate_rps` | Workload demand descriptor | Generated mean rate in requests/s. Actual offered traffic is exogenous; controllers use observed rate telemetry, not future arrival tapes. |
| `model_class(service_id)`, `CLASS_MODELS` | Service/model resource class | Derived mapping LIGHT/LIGHT/MEDIUM/MEDIUM/HEAVY by ID modulo 5 to MobileNetV3, ResNet-50 and ViT-B/16 profiles. Not a `Service.model_class` field or a submitted model identifier. |
| Per-service configuration: `preprocess_ms`, `inference_ms`, `postprocess_ms`, `cold_start_slots` | Execution and readiness profile | Hardware-derived class timing parameters. Input upload is included in preprocessing. These describe execution costs, not business SLA targets. |
| `EdgeServer.cpu_capacity`, `gpu_capacity`, `bandwidth_capacity_mbps`; `Workload.gpu_units` | Platform resource inventory | Finite CPU, memory and bandwidth capacities plus GPU execution concurrency units. In the hardware-grounded simulator `gpu_capacity` is the VRAM reservation limit; it is distinct from compute concurrency. |
| `Scenario.network_latency_ms`; snapshot `network_ms` | Topology/network cost | Pairwise propagation latency in ms. **Separate per-service maximum network latency: not currently represented.** End-to-end deadlines include network effects. |
| `Config.max_replicas` | Replica ceiling | Global controller ceiling, frozen at 3 in the held-out study. **Intent-specific per-service replica limits: not currently represented.** |
| `Parameters.gold_floor`, `required_warm` | Bounded warm capacity protection | Frozen Gold floor and causal retention requirement in v2. **Availability percentage, fault tolerance and anti-affinity: not currently represented.** A warm floor is not an availability SLA. |
| `_fits`, `Simulator.apply`, candidate `capacity_feasible` | Resource feasibility | Reservation/capacity checks and routing-candidate resource checks. **Explicit allowed-node lists, model/device compatibility metadata, region constraints and affinity: not currently represented.** |
| Snapshot `rates`, `latency_ms`, `queue_lengths`, `oldest_wait_ms`, `utilization`, `reserved`, `replicas` | Assurance/controller telemetry | Current/past observed state; not intent fields. |
| Candidate `queue_length`, `remaining_busy_ms`, `cycle_ms`, `cycle_variance_ms2`, `network_ms`, `resource_wait_ms`, `available_in_ms` | Queue-aware decision context | Observed/nominal estimates for replica choice and deployment evaluation. Risk is a proxy, not a calibrated SLA violation probability. |
| `Config.action_budget`, `cooldown_slots`, lifecycle penalties | Orchestration operating constraints | Global implementation settings; no upstream intent negotiation of these values. |
| No corresponding field | Accuracy target, privacy/data residency, security, energy/carbon budget, tenant isolation, multi-operator sovereignty, cost budget, service availability target, percentile-specific SLO | **Not currently represented.** Reported p95/p99 latency and tier breach rates are evaluation metrics, not independently configured intent targets. |
| No corresponding field | GPU-required boolean or device-feature contract | **Not currently represented.** The evaluated pipeline always includes GPU inference; reservations and GPU units provide resource feasibility, not a general CPU/GPU capability negotiation mechanism. |

# Digital Service Orchestrator Integration Point

Proposed integration point: **inside or underneath the DSO, between consumption of already-translated service requirements/telemetry and resource-domain actuation**.

The existing control seam is `(config, snapshot) → list[Action]`; routing separately uses `choose(candidates, deadline, policy, rr_counter, age_ms) → replica_id or None`. V2 adds causal warm-capacity protection around the v1 controller and inherits its routing. No new callable, REST API, DSO adapter or resource driver is introduced by this documentation.

For the frozen held-out runs, common initial placements are preserved. JointSLA changes subsequent replica deployment through scale-out, scale-in and migration; it does not create a new intent-aware initial placement algorithm.

# JointSLA Decision Outputs

- Placement of additional replicas: `Action(kind="scale_up", service_id, target)`.
- Scale-in: `Action(kind="scale_down", service_id, replica_id)`.
- Migration/reallocation: `Action(kind="migrate", service_id, target, replica_id)` where proposed and accepted.
- Request routing: an eligible replica ID chosen through the existing routing function; routing is not a fourth `Action.kind`.
- Keep/no action: empty proposal list or retention of current deployment, subject to v2 filtering and bounded repair.

The simulator validates proposals sequentially, including competing reservations, cooldown, minimum surviving replicas and the replica ceiling. Accepted decisions operate on simulated resources, not production edge infrastructure.

# Monitoring and SLA Assurance Feedback

The simulator records request end-to-end latency, service/node queue delay, compute, network, lifecycle penalty and `breach`. Snapshot telemetry feeds subsequent decisions; completed observations support causal estimates. V2 derives recent arrival counts from completed-slot telemetry and never reads future burst masks or future work factors.

Resource/lifecycle/controller logs and per-tier metrics support offline assurance analysis. A future monitoring-to-DSO feedback adapter is conceptual; existing breach detection and telemetry are not a production SLA assurance service. There is no promise that a feedback decision can meet a deadline when resources or cold readiness are infeasible.

# What Is Implemented

Seeded workloads; finite simulated CPU/GPU/VRAM/network resources; CPU-pre → GPU-inference → CPU-post pipelines; replica lifecycle costs; SLA-aware/v1/v2 decisions; causal queue-aware routing; telemetry and verified request outcomes. Isolated timings and memory profiles ground selected model execution costs in measured hardware. Node topology, contention, traffic and migrations remain simulated.

The completed evidence chain includes synthetic paired evaluation, scale 5/20 → 10/40 → 20/80, controller optimization, the MJO comparator, model profiling, hardware-grounded negative validation, a 0.5x–2x pressure sweep, D0–D7 decomposition, burst analysis and frozen v2 held-out evaluation. These are distinct studies with their existing scopes. In particular, the final held-out comparison uses seeds 31–60 at 1x and 2x on 10 nodes/40 services; the wider sweep is not an additional held-out v2 experiment.

# What Is Conceptual Only

Business/B2B user intent; upstream Intent Management Function and TMF921 interface; translation/validation of requirements; full DSO; external resource actuation; live monitoring-to-DSO binding; cloud/edge federation. The proposed architectural diagram labels those contextual components separately from the implemented research simulator.

## Example intent walkthrough

Business intent: “Provide low-latency AI video analytics at the edge with high service priority.”

| Step | Proposed interpretation | Repository boundary |
|---|---|---|
| Intent | Desired user-facing video analytics outcome | Conceptual only; no natural-language parser. |
| Structured SLA | A service identity, Gold tier, explicit deadline in ms and relative priority | Corresponding fields exist; upstream must provide validated values. No new numeric SLA is selected here. |
| Resource profile | CPU cores, GPU memory in GiB and bandwidth in Mbps; inference profile | Existing reservations and class profiles provide proxies. Video analytics is illustrative; the measured workloads are vision-model pipelines, not a deployed video analytics service. |
| Locality/compatibility | Ingress attachment and nodes with sufficient resources | Ingress and feasibility exist. Explicit edge-preference/allowed-node/device-compatibility constraints are not currently represented. |
| DSO decision | Pass existing requirements plus observed queues, readiness and capacity to JointSLA | Candidate integration point only. |
| Deployment/routing | Choose accepted replica actions and route to eligible replicas | Implemented in the simulator. |
| Assurance | Observe request deadline breaches and queue/resource state, then supply feedback | Simulator telemetry exists; production intent reporting/DSO feedback integration is conceptual. |

Thus intent → structured SLA → JointSLA requirements/telemetry → replica decisions → request routing → observed SLA → feedback. This walkthrough is not a TMF921 message schema and introduces no pseudo-JSON or executable adapter.

# What Is Outside Scope

Full TM Forum Intent Management, TMF921 parsing/conformance, ontology validation, intent conflict resolution, business negotiation, natural-language translation, real 6G integration, production SOVEREIGN APIs, Kubernetes/OpenNebula deployment and a complete SOVEREIGN platform. No new scientific experiment, tuning, plot regeneration or algorithmic version belongs to this integration task.

# Safe Paper Claims

> JointSLA can be positioned as a decision function within an intent-driven Digital Service Orchestrator, consuming intent-derived SLA and resource constraints.

This is architectural positioning, not evidence of deployed integration. The paper contributions are bounded as follows:

1. A causal coupled placement/scaling/routing framework used as the system under study.
2. Operating-envelope characterization across scale and offered load.
3. Hardware-grounded identification of performance reversals associated with VRAM, warm capacity and cold recovery, with decomposition that does not prove a unique cause.
4. A frozen held-out mitigation experiment in which Gold protection improves priority traffic **relative to v1** but does not eliminate the resource-performance trade-off.

Coupled orchestration is regime-dependent. Consolidation can offer resource and latency benefits under contention while lower-pressure hardware-grounded conditions expose SLA penalties from limited warm capacity and recovery costs. These interpretations must remain tied to their existing comparisons and uncertainty.

V2 passes H1/H2/H5/H6 and fails H3/H4. At 1x, its aggregate breach rate remains higher than SLA-aware; the Gold baseline comparison is not established as equivalence. At 2x, its latency advantage over v1 is lost. Intent translation is not claimed as novelty; literature differentiation remains a separate scholarly assessment.

# Claims to Avoid

“JointSLA is a universally superior scheduler”; “fully integrated with SOVEREIGN-6G”; “implements TMF921”; “production SOVEREIGN component”; “real 6G deployment”; “implements intent translation”; “guarantees Gold availability/deadlines”; “enforces geographical/device compatibility”; “the complete DSO is implemented”; “the decomposition proves a unique cause”; or “v2 removes the SLA/resource trade-off”. None is supported by the repository evidence used here.
