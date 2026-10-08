# Research Question

Does the validated synthetic JointSLA advantage persist under measured architecture execution and memory?

**JointSLA did not retain its aggregate SLA/p95 advantage in this preregistered DIRECT calibration. Preserve this negative external-validity result; it does not invalidate the previously verified synthetic experiments.**

# Hardware Platform

CPU: Intel(R) Core(TM) Ultra 7 255HX; 20 logical processors; 31.43 GiB RAM. GPU: NVIDIA GeForce RTX 5070 Laptop GPU, 8123 MiB VRAM; compute capability [12, 0]. OS Windows-11-10.0.26300-SP0, Python 3.12.14, PyTorch 2.10.0+cu128, torchvision 0.25.0+cu128, CUDA build 12.8. Actual synchronized kernel passed. Driver 617.42; AC detected True. Detailed clocks, temperature and power observations: `profiling/telemetry.json`.

# Profiling Methodology

Locally initialized torchvision architectures, no datasets or pretrained download; deterministic in-memory uint8 RGB image, batch 1 FP32 3×224×224. Eval + inference_mode, one CPU thread, TF32 disabled, no system power changes. Architecture execution only, not task accuracy. [CUDA events](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.Event.html) with explicit synchronization isolate GPU forward. Separate host timers measure synchronized transfers/postprocessing.

# AI Models

| model | pre_median_ms | upload_median_ms | gpu_median_ms | post_median_ms | peak_allocated_MiB | cold_median_ms |
| --- | --- | --- | --- | --- | --- | --- |
| mobilenet | 0.71295 | 0.1043 | 6.25717 | 0.0803 | 36.6763 | 64.2938 |
| resnet50 | 0.73025 | 0.07785 | 4.64158 | 0.06655 | 155.142 | 182.73 |
| vit_b16 | 0.74105 | 0.08475 | 6.67034 | 0.09155 | 348.057 | 439.583 |

LIGHT/MEDIUM/HEAVY denote architecture/memory classes. MobileNet median GPU time exceeds ResNet on this laptop; no enforced latency ordering.

Secondary CPU-only inference, one thread, 30 measured repetitions, ms (not used for GPU pipeline calibration):

| model | mean | median | std | p95 | p99 |
| --- | --- | --- | --- | --- | --- |
| mobilenet | 9.03194 | 8.86695 | 0.596408 | 10.0738 | 11.0565 |
| resnet50 | 84.2845 | 82.3144 | 3.75126 | 90.8557 | 91.6166 |
| vit_b16 | 300.872 | 302.897 | 10.7504 | 314.895 | 328.177 |

# Warm-Up and Measurement Protocol

Each model: 50 GPU warmups, 300 measured steady repetitions; 20 model-cold repetitions, 30 warmups after each model-cold first forward; secondary CPU: 10 warmups and 30 measured repetitions. 5,010 raw rows across three models. Raw GPU event and host-wall forwards are distinct. Full mean/median/sample-SD/p50/p90/p95/p99/min/max saved for every stage.

# CPU Preprocessing

| model | stage | count | mean | median | std | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mobilenet | cpu_pre | 300 | 0.735247 | 0.71295 | 0.0627645 | 0.879095 | 0.992713 |
| mobilenet | input_upload | 300 | 0.100122 | 0.1043 | 0.0339564 | 0.13114 | 0.28305 |
| resnet50 | cpu_pre | 300 | 0.748703 | 0.73025 | 0.0647242 | 0.873495 | 1.06848 |
| resnet50 | input_upload | 300 | 0.086797 | 0.07785 | 0.0325872 | 0.12893 | 0.158588 |
| vit_b16 | cpu_pre | 300 | 0.764283 | 0.74105 | 0.0708434 | 0.90849 | 1.019 |
| vit_b16 | input_upload | 300 | 0.0966533 | 0.08475 | 0.0294303 | 0.13613 | 0.201378 |

No disk I/O. Resize, normalize and prepare NCHW on CPU. H2D upload measured separately; mapping charges it to the first CPU stage.

