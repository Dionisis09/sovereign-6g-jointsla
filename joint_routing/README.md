# Joint placement and queue-aware routing: frozen experimental design

This is a new mechanism experiment. Existing `dynamic_placement`,
`paper_evaluation` and verified results remain unchanged. The physical pipeline
is the inherited, unchanged CPU → GPU → CPU worker, with stages colocated.
No new workload, topology, SLA threshold, learning or hardware model is added.

## Comparators and identifiability

The existing SLA-aware baseline is already a work-conserving shared FIFO queue:
available replicas pull requests. It is not static or arbitrary request routing.
New policies use explicit per-replica queues via a facade around that same worker:

- SLA-aware+RR: unchanged `sla_aware` deployment function, round robin over
  currently eligible replicas sorted by ID.
- SLA-aware+ShortestQueue: the same deployment function, minimum waiting count
  plus one for an in-flight request, with replica-ID tie breaking.
- JointSLA: routing-aware slow deployment scoring and fast SLA/slack routing.
- JointSLA-no-queue: the same slow scoring but fast routing removes replica
  backlog, remaining busy work and queue-dependent variance multiplication.
- JointSLA-no-slack: the same slow scoring but fast routing ranks expected
  completion alone, without the variance/slack risk proxy.

Routing-only baselines share the deployment *function*, not identical resulting
placements: changed completion/queue feedback can change its actions. Explicit
queues differ from the central pull baseline. Comparisons cannot attribute all
differences exclusively to score weights. Ablations remove fast routing terms;
their state feedback may subsequently alter deployment.

## Observable routing estimates

Eligible means ready, not retiring, not awaiting migration, a feasible resident
reservation, and sufficient physical capacity to execute its service. An active
busy replica may receive queued work; a cold/migrating replica may not.
If none is eligible, requests wait in a pending service queue. They are not
dropped. On replica readiness or migration reallocation, waiting work is
redispatched in arrival order. In-flight work is never moved or interrupted.

For candidate i and request with current age a:

```
queue_wait = waiting_count_i × observed_mean_cycle_i + remaining_busy_estimate_i
resource_wait = CPU_work_ms × rho_CPU/(1-rho_CPU)
              + inference_ms × rho_GPU/(1-rho_GPU)
              + observable_GPU_waiters × inference_ms/GPU_units
completion_estimate = a + queue_wait + resource_wait + network
                    + nominal_compute + applicable_first_request_penalty
slack = deadline - completion_estimate
variance_proxy = observed_cycle_variance × (waiting_count + busy_indicator + 1)
risk_proxy = 1 if slack <= 0 else variance_proxy/(variance_proxy + slack²)
```

The utilization proxy uses previous-slot measured fractions, capped at the
existing 0.98 limit. Cycle mean/variance update from completed requests only,
excluding service queue waiting, using the existing EWMA alpha=0.5. Initial
variance uses nominal compute and the existing work jitter sigma. Migration
resets the source-node observation when the destination differs.

Choose lexicographically by risk proxy, then largest slack, then completion,
then replica ID. The variance/slack expression is Cantelli-inspired, but is
**not a calibrated probability**: estimated moments and dependent resource
waiting do not justify a probabilistic SLA guarantee. Without replica variance
differences this may have the same ordering as minimum predicted completion;
the no-slack ablation tests whether this term adds practical value.

The arriving request's pre-generated work factor is never inspected for scoring.
No future requests or burst flags enter the controller/router. Predictions are
proxies and can be wrong. Routing computation is measured in wall time, as is
existing controller time; neither is injected into simulated request latency.

## Slow deployment and formal coupling

At unchanged control intervals, tier/SVRS prioritization considers feasible
keep, scale-out, scale-in and migration actions with existing limits, cooldown,
capacity checks and lifecycle penalties. Candidate quality virtually dispatches
up to the first **20 currently waiting requests**, or one nominal probe if none
wait. Virtual queues are a copy; no future arrival is generated. Cold-start or
migration availability delay enters hypothetical target completion estimates.
This bounded greedy evaluation is an approximation, not a solver or oracle.

