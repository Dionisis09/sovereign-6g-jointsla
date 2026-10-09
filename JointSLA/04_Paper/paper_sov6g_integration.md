# JointSLA in an intent-driven orchestration context

## A SOVEREIGN-6G motivation

Future digital services require coordinated access to communication, computation and acceleration resources across a telco cloud continuum. The SOVEREIGN-6G project overview identifies a Digital Service Orchestrator (DSO) responsible for SLA assurance across heterogeneous resources [1]. This context motivates studying how a downstream orchestration function should coordinate replica deployment, scaling and request routing. Our work characterizes that function through reproducible simulation with selected execution costs grounded in measured hardware. The architectural mapping proposed here does not establish integration with the SOVEREIGN platform or claim to reproduce its complete architecture.

## B Intent-driven service request

A business-facing request might ask an operator to provide low-latency AI video analytics near users with high service priority. Such a statement specifies a desired outcome rather than a replica configuration. An intent-driven orchestration context therefore requires an upstream function to resolve service identity, priority, latency requirements and resource constraints before scheduling. This example is illustrative: the evaluated vision-model pipelines are resource proxies, not an implemented video analytics application. Intent interpretation is neither an implemented capability nor a novelty claim of this study.

## C Translation into technical requirements

The translation boundary separates business semantics from machine-actionable requirements. TM Forum's TMF921 API provides an upstream reference for expressing and managing intents [2]; no TMF921 parser, compliant payload or ontology implementation is introduced here. Existing simulator records instead expose `service_id`, `tier`, `deadline_ms`, `priority`, `cpu_cores`, `gpu_vram_gb` and `bandwidth_mbps`. These fields can represent a subset of intent-derived requirements once values have been validated externally. Current inputs are generated or loaded from frozen workload records, rather than translated from business statements.

Other concepts have narrower representations. The ingress node and network latency matrix support locality-dependent cost estimates, but they do not enforce geographical affinity or a separate network-latency SLA. Replica ceilings are global configuration values. Hardware classes are derived from service identifiers and mapped to measured model profiles, rather than supplied as arbitrary service-model contracts. Explicit availability targets, data residency, tenant isolation, allowed-node lists and device-feature compatibility are not represented. A GPU inference stage exists in every evaluated pipeline; this is not general capability negotiation.

## D DSO integration point

JointSLA can be positioned as a decision function within an intent-driven Digital Service Orchestrator, consuming intent-derived SLA and resource constraints. The proposed integration point lies after requirement translation and before resource-domain actuation. A conceptual adapter would map validated requirements and observed state to existing service/configuration records and controller snapshots. The repository provides an internal control interface returning action proposals, together with a separate eligible-replica routing function. It does not provide that adapter, external orchestration APIs or production deployment drivers. Common initial placements remain preserved in the frozen held-out evaluation; subsequent placement changes arise through accepted replica creation and migration.

## E Role of JointSLA

The system under study couples deployment decisions with queue-aware request selection. Feasible scale-out, scale-in and migration proposals are subject to resource reservations, cooldown, replica limits and action budgets. Routing evaluates eligible replicas using observable queues, execution estimates and remaining deadline slack. JointSLA-v2 adds causal warm-capacity retention and bounded Gold repair while inheriting v1 routing. Neither policy reads future traffic or scheduled burst information.

The contribution is an operating-envelope characterization, not a claim that coupling universally improves service quality. Completed evidence includes paired synthetic evaluation, scalability, controller optimization, an optimization comparator, hardware profiling, pressure variation, decomposition and burst recovery analysis. These studies have distinct scopes. The final mitigation comparison uses frozen held-out seeds 31–60 at 1x and 2x load. Consolidation can reduce resource occupancy and improve latency under contention, yet hardware-grounded lower-pressure conditions expose SLA penalties associated with limited warm capacity and cold recovery. The decomposition informs these interactions without establishing a unique cause. V2 improves Gold breaches relative to v1, but its failed resource and latency criteria retain the underlying trade-off.

## F Monitoring and assurance feedback

Observed request latency, service and node queue delay, lifecycle overhead, utilization and SLA breaches support feedback and evaluation. Controller snapshots expose current or completed observations, while post-run exports support paired statistical analysis. This distinction matters: simulator telemetry and breach detection are implemented, whereas binding these observations to a live DSO assurance service remains conceptual. Warm replica floors do not constitute availability guarantees, and a risk proxy is not a calibrated probability of meeting a deadline. Feedback cannot remove infeasibility caused by finite resources or cold readiness exceeding latency headroom.

## G Scope and contribution boundary

The paper contributes a causal coupled orchestration framework as the system under study; characterization across scale and offered load; hardware-grounded analysis of VRAM, warm-capacity and recovery-related reversals; and held-out assessment of a bounded Gold-protection mitigation. The overall v2 success criterion is not met, and negative results remain part of the characterization. The study implements neither full Intent Management nor a complete SOVEREIGN DSO, TMF921 compliance or a real 6G deployment. Intent is an architectural input layer; the research begins with structured technical constraints. No new algorithmic novelty is claimed through this mapping, and no further experiment or tuning accompanies it.

## References and evidence

[1] [Iquadrat SOVEREIGN-6G project overview](https://www.iquadrat.com/rd/sovereign-6g/), accessed 7 October 2026. Supports the DSO and heterogeneous continuum motivation, not the specific proposed interface wiring.

[2] [TM Forum Intent Management API overview](https://www.tmforum.org/open-digital-architecture/open-apis/intent-management-api-TMF921/v4.0), accessed 7 October 2026. Provides upstream API context, not evidence of repository conformance.

Repository evidence and exact field mappings: [SOVEREIGN intent mapping](SOVEREIGN_INTENT_MAPPING.md). Diagram source: [architecture Mermaid](figures/sov6g_intent_jointsla_architecture.mmd). Scientific conclusions: [frozen held-out report](../results/jointsla_v2_heldout/report.md); numerical results and hypothesis outcomes are unchanged.