# GPU Inference

| model | count | mean | median | std | p95 | p99 | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mobilenet | 300 | 5.41875 | 6.25717 | 1.8313 | 7.45646 | 7.66709 | 3.04746 | 8.17869 |
| resnet50 | 300 | 4.76135 | 4.64158 | 0.368588 | 5.69626 | 6.48478 | 4.53552 | 6.70733 |
| vit_b16 | 300 | 6.72407 | 6.67034 | 0.129016 | 6.95801 | 7.14907 | 6.58234 | 7.39328 |

Resident CUDA input; forward only, no transfer or preprocessing. MobileNet distribution varies substantially; clock/launch/background effects are possible explanations, not isolated causal findings.

# CPU Postprocessing

| model | mean | median | std | p95 | p99 |
| --- | --- | --- | --- | --- | --- |
| mobilenet | 0.0786993 | 0.0803 | 0.0293877 | 0.104285 | 0.116932 |
| resnet50 | 0.0759013 | 0.06655 | 0.02001 | 0.118145 | 0.147211 |
| vit_b16 | 0.095885 | 0.09155 | 0.0311595 | 0.14646 | 0.172875 |

Includes logits D2H, explicit synchronize, softmax, top-5, argmax. No classification accuracy claim.

# VRAM Measurements

| model | model_residency_bytes | allocated_after_model_load_bytes | reserved_after_model_load_bytes | inference_peak_allocated_bytes | inference_peak_reserved_bytes | baseline_allocated_bytes |
| --- | --- | --- | --- | --- | --- | --- |
| mobilenet | 22110720 | 30630400 | 35651584 | 38457856 | 60817408 | 0 |
| resnet50 | 103917056 | 112436736 | 123731968 | 162678272 | 226492416 | 8519680 |
| vit_b16 | 346926080 | 356494336 | 402653184 | 364963840 | 406847488 | 8519680 |

Bytes. Model residency is allocation delta after model load. Inference allocated and allocator-reserved peaks are different measurements, not additive. Profile reservation uses absolute inference peak allocated / 2^30 per replica, conservatively including framework workspace. Baseline allocation is disclosed. No VRAM CI is invented for a single observed maximum over repetitions. [Allocated](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_allocated.html) and [reserved](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_reserved.html) APIs.

# Cold Start Measurements

| model | stage | count | mean | median | std | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mobilenet | construction | 20 | 30.1481 | 30.1023 | 0.52378 | 30.8012 | 31.4418 |
| mobilenet | local_state_load | 20 | 20.396 | 19.4986 | 3.78308 | 21.347 | 33.3513 |
| mobilenet | model_gpu_transfer | 20 | 11.3466 | 9.86745 | 2.63535 | 16.5003 | 16.7499 |
| mobilenet | first_gpu_inference | 20 | 4.50319 | 4.02424 | 1.25865 | 7.70004 | 8.14335 |
| mobilenet | first_gpu_forward_wall | 20 | 4.55163 | 4.0703 | 1.26565 | 7.76564 | 8.21625 |
| mobilenet | cold_start_total | 20 | 66.4423 | 64.2938 | 6.63607 | 72.4562 | 88.2934 |
| mobilenet | warmed_gpu_inference | 20 | 3.80628 | 3.12416 | 1.46981 | 7.08924 | 7.29481 |
| resnet50 | construction | 20 | 114.797 | 114.458 | 1.54006 | 116.542 | 119.388 |
| resnet50 | local_state_load | 20 | 41.1236 | 39.9586 | 6.4739 | 42.6583 | 63.2389 |
| resnet50 | model_gpu_transfer | 20 | 21.7544 | 21.0642 | 2.22064 | 25.8095 | 25.8523 |
| resnet50 | first_gpu_inference | 20 | 6.36892 | 6.20866 | 0.855138 | 7.51211 | 7.59786 |
| resnet50 | first_gpu_forward_wall | 20 | 6.43405 | 6.25405 | 0.875106 | 7.61132 | 7.6633 |
| resnet50 | cold_start_total | 20 | 184.109 | 182.73 | 7.26371 | 190.505 | 207.159 |
| resnet50 | warmed_gpu_inference | 20 | 5.05971 | 4.68838 | 0.633959 | 5.99808 | 6.36285 |
| vit_b16 | construction | 20 | 284.755 | 285.43 | 4.49313 | 291.885 | 294.129 |
| vit_b16 | local_state_load | 20 | 98.95 | 93.5628 | 18.6999 | 109.104 | 162.755 |
| vit_b16 | model_gpu_transfer | 20 | 51.2694 | 52.098 | 3.25709 | 55.8625 | 56.051 |
| vit_b16 | first_gpu_inference | 20 | 7.30742 | 7.29864 | 0.314967 | 7.74002 | 8.04631 |
| vit_b16 | first_gpu_forward_wall | 20 | 7.36923 | 7.3556 | 0.318683 | 7.80697 | 8.10299 |
| vit_b16 | cold_start_total | 20 | 442.343 | 439.583 | 22.0664 | 462.825 | 513.293 |
| vit_b16 | warmed_gpu_inference | 20 | 6.95983 | 6.96275 | 0.193655 | 7.26552 | 7.3377 |