Write x[s,n,t] for allocated replica count (with eligible count distinguished
by lifecycle state), and r[q,n,t] for a request's current binary assignment.
The service-level r[s,n,t] is the fraction of dispatched requests assigned to
node n during the slot. Routing is permitted only where an eligible replica
exists. Each dispatched admitted request has sum_n r[q,n,t]=1; a temporarily
pending request has no assignment until eligibility returns. Redispatch removes
its previous waiting assignment before replacing it.

Conceptually minimize tier-weighted predicted SLA failure and normalized
end-to-end delay, plus migration, cold-start and resource costs, subject to
CPU/VRAM/bandwidth reservations, finite GPU execution, lifecycle, replica-count
and action-budget limits. The implementation approximates:

```
J = priority × mean(completion_estimate/deadline + risk_proxy)
  + 0.35 × per-service CPU/VRAM pool reservation fraction
  + 0.25 × lifecycle_overhead/(deadline × virtual_batch_size)
```

The risk and normalized-delay coefficients are fixed at one. Resource/lifecycle
weights reuse existing headroom/overhead parameters. No weights or criteria are
tuned on seeds 1–30. Resource accounting retains temporary double reservations
for migration, through the unchanged physical engine.

## Predeclared hypotheses and decision rules

Main tests compare JointSLA with SLA-aware, RR and ShortestQueue for failure,
request mean, p95 and p99: one Holm family of 12 two-sided paired Wilcoxon tests.
The existing statistical bootstrap, signed-rank, Holm and effect-size functions
are reused unchanged, with 10,000 seed bootstrap resamples. Eight ablation
comparisons form a separate exploratory Holm family and do not establish H1–H5.

- **H1:** versus SLA-aware, positive failure reduction with Holm p<0.05 and
  positive lower paired mean-difference CI.
- **H2:** the same rule for p95.
- **H3:** supported p99 reduction, or lower 95% relative-improvement CI >=−5%.
  The latter is a predeclared descriptive bootstrap noninferiority criterion,
  not a Wilcoxon noninferiority test.
- **H4:** H1 and H2 hold, while upper paired bootstrap bounds indicate average
  replica increase <=5% and VRAM residency increase <=2 percentage points.
  This supports benefit at comparable measured resource use, not causal proof
  of resource-independent efficiency. All lifecycle/actions remain disclosed.
- **H5:** mean controller decision time <=10 ms and routing-attempt p95 <=1 ms
  in this instrumented local run. The budget is 10% of the existing 100-ms
  control slot, plus a 1-ms request-routing budget. This is an operational
  screen, not real-hardware profiling or a universal production claim.

For H5 the new instrumented total includes control-start snapshot construction
as well as policy computation/action application; snapshot cost is not hidden
outside the timer. The legacy compute/action-only timer remains separately
available for comparison with historical baselines, whose snapshot times were
not measured. These different timing scopes must not be conflated.

Thresholds are fixed *before* the main runs. Frozen protocol stores them, engine
and new-source hashes and preserved baseline-artifact hashes. Results are not
rescued by parameter changes if any hypothesis fails.

## Outputs and reproducibility

Run `python run_joint_routing.py --seeds 1:30`. The verified 120 baseline runs
are reused, and five new policies run on the same 30 workloads: 150 newly
simulated runs, 270 rows in the combined comparison. Use `--reuse-results` for
analysis without simulation or `--force` to rerun the new policies only.
Existing baselines and paper results are never overwritten.

Outputs go to `results/joint_routing_30seeds`: raw/summarized metrics, main and
ablation tests, every paired difference, request outcomes, complete scored
routing candidates, routing attempts, action/lifecycle/capacity evidence,
diagnostic resource ratios, hypothesis evaluation, report and eight figures
in PNG 300 dpi / SVG / PDF. Routing costs include candidate construction,
ranking and two observational counterfactual selections, exclude JSON/audit
serialization, and disclose both per-attempt and per-offered-request costs.
Replica request imbalance includes all allocated instances; lifetimes differ,
so its CV is descriptive, not a fair-load optimality measure.
