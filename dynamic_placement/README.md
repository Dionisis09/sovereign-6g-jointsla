# Dynamic edge service placement

The additional 8/9/10-node runs and the empirical capacity knee are documented
in [CAPACITY_SWEEP.md](CAPACITY_SWEEP.md). Run
`python -m dynamic_placement.capacity_sweep`; exports are in
`results/capacity_sweep` and the master summary gains three capacity rows.

The three follow-up scenarios (predictive prewarming, six/seven-node capacity,
and Bronze admission control) are documented in [SCENARIOS.md](SCENARIOS.md).
Run `python -m dynamic_placement.scenarios`; their full exports are in
`results/dynamic_scenarios`, and the original `summary.csv` is extended with
the new rows while preserving its original summary and figures.

A small synthetic experiment with **5 heterogeneous edge nodes, 20 AI services,
100 decision slots, and 30 paired Monte Carlo seeds**. A native slot controller
runs over SimPy request events. This extends the static experiment without
changing its code or results.

## Run

From the repository root, using Python 3.12 or newer:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m dynamic_placement.runner
```

For another output directory or consecutive seed range:

```powershell
& .\.venv\Scripts\python.exe -m dynamic_placement.runner --config dynamic_placement/config.json --trials 30 --seed 100 --output results/dynamic-reproduction
```

Tests require the optional `pytest==9.1.1` dependency:

```powershell
& .\.venv\Scripts\python.exe -m pip install pytest==9.1.1
& .\.venv\Scripts\python.exe -m pytest -q
```

## Model and units

Each default slot is **0.1 seconds**: 100 slots observe 10 seconds of arrivals.
Discrete orchestration does not quantize request delay to 100 ms: SimPy executes
requests continuously within each slot. Decisions at the start of a slot see
previous-slot observations and current queue state. No controller sees the
future traffic tape or scheduled burst flags.

Topology and service demands reuse the seeded static generator, with explicit
unit transformations in `workload.py`. Nodes have 9–12 CPU cores, 20–30 GB GPU
VRAM, 2 or 3 GPU compute units, and 280–420 Mbps bandwidth. Pairwise network
delay is symmetric, 4–25 ms off-diagonal and zero for local ingress. CPU and
GPU capacities remain distinct; VRAM residency does not mean the GPU is busy.

Each replica reserves 0.8–2 CPU cores, 2–7 GB VRAM, and its service's mean
payload bandwidth. Every reservation checks all three limits. Physical GPU
compute units and a serialized shared node link enforce instantaneous capacity
through queues. CPU uses integer 0.1-millicore tokens, rounded down from the
declared demand/capacity, to avoid floating-point resource-release stalls.

A service has three colocated sequential components:

1. CPU preprocessing: 2 ms, full reserved CPU share.
2. GPU inference: 10 ms, one GPU compute unit and 25% of its CPU share.
3. CPU postprocessing: 2 ms, full CPU share.

One replica handles one request at a time through its complete network/compute
pipeline. Its worker pulls from the service's FIFO queue. Replicas share finite
node GPU, CPU and link resources. Network delay includes the pairwise delay
and payload serialization; waiting for the link belongs to node queue delay.
Request work has seeded mean-one lognormal jitter (sigma 0.1).

The exact recorded decomposition is:

`end-to-end = service queue + node resource queues + network + compute + lifecycle penalty`.

This is an explicit queue model, **not an M/M/1 approximation**: compound arrivals,
multiple GPU units and staged compute violate M/M/1 assumptions. CPU/GPU queue
delays and finite backlog remain valid when incoming demand exceeds capacity.

Default base rates are 8–32 requests/s per service and payloads 0.05–0.25 Mbit.
For each slot, rate = base rate × mean-one lognormal noise × burst multiplier.
Cluster count is Poisson(rate × slot duration / mean batch size); each cluster
has a geometric request count of mean 2 and a uniform arrival time within the
slot. Requests in a cluster arrive together, giving a compound Poisson process.
Each service receives 3× periodic bursts starting near slots 20, 50 and 80,
with seeded phase 0–4 and duration 5–10 slots. No fitted external trace is used.

Service ID cycles Gold/Silver/Bronze. Their priority weights are 3/2/1 and their
deadlines are the generator's 25–65 ms multiplied by 1/1.8/3, respectively.
All policies know the same service metadata. Tier labels change orchestration
priority only in the proposed policy; request queues remain FIFO for everyone.

## Policies

All policies start with the **same greedy feasible placement using declared
mean demands**, one warm replica per admitted service. This isolates dynamic
decisions from differences in initial admission or placement.

| Policy | Decision rule |
|---|---|
| Static | Retain the initial placement and replica counts. |
| Reactive | If a replica's node CPU **or** GPU busy utilization exceeded 80% in the previous slot, attempt a local scale-out. If both were below 20%, remove an idle surplus replica with an empty service queue. |
| Periodic | Every 10 slots, greedily migrate a replica from a node above 80% CPU/GPU busy utilization to a feasible node below 50%. It does not add replicas. |
| SLA-aware | Rank services using SVRS; consider feasible scale-out and migration targets using latency, CPU/GPU pressure, reservation headroom and lifecycle overhead. Scale in idle surplus replicas when pressure falls. |

Common limits: at most three replicas per service, two proposed actions per
slot, and a three-slot cooldown per service. The engine validates actions
sequentially; conflicting reservations are rejected and counted. Scale-down
keeps at least one replica, discards no requests, and only retires idle replicas.

New replicas reserve capacity immediately but cannot serve during a one-slot
cold start. Their first request pays another 5 ms penalty. A migration reserves
the target while holding the source reservation, finishes an in-flight source
request, releases source capacity, and makes the replica unavailable for one
slot. Its first target request pays 10 ms. Other replicas continue serving and
queued requests wait. Lifecycle delays thus enter latency through queueing and
the explicit first-request penalty. Scheduled readiness times are logged even
if the experiment drains before a newly started lifecycle period ends.

### Proposed heuristic

Let `c` be the number of ready replicas, `Q` the service queue length, and `C`
the nominal 14 ms compute pipeline time. Define:

```text
predicted_delay = max(recent mean completed latency, oldest queue age + C)
SVRS = tier_weight × (predicted_delay + Q × C / max(1,c)) / deadline
```

Services are ranked by decreasing SVRS, then tier priority and observed EWMA
arrival rate. The EWMA uses alpha 0.5. For each feasible target/action:

```text
rho = min(0.98, max(target CPU/GPU busy fraction, EWMA_rate × C / projected_replica_count))
estimated_delay = network + C/(1-rho) + Q × C/projected_replica_count
cost = estimated_delay/deadline
     + 0.35 × mean(target busy pressure, projected CPU/VRAM reservation fraction)
     + 0.25 × lifecycle_overhead/deadline