CUDA process/driver already initialized. New constructor + cached local state load + synchronized model H2D + first-forward host wall. OS cache not evicted; internet excluded. Input preparation/upload excluded from startup. This measures model-ready overhead, not process boot or storage-cold latency.

# Simulator Mapping

## Simulator semantics and direct calibration

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

### Exact transformations

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

### Population and frozen controller interface

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

### Selected regime

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

### Measured and simulated

Measured: real architecture CPU preprocessing, upload, isolated CUDA forward,
CPU postprocessing, allocated/reserved GPU memory, cached model-ready cold start,
secondary single-thread CPU inference; actual local CPU controller runtime.

Simulated: 10 nodes, CPU/GPU/link contention and concurrency, memory co-residency,
arrivals, work-factor noise, topology/network, core reservation demands,
orchestration/migration, SLA service tiers and deadlines. No real telco testbed.

API references: [CUDA event timing](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.Event.html),
[allocated bytes](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_allocated.html),
[allocator-reserved bytes](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.memory_reserved.html).

Concrete per-class values: `simulator_mapping.csv`; controller config: `experiment_freeze.json`. Global mean-median parameters and per-class physical worker times are deliberately distinct. The frozen global estimator is not adapted to each model.

# What Is Hardware-Measured vs Simulated

Measured: three isolated architecture stage timings, input/output transfers, model residency/allocated/reserved memory, cached model-ready cold start, secondary CPU forward, controller CPU runtime. Simulated: 10 nodes, all node capacities, 2/3 GPU concurrency slots, CPU reservations/interference, network/bandwidth, synthetic arrivals/work jitter, service tiers/deadlines, actions and migration downtime. Hardware-derived execution does not make node contention or orchestration physically validated.

# Hardware-Grounded Workload

MEDIUM 10 nodes / 40 services, 100 slots × 0.1 s. ID modulo 5 gives 16/16/8 services, without RNG draws. Original topology, warm initial assignments, per-request work factors, traffic tape, tier deadlines and resource capacities stay unchanged. Original tape equality was independently checked for all 30 seeds. Median calibrated service times and measured peak allocation replace synthetic execution/memory. DIRECT regime only; no pressure-restoring normalization, optional LARGE or p95 sensitivity. Headroom/pressure differs from the old synthetic operating point and therefore limits mechanism attribution.

# Pilot

{
  "common_hashes": true,
  "finite_metrics": true,
  "max_drain_seconds": 0.12203560722028683,
  "max_rss_mib": 127.796875,
  "max_runtime_seconds": 1.320499999987078,
  "maximum_waiting_requests": 323,
  "profile_sha256": "683a12933079dd3d93d7ef0e9532103f15234b5115e55ffaf732726f17e29cb5",
  "regime": "Direct hardware times; no pressure rescaling or post-pilot tuning. Unlimited queues fully drained.",
  "requests_verified": 69244,
  "runs": 6,
  "successful": true,
  "unit_and_component_checks": true
}

