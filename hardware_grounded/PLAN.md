# Hardware-grounded validation plan

JointSLA and SLA-aware source, routing/controller algorithms, action budgets,
random-number streams, lifecycle and request accounting remain frozen. SHA-256
protection covers existing verified results and Python source. New work is isolated.

Execution order: actual synchronized CUDA check; profiling; raw profiling report;
simulator unit inspection; documented calibration; profile/configuration freeze;
all existing and new tests; seeds 1,2,3 pilot; regime audit; MEDIUM seeds 1:30.
No calibration, traffic or SLA changes based on comparative results.

Three torchvision architectures: MobileNetV3 Large, ResNet-50, ViT-B/16, random
local weights. Batch 1 FP32, 50 GPU warmups, 300 measured forwards per model,
20 model-cold repetitions, secondary CPU 10 warmups/30 repetitions, one CPU
thread. Exact protocol is saved before hardware measurements. CUDA events and
explicit synchronization are mandatory. No process/driver-cold claim.

Hardware timing central estimate is the median; p95/p99 are retained. Workload
assignment is deterministic and does not draw from any existing RNG stream.
Class proportions are 40% LIGHT, 40% MEDIUM, 20% HEAVY unless pre-existing
categorical model classes are found. Units and possible physical mappings must
be inspected before selecting an evaluation regime. Existing physical-ms SLA
deadlines stay unchanged. MEDIUM = 10 simulated nodes / 40 services.

## Hypotheses and decision rules (before any simulation outcomes)

- HW1: lower aggregate breach fraction; mean paired JointSLA-minus-SLA-aware
  delta < 0, 95% paired bootstrap CI wholly < 0, Holm-adjusted signed-rank p < .05.
- HW2: same criteria for p95 request latency.
- HW3: no material resource increase: mean average-replica count, mean
  time-averaged allocated VRAM, and mean total actions each at most 1.05 times
  SLA-aware. Report peak replicas/VRAM and each action type independently.
  This is a descriptive 5% guardrail, not a non-inferiority statistical claim.
- HW4: measured full controller snapshot+decision mean < existing 10 ms budget;
  p95 and individual seeds also reported. No GPU work runs during simulation.
- HW5: lower mean breach fraction in at least two of three model classes.
  This descriptive cross-class criterion is not a simultaneous class-level
  significance claim. Report every class and tier, including negative Gold results.

Primary family: aggregate breach fraction, mean, p95, p99 request latency;
30 paired seeds, 10,000 paired bootstrap resamples (existing implementation),
95% CI, Wilcoxon signed-rank, Holm correction, rank-biserial effect size,
wins/ties/losses. No request-level pseudo-replication.

Optional LARGE and p95 sensitivity are not required for this first calibration;
include them only after a stable MEDIUM evaluation and explicit preregistration
of their configuration before their results. They cannot replace the main result.

All arrivals/outcomes must reconcile exactly; both policies must receive the
same per-seed workload and traffic hash. No future leakage or dropped audits.
Real measured execution/memory is injected into a simulated network, workload,
multi-node resource scheduler and orchestrator. Single laptop GPU profiling
does not constitute a real telco deployment or universal hardware benchmark.
