# GPU experiment intake for Bronze/Silver/Gold

This is the handoff plan for when a suitable GPU host or cluster is available.
No GPU run is claimed by the CPU dataset or by the old kind dry-run.

## Before a run

Record GPU model and memory, driver/runtime versions, node count, Kubernetes
version, accelerator sharing method (MIG, HAMi, or none), image digests,
model weights digest, CPU and RAM, and the per-tier SLO contract. Set a
resource budget and maximum allowed replica count before viewing outcomes.
Keep credentials and customer traffic outside the research repository.

## Minimum measurements

For each offered request: anonymous request ID, tier, arrival time, deadline,
admission/rejection, completion time, latency and selected replica. For each
pod: UID, node, GPU allocation, scale request, scheduling, start, weights
loaded, warm-up complete, Ready, drain and termination times. Sample queue
depth, arrival rate, GPU memory/utilization and CPU contention with timestamps
and missing-data flags. Log each candidate action, TTV/TTR/PostSLO forecast,
forecast version, gate decision, applied action and rollback observation.

Synchronize clocks. Preserve every offered request in the SLA denominator;
do not calculate latency for rejected requests. Separate actual readiness
from Kubernetes admission dry-run. Record resource use as pod-seconds and
GPU allocation-seconds, alongside per-tier failures.

## Experiment gate

Run fixed-floor, reactive and unchanged JointSLA baselines on paired workload
tapes before testing the new allocator. Use a development split for model and
parameter selection, then freeze the policy and evaluate on untouched test
blocks. Report per-tier paired effects, calibration, resource cost, failed
actions, and whether each tier contract was met. A live actuator would require
separate authorization, observed canary SLO, concurrency control and rollback
tests. The CPU counterfactual outputs must never be presented as GPU evidence.