Before the pilot, all 171 existing tests plus 18 new tests passed (189 total). The new adapter passed exact uniform-profile request/action/node/event trace equivalence for both policies; profile parsing, conversions, assignment, tape preservation and causal snapshots were checked. Six pilot runs, seeds 1/2/3. All physical-unit/request/capacity/lifecycle/hash checks passed; maximum drain 0.122 s. Pilot was a feasibility gate, not evidence supporting a superiority claim. No configuration changed afterward.

# Main 30-Seed Evaluation

Completed 60 runs, 30 paired seeds; 701,264 request outcomes independently reconstructed from exports. Per-run request/routing/component/lifecycle/reservation audits are saved. Pilot outcomes remain separate. 900 subgroup rows checked. All original verified artifact hashes remain intact.

# SLA Results

| policy | metric | mean | standard_deviation | ci95_lower | ci95_upper |
| --- | --- | --- | --- | --- | --- |
| sla_aware | sla_breach_rate | 0.154269 | 0.0319943 | 0.143064 | 0.165399 |
| joint_sla | sla_breach_rate | 0.254808 | 0.0297548 | 0.244392 | 0.265554 |

Rates are fractions of ALL offered requests; no drops or unplaced requests. Between-seed arithmetic mean is primary; raw numerators and denominators retained. JointSLA did not retain its aggregate SLA/p95 advantage in this preregistered DIRECT calibration. Preserve this negative external-validity result; it does not invalidate the previously verified synthetic experiments.

# Mean / p95 / p99

| policy | metric | mean | standard_deviation | ci95_lower | ci95_upper |
| --- | --- | --- | --- | --- | --- |
| sla_aware | mean_request_latency_ms | 48.7698 | 9.44267 | 45.485 | 52.0977 |
| sla_aware | p95_latency_ms | 188.7 | 53.7112 | 170.526 | 208.474 |
| sla_aware | p99_latency_ms | 410.297 | 128.419 | 365.696 | 456.712 |
| joint_sla | mean_request_latency_ms | 61.8862 | 8.3533 | 59.0844 | 64.928 |
| joint_sla | p95_latency_ms | 226.403 | 32.0355 | 215.823 | 238.152 |
| joint_sla | p99_latency_ms | 377.136 | 77.8819 | 351.291 | 405.256 |

Milliseconds; means ± SD and 95% bootstrap CI of seed means. Requests finishing after the 10-second arrival horizon are included; all queues drain without additional decisions.

# Model-Class Results

| model_class | policy | sla_breach_rate | mean_request_latency_ms | p95_latency_ms | p99_latency_ms | mean_queue_delay_ms |
| --- | --- | --- | --- | --- | --- | --- |
| HEAVY | joint_sla | 0.307413 | 76.7937 | 304.68 | 492.529 | 62.6366 |
| HEAVY | sla_aware | 0.182093 | 54.7527 | 228.395 | 457.955 | 39.1636 |
| LIGHT | joint_sla | 0.249506 | 57.3221 | 198.551 | 308.687 | 44.2884 |
| LIGHT | sla_aware | 0.157103 | 48.1051 | 176.699 | 373.117 | 32.7313 |
| MEDIUM | joint_sla | 0.233921 | 58.7571 | 220.469 | 326.099 | 46.2046 |
| MEDIUM | sla_aware | 0.136045 | 45.7905 | 178.198 | 388.139 | 31.9817 |

Rates are fractions. Every class is retained; same per-seed request-weighted metric definition within each subgroup. Full tier×model rows: `tier_model_class_results.csv`; every cell has ≥30 requests; no cells silently excluded.

# Gold / Silver / Bronze

