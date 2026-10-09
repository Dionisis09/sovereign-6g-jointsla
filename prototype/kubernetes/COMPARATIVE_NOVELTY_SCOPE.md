# Scope of JointSLA's contribution and prior-work checks

Verified primary sources, checked 8 October 2026. This is a focused positioning
note, not an exhaustive systematic review or a novelty certificate.

| Prior work | Established mechanism | Implication for JointSLA |
|---|---|---|
| [InferLine, Crankshaw et al., arXiv v2 (2020)](https://arxiv.org/abs/1812.01776v2) | A low-frequency provisioning planner and high-frequency tuner manage prediction pipeline stages toward end-to-end tail-latency objectives. Profiling, simulation and network calculus guide replication, batching and heterogeneous hardware. | Latency-aware provisioning and autoscaling of inference pipelines are established. JointSLA cannot claim their invention. Its lightweight observed queue/cycle/slack rule needs separate justification and measured trade-offs. |
| [INFaaS, Romero et al., USENIX ATC 2021](https://www.usenix.org/conference/atc21/presentation/romero) | Per-query model/hardware/optimization choice is combined with VM-level and model-level autoscaling, meeting performance/accuracy objectives across model variants. | Joint selection and scaling are established. The present single fixed CPU model does not demonstrate INFaaS-style heterogeneity or accuracy/cost optimization. |
| [Clockwork, Gujarati et al., USENIX OSDI 2020](https://www.usenix.org/conference/osdi20/presentation/gujarati) | Predictable inference execution is used to construct a distributed serving system with request-level latency objectives and performance isolation. | Deadline-aware inference scheduling and measured execution behavior are established. JointSLA's observed cycle moments are empirical proxies, not Clockwork's predictability guarantees. |

The current runtime imports frozen `required_warm` and `choose` functions. Its
router estimates completion from queue, busy state, observed cycle mean/variance
and deadline slack, then ranks by a variance/slack risk proxy. The warm-headroom
scaler uses observed arrivals, queued work, cycle time, a cold-start allowance and
Gold floor to request replicas. Real HTTP inference and Kubernetes scale actions
exercise those rules. This combination is an implementation-specific contribution
candidate, not a demonstrated first in the literature.

The registered experiment asks whether that unchanged combination lowers the
all-offered SLA failure rate at a disclosed resource cost, and whether substituting
one scaling/routing rule changes the result. Positive results would support this
local empirical claim, not establish general algorithmic novelty. Negative or
inconclusive results remain part of the contribution: an independently verified,
reproducible comparison with explicit failure categories and no concealed drops.

The CPU Kubernetes adapter sets network/resource/penalty estimates to zero; actual
HTTP overhead still enters measured outcomes. It uses a conservative full cycle
for busy residual work. Thus it is not a calibrated breach probability, a formal
SLA guarantee, a five-site network placement evaluation, a production GPU scheduler
or a real measurement of sovereignty constraints. The existing multi-component
simulator experiments must keep their separate evidence scope.

For a paper, present the exact rule, assumptions, ablations and cost/failure
trade-offs as the proposed contribution. An exhaustive related-work review and
broader deployment/workload validation are still required before claiming a novel
or generally superior orchestration method. Previously unsupported citations and
percentages stay excluded. External benchmark percentages are not compared to
our local SLA rates because workloads and denominators differ.

Static-2 is an initial-capacity baseline, not a matched replica-time budget control.
No static-4 sensitivity arm is included. Report replica-seconds explicitly, and
do not claim that an advantage over Static-2 persists at equal realized capacity.
Likewise, the main short burst alone cannot isolate cold-start prevention from
more available compute; the readiness traces and rule-substitution arms provide
limited mechanism evidence, not a fully controlled physical-capacity intervention.
