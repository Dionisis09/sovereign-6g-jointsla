# Benchmark runner optimization v2

Status: host runner changes implemented; all six preparation paths accepted.
The new 180-trial comparison is tracked separately. No end-to-end speedup
or comparative SLA result is claimed from this microbenchmark.

## Measured overhead

Twelve sequential read-only pod-list queries per method on the owned validation
cluster yielded median 63.12 ms for kubectl and
2.50 ms for a reused Kubernetes API client (25.2x faster
for this operation). These measurements include client startup/serialization and
are not randomized policy trials. Raw samples are in [api_timings.json](api_timings.json).

The initial v1 reactive/static full trials lasted 74.36 and 72.77 seconds;
preparation occupied approximately 43.45 and 41.75 seconds. The unchanged
35-second settling window, 10.7-second burst and 20-second follow-up account for
about 65.7 seconds plus final response time. Even eliminating every other overhead
would save only roughly 10-12%. The measured query speedup does not imply a
25x speedup of a real-time Kubernetes experiment. The original estimate remains
roughly 3.5-4 hours for 180 serial trials, with additional delays possible for
native HPA initialization and missing resource metrics.

## Changes and preservation

Repeated CLI calls for pod/readiness polling, deployment scaling and native HPA
creation/status use bounded Kubernetes API clients. A single gateway patch sets
its policy environment and replicas after the prior pod has drained, preserving
a fresh gateway process/controller state. Only the owned validation context and
namespace are used. Existing serving images/model, planner/router functions,
metrics frequency, initial two warm replicas, eight direct preconditioning calls
per backend, workload tapes, deadlines, 30 paired seeds and 35/20-second windows
remain unchanged. No concurrent competing inference bursts are introduced.

Preflight waits for complete resource metrics and matching current ready pod
UIDs at target=2. Transient endpoint propagation failures can delay preparation;
o burst request is retried or discarded for performance. These correctness gates
may consume time but avoid starting under an invalid initial state.

The v1 attempt stopped before its third burst on incomplete CPU telemetry. Its
two verified trials, failed preparation, frozen manifest and full source snapshot
remain in `prototype/.cache/kubernetes_comparison_v1/`, excluded from v2.
A failed subsequent preparation check is also retained. No selective replay or
pooling of different registered setup versions is permitted.

Further large wall-clock savings would require shorter settling/follow-up windows,
fewer repetitions/arms, or independent physical hosts. Those change the research
design and are not implemented here. Simulator fast-forward is inappropriate for
actual HTTP/model execution, asynchronous resource metrics and native HPA timing.

## Evidence

- Full test log: `.cache/kubernetes/benchmark-pytest-v2-final.log`.
- New preparation log: `.cache/kubernetes/benchmark-preflight-v2-final.log`.
- Main progress after acceptance: `prototype/.cache/kubernetes_comparison_v2/progress.json`.
- [Registered protocol](../../RESEARCH_EVALUATION_PROTOCOL.md).
- [Host runner](../../../benchmark/experiment.py).

Final preparation checks (s): static=41.86, reactive=42.39, hpa=56.84, joint=42.83, joint_sq=42.36, reactive_joint=41.87.
These are preparation acceptance measurements without competing bursts, not a
paired end-to-end speed experiment. Their values show that fixed settling and
native HPA readiness dominate; no significant overall speedup is demonstrated.