| tier | policy | sla_breach_rate | mean_request_latency_ms | p95_latency_ms | p99_latency_ms | mean_queue_delay_ms |
| --- | --- | --- | --- | --- | --- | --- |
| Bronze | joint_sla | 0.161729 | 70.763 | 261.117 | 421.987 | 56.9478 |
| Bronze | sla_aware | 0.131477 | 69.3968 | 279.664 | 556.258 | 52.8941 |
| Gold | joint_sla | 0.359662 | 53.9713 | 194.713 | 310.992 | 41.389 |
| Gold | sla_aware | 0.226285 | 38.3217 | 143.564 | 287.274 | 24.8248 |
| Silver | joint_sla | 0.236035 | 61.4783 | 227.221 | 358.409 | 48.7149 |
| Silver | sla_aware | 0.101723 | 39.4864 | 139.863 | 303.772 | 25.0338 |

Gold trade-offs are not hidden. All tier/model counts, queue delays, mean/p95/p99 exported. No subgroup statistical superiority is implied by a descriptive mean.

# Resource Cost

| policy | average_replicas | peak_replicas | average_vram_residency_gib | peak_pool_vram_gib | cold_starts | scale_outs | scale_ins | migrations | total_actions | average_cpu_utilization | average_gpu_utilization |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| joint_sla | 44.3074 | 57.8667 | 6.44724 | 8.80508 | 38.8333 | 38.8333 | 37.7333 | 3.53333 | 80.1 | 0.0359671 | 0.27201 |
| sla_aware | 68.1303 | 74.7667 | 10.0604 | 11.4295 | 97.9 | 97.9 | 67.3333 | 2.26667 | 167.5 | 0.035898 | 0.275929 |

Average replicas/VRAM are exact allocation integrals over 10 seconds, including cold/retiring replicas and migration double reservation. Pool VRAM peak is the maximum simultaneous ledger total; node VRAM fractions have synthetic capacities as denominators. Compute utilization uses actual finite-resource time integrals; offered ratios are only global-estimator diagnostics. Reduced resource cost cannot by itself establish joint SLA/resource efficiency.

# Controller Cost

| policy | controller_total_instrumented_mean_ms | controller_total_instrumented_p95_ms | controller_snapshot_mean_ms | controller_decision_mean_ms | request_routing_decision_mean_ms | request_routing_decision_p95_ms | controller_cpu_ms_per_request | wall_clock_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| joint_sla | 3.57048 | 6.11757 | 0.4873 | 3.08318 | 0.0171408 | 0.025863 | 0.060177 | 1.29449 |
| sla_aware | 0.518406 | 1.07026 | 0.0215783 | 0.496827 | 0 | 0 | 0.00491873 | 0.52545 |

Same existing full snapshot + policy/action timing scope. CPU wall-clock overhead during the simulation, no GPU profiling concurrent. Routing and simulated request delays remain distinct. Runtime timing is inherently nondeterministic; request/actions are deterministic.

# Statistical Tests

30 independent paired seeds 1–30; seed is the inference unit. Existing percentile paired bootstrap (10,000 resamples, fixed hash-derived RNG seed 73001), two-sided Wilcoxon signed-rank (round differences to 12 decimals), Holm family of four primary metrics, rank-biserial correlation and W/T/L. Negative JointSLA-minus-SLA-aware delta means benefit; positive RBC means benefit. Latency quantiles use linear interpolation per seed, then seed-level mean; they are not pooled request percentiles.

| metric | delta_joint_minus_sla | delta_ci95_lower | delta_ci95_upper | p_value | p_value_holm | rank_biserial_correlation | wins | ties | losses | supported_improvement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sla_breach_rate | 0.100539 | 0.0882897 | 0.111685 | 1.86265e-09 | 7.45058e-09 | -1 | 0 | 0 | 30 | False |
| mean_request_latency_ms | 13.1164 | 9.97928 | 16.0211 | 1.30385e-07 | 3.91155e-07 | -0.948387 | 2 | 0 | 28 | False |
| p95_latency_ms | 37.7036 | 20.8983 | 52.8018 | 0.000231637 | 0.000463273 | -0.729032 | 7 | 0 | 23 | False |
| p99_latency_ms | -33.1615 | -78.597 | 8.55445 | 0.262122 | 0.262122 | 0.23871 | 18 | 0 | 12 | False |

