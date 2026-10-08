# Simulator semantics and direct calibration

Inspected after real model profiling and the raw profiling report, before any
hardware-grounded simulation. Frozen source: `dynamic_placement/workload.py`,
`simulator.py`, `policies.py`, `joint_routing/simulator.py`, `controller.py`, and
`controller_optimization/optimized.py`. No existing file is edited.

| Quantity | Existing meaning and units | Hardware mapping |
|---|---|---|
| CPU demand | Service `cpu_cores`; reservation cores, integer 0.1-millicore tokens during execution | Preserve synthetic core demand, not replaced by milliseconds |
| GPU compute demand | One `simpy.Resource` token per inference; 2 or 3 concurrent execution units per virtual node | Preserve artificial concurrency slots; no inferred physical throughput or GPU utilization fraction |
| GPU memory | `gpu_vram_gb`; finite per-replica reservation on creation, extra target reservation during migration | Peak allocated bytes / 2^30 (GiB); variable name `gb` retained, units explicitly GiB |
| Node capacity | CPU, VRAM, bandwidth generated synthetically from the existing scenario | Preserve capacities and topology; 10 virtual nodes are not 10 measured laptops |
| Execution time | Preprocess, inference, postprocess in ms; worker multiplies each by the existing request work factor and divides by 1000 to obtain SimPy seconds | Per-class median preprocessing + measured H2D upload, median CUDA forward, median postprocessing including D2H/sync |
| Queue service rate | Actual discrete FIFO/replica worker throughput, network + resources + three stages; no direct M/M/1 server rate parameter | Calibrated stage durations change realized throughput; all finite resource queues unchanged |
| Candidate estimates | Global compute sum + network + existing utilization/queue contention proxy, then causal cycle EWMA | Same formulas and code; global 40/40/20 mean of class median times. No model-aware controller redesign |
| Cold start | New replica reserves resources then is unavailable for integer `cold_start_slots × slot_seconds`; initial replicas warm | Per-class ceil(measured median model-ready cold ms / 100 ms); no lifecycle change |
| Controller cold estimate | Single global cold-start parameter in both controllers | Ceil(population weighted mean model-ready cold / 100 ms). This estimate remains global and does not equal each class cold time |
| Cold first-request penalty | Additional 5 ms after activation | Retained synthetic 5 ms; no claim it is hardware measured |
| Migration | Finish in-flight request, reserve target, release source, pause one slot, then 10 ms penalty | Retain synthetic 100 ms downtime / 10 ms penalty; model state/network transfer was not benchmarked |
| SLA deadline | Service deadline in physical ms; original tier multipliers 1/1.8/3 | Unchanged. Dimensions already compatible; no outcome-dependent thresholds |
| Arrival/network/RNG | Compound Poisson clusters, periodic bursts, lognormal jitter, pairwise ms delays, Mbit payload / Mbps capacity | Entire original tape/topology/payload/core demand retained verbatim |

## Exact transformations

For class c, measured medians t_pre,c, t_upload,c, t_gpu,c, t_post,c (ms):

`preprocess_ms[c] = t_pre,c + t_upload,c`

`inference_ms[c] = t_gpu,c`, `postprocess_ms[c] = t_post,c`.

CPU-to-GPU upload is a measured transfer charged to the first CPU stage as an
explicit three-stage approximation. The CUDA forward excludes upload and output
handling. Postprocessing includes D2H plus synchronization. Per-request realized
compute is `(pre + gpu + post)[c] × original_work_factor` ms. Existing synthetic
work jitter remains; observed hardware variability is not fitted into an RNG.

`vram_gb[c] = inference_peak_allocated_bytes[c] / 2^30`.

Allocator-reserved peaks are reported separately and are never summed with
allocated memory. Peak allocation includes framework workspace; charging the
isolated peak independently per replica is conservative and does not reproduce
actual co-resident sharing. Baseline allocations are disclosed in raw outputs.

`cold_slots[c] = max(1, ceil(cold_start_median_ms[c] / (1000 × slot_seconds)))`.

The measured cold total sums Python constructor + local state read/load + model
H2D transfer + host-wall first synchronized CUDA forward. It denotes model-ready
startup in an already initialized CUDA process, with potentially cached disk
reads. Input preprocessing/upload are excluded from that startup total. Rounding
produces 100/200/500 ms readiness for LIGHT/MEDIUM/HEAVY respectively, versus
measured 64.294/182.730/439.583 ms; quantization overhead is disclosed.

## Population and frozen controller interface

There are no existing model architecture categories; tier is an SLA category,
not model weight. Service ID modulo 5 maps to LIGHT,LIGHT,MEDIUM,MEDIUM,HEAVY:
16 MobileNetV3 Large, 16 ResNet-50, 8 ViT-B/16 services. This cycles independently
of tiers (service ID modulo 3) and draws no RNG values. LIGHT/MEDIUM/HEAVY denote
architecture/memory categories, not an enforced latency ordering: measured
MobileNet batch-1 median is larger than ResNet median on this machine.

The frozen algorithms accept global Config timing parameters. They remain
global: each timing is the population weighted mean of per-model medians and
global cold-start slots are rounded from the population mean cold median.
Actual workers receive class-specific Config views while executing the exact
original `Simulator.worker` generator. No event or scheduling rule is changed.
Routing scores, placement/risk functions, queue awareness, action budget,
optimized indexes and causal completion history are inherited verbatim.
The legacy completion-history initial variance `(work_sigma × 14)^2` remains
unchanged, including its fixed 14-ms reference. A model-aware estimator would
be an algorithm change and is deliberately outside this experiment.

Initial assignments are the original generator assignments. They remain feasible
because measured memory reservations are below original synthetic demands; no
re-placement or RNG perturbation is performed. The scenario application metadata
is updated consistently with service memory. Original SLA/traffic hashes excluding
service memory are checked alongside the identical paired hardware workload hash.

## Selected regime

DIRECT is dimensionally valid for timing and memory and sufficient for this first
test. Node capacities/concurrency remain simulated; it is hardware-grounded
execution calibration, not an exact replica of the physical GPU pool. No second
pressure-preserving regime is run. No scaling factors restore synthetic pressure.
Consequently lower execution time and memory pressure may alter the operating
regime. This is an intended challenge to the old synthetic result, not an attempt
to preserve a win. Hardware profiles/configuration are frozen before the pilot.

Actual utilization comes from unchanged resource-time integrals with calibrated
worker durations. Legacy offered-load diagnostic ratios use the global controller
timings (not per-class times) and are explicitly retained as global-estimator
diagnostics, never presented as measured hardware utilization. Triggered cold
downtime in the new result is recomputed from each exported lifecycle interval.

## Measured and simulated

Measured: real architecture CPU preprocessing, upload, isolated CUDA forward,
CPU postprocessing, allocated/reserved GPU memory, cached model-ready cold start,
secondary single-thread CPU inference; actual local CPU controller runtime.

Simulated: 10 nodes, CPU/GPU/link contention and concurrency, memory co-residency,
arrivals, work-factor noise, topology/network, core reservation demands,
orchestration/migration, SLA service tiers and deadlines. No real telco testbed.

API references: [CUDA event timing](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.Event.html),
[allocated bytes](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_allocated.html),
[allocator-reserved bytes](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_reserved.html).