```

The `C/(1-rho)` term is a bounded **controller proxy**, not the simulator's
latency calculation or an assertion that traffic is M/M/1. The cap prevents
infinite ranking costs. Scale-out increases the projected replica count;
migration keeps it fixed and must reduce the source score on a host above
80% utilization. Target feasibility uses CPU, VRAM and bandwidth together.
Lifecycle overhead includes downtime and the first-request penalty. Scale-out
is considered when normalized observed risk is at least 0.8 or estimated
per-replica work demand exceeds 80%. Ties are deterministic. These simple
weights and thresholds are fixed before the 30-seed run.

This heuristic can detect an individual service queue before host utilization
reaches 80%. It can also consume more replica seconds and VRAM than migration
alone; the exported cost metrics make that tradeoff visible. It is not a DRL
implementation or a guarantee of improvement.

## Metrics and artifacts

Arrivals stop at slot 100, but all admitted requests **drain to completion**
with the final placements. No further policy decisions occur during draining.
Late completions remain in their original arrival cohorts, so the last slots
do not hide requests waiting beyond the measurement horizon.

- `runs.csv`: one row per seed/policy; time-averaged slot latency, request-weighted latency, service/node
  queue delay, SLA breach percentage, per-tier breaches, actions/migrations,
  replica seconds, VRAM GB-seconds, utilization and offered overload.
- `summary.csv`: mean, sample SD (`ddof=1`) and count for every metric.
- `results_table.md`: concise mean ± SD comparison.
- `slot_trajectories.csv`: 12,000 policy/seed/slot rows, including observed
  arrivals, backlog, decision time and retrospective latency/SLA cohorts.
- `node_trajectories.csv`: 60,000 policy/seed/node/slot rows; CPU/GPU/link busy
  utilization, CPU/VRAM residency and nominal offered-load ratios.
- `request_outcomes.csv.gz`: every offered request, its deadline, timestamps,
  exact delay components and breach outcome.
- `traffic.csv`, `inputs/seed_*.json.gz`: full rates, burst flags, arrivals,
  request work, topology, services and common initial placement.
- `actions.csv`, `reservation_events.csv`, `lifecycle_events.csv`: audit trail.
- `paired_differences.csv`: proposed-minus-baseline mean and sample SD across
  paired seeds; descriptive differences, not a significance claim.
- `config.json`, `protocol.json`, `environment.json`, `verification.json`:
  parameters, input/source hashes, pinned environment and independent checks.
- Three figures, each PNG and SVG: latency through bursts, cumulative SLA
  breaches, and GPU compute utilization by node.

SLA breach percentage uses **all offered requests**; admission failures count
as breaches and are separately disclosed. Mean latency includes completed
requests only. No latency is invented for admission failures. The explicitly
time-averaged metric gives each nonempty arrival slot equal weight; its number
of observed slots is also saved. Slot plots take
an equal-seed mean of each slot's request mean, whereas the main latency metric
weights every completed request within its seed equally. Cumulative breaches
sum request counts, rather than averaging slot percentages.

Actual CPU/GPU/link utilization integrates busy resource time within each slot
and stays in [0,1]. `*_offered_ratio` is nominal incoming work divided by node
capacity, distributed evenly over the service's allocated replicas at the end
of the slot (including temporarily inactive replicas); it may exceed one.
It is a pressure diagnostic, not an instantaneous allocation measurement.
Overload percentage is the fraction of node-slots with that ratio above one.
The saturation metric uses the 80% high threshold. VRAM utilization describes
reserved residency and includes capacity held during migration/cold start.

Decision execution time measures policy computation plus action validation and
application. It excludes snapshot construction, simulated request events and
CSV/plot export. Total simulation wall time is also saved. Timing is machine
dependent and is the only intentionally non-deterministic result.

## Scope, checks and extension

`validate_run` independently reconstructs all request delay components,
deadline decisions, identities and the resource reservation ledger. Tests
exercise queue growth, draining, cold starts, active migration, finite capacity,
last-replica protection, deterministic replay and threshold/risk policies.

To reconstruct exported latency/SLA metrics and every summary mean/SD/count,
and verify source/input hashes and resource reservations, run:

```powershell
& .\.venv\Scripts\python.exe -m tools.verify_dynamic_results --output results/dynamic
```

This writes `export_verification.json` and does not run the simulator again.

The model has no packet loss, finite queue limit, failures, request cancellation,
network topology routing, interference model or realistic GPU throughput curve.
Service components move together; placement of individual DAG components is
left for a later experiment. No Kubernetes, OpenNebula or real networking is
involved. Published scheduling percentages supplied earlier are excluded from
the rationale and conclusions; results derive from this synthetic model only.

Modules separate generation, policies, simulation, metrics, running and plotting.
Future RL/optimization controllers can join `POLICIES` using
`(config, past_only_snapshot) -> list[Action]`; the same engine validates them.
Static generation/initial greedy placement are reused directly from
`placement_experiment`; generic JSON, hash and gzip helpers are reused from
`catalyst.reused`. Existing CATALYST controllers and parameters are not imported.