Independent sorted-quantile, bootstrap, signed-rank DP/normal-CDF and Holm reconstructions passed.

# Negative Seeds

SLA-loss seeds (JointSLA breach fraction > SLA-aware): [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30].

All negative seed/metric pairs, including tail latency exceptions, are in `negative_seed_cases.csv`; complete paired differences in `paired_seed_differences.csv`. No failed seed removed.

# HW1-HW5

{
  "HW1": false,
  "HW2": false,
  "HW3": true,
  "HW4": true,
  "HW5": false,
  "criteria": "Preregistered PLAN.md; HW3 5% descriptive guardrail, HW5 benefit in >=2 classes, not significance/non-inferiority claims.",
  "model_class_breach_improvement": {
    "HEAVY": -0.12532023509266538,
    "LIGHT": -0.0924031040868683,
    "MEDIUM": -0.09787616940064803
  },
  "resource_ratios_joint_over_sla": {
    "average_replicas": 0.650332559485267,
    "average_vram_residency_gib": 0.6408560670978516,
    "total_actions": 0.47820895522388057
  }
}

HW3 is the predeclared descriptive 5% resource guardrail; it is not a statistical non-inferiority test or proof of good SLA efficiency. HW5 requires lower class mean breach rate in at least two classes. No hypothesis definition changed after outcomes.

# Threats to Validity

Single physical machine, single GPU architecture, laptop GPU; no clock/power isolation and background load possible; sequential model profiling may mix device operating states; only three representative vision architectures and local random weights; CPU one thread; cached disk startup, initialized driver; measured memory workspace may be shared on real co-resident GPUs; synthetic arrival process, work jitter, network, node count/capacity and concurrency remain. Global frozen controller priors approximate class-specific execution/cold overhead and preserve the legacy 14-ms initial variance. Direct injection changes the original pressure regime. This joint calibration cannot identify which changed physical assumption causes a performance reversal. No real telco testbed, no real deployment, no hardware-variability sensitivity run.

# Safe Paper Claims

JointSLA did not retain its aggregate SLA/p95 advantage in this preregistered DIRECT calibration. Preserve this negative external-validity result; it does not invalidate the previously verified synthetic experiments.

Safe wording: “In a 30-paired-seed hardware-grounded simulation using isolated FP32 profiles from three neural-network architectures on one physical laptop GPU, the previously observed synthetic JointSLA advantage was challenged and the DIRECT-calibration result was preserved without algorithm tuning.” Describe the actual metrics and resource/controller trade-offs below, not a universal superiority claim.

# Claims We Cannot Make

Production validated, carrier-grade, real 6G deployment, universally hardware independent, GPU-independent, real telco validation, state of the art, or statistically established class-level advantages. No claim of actual co-resident GPU throughput, pretrained task accuracy, internet/storage-cold loading, or a result from an unrun pressure-preserving/sensitivity/LARGE experiment.

# Implications for B-Level Publication

Hardware grounding strengthens methodological transparency and exposes a meaningful limitation, but weakens the case for a persistent aggregate advantage when HW1/HW2 fail. A paper may report regime-dependent trade-offs and this negative result; it cannot use this run to support a robustness claim. The experiment alone cannot guarantee publication or a venue classification. Further mechanism ablations would require separately preregistered experiments, not retuning these frozen results.

Reproduce existing profiles/results:

```powershell
.venv\Scripts\python.exe run_hardware_profiling.py --check
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_hardware_grounded_experiment.py --pilot --reuse-results
.venv\Scripts\python.exe run_hardware_grounded_experiment.py --seeds 1:30 --reuse-results
```

Rerun simulations with fixed measured profiles: replace `--reuse-results` with `--force`, pilot first. Fresh hardware profiling: `python run_hardware_profiling.py --profile --force --models mobilenet,resnet50,vit_b16` only in a new experiment checkout/output before creating its freeze; this experiment refuses profile overwrite after calibration freeze. Full profile dependencies: `hardware_grounded/requirements-profile.txt`.
