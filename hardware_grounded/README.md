# Hardware-grounded validation of frozen JointSLA

This experiment measures MobileNetV3 Large, ResNet-50 and ViT-B/16 architecture
execution on the detected physical CUDA GPU, then calibrates the existing
CPU→GPU→CPU simulation. No datasets, pretrained accuracy or real telco deployment.
Existing algorithms and verified results are protected by SHA-256.

The DIRECT MEDIUM evaluation uses 10 virtual nodes, 40 services, 100 epochs,
30 paired seeds, a deterministic 40/40/20 model mix and unchanged arrival tapes,
deadlines, node capacities, policies, budget and resource/lifecycle semantics.

**Result:** JointSLA's aggregate advantage did not survive this calibration:
15.43% vs 25.48% mean SLA breaches (SLA-aware vs JointSLA), with lower resource
use by JointSLA. See the complete 28-section report in
`results/hardware_grounded/report.md`. No tuning was performed after the pilot.

## Install

Python 3.12 was used. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r hardware_grounded/requirements.txt --timeout 180
```

The existing workspace venv already contains these dependencies. The profiling
runner requires a real synchronized CUDA kernel and successful torchvision
import; it stops without GPU measurements if either fails. The dependency wheel
was checked against the official PyTorch SHA-256 before execution.

## Reuse or reproduce simulations

```powershell
.venv\Scripts\python.exe run_hardware_profiling.py --check
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_hardware_grounded_experiment.py --pilot --reuse-results
.venv\Scripts\python.exe run_hardware_grounded_experiment.py --seeds 1:30 --reuse-results
```

To execute simulations again against exactly the frozen measured profiles:

```powershell
.venv\Scripts\python.exe run_hardware_grounded_experiment.py --pilot --force
.venv\Scripts\python.exe run_hardware_grounded_experiment.py --seeds 1:30 --force
```

Controller wall time varies between runs; request/action outcomes are deterministic.
The runner checks the fixed profile/config and execution source hashes. `--force`
replaces only new hardware-grounded outputs, never a previous verified tree.
CSV seeds such as `--seeds 4,5,6` or ranges are accepted for partial runs; they
are not a substitute for the required 30-seed analysis.

## Fresh hardware profiling

Fresh profiling belongs in a separate copy of the experiment before its calibration
freeze is created. Do not delete this study's freeze or replace its measured data.
In that fresh project copy (without the hardware-grounded result directory):

```powershell
.venv\Scripts\python.exe run_hardware_profiling.py --check
.venv\Scripts\python.exe run_hardware_profiling.py --profile --models mobilenet,resnet50,vit_b16 --force
```

After inspecting the newly measured values and documenting their mapping, freeze
its calibration and run tests/pilot before full evaluation. The existing mapping
contains this machine's measured cold values and must be documented afresh for
another machine; this study makes no cross-device guarantee.

Profiling is batch 1 FP32, 50 GPU warmups, 300 repetitions, 20 model-cold loads,
one CPU thread; CPU-only timing is secondary. CUDA events time forwards, while
host timers with synchronization measure upload/output transfer. Model-cold is
not CUDA process/driver-cold; local checkpoint reads may be OS-cached.

## Mapping and module boundaries

- `profiling.py` / `environment.py`: raw measurements and actual platform metadata.
- `calibration.py`: validated catalog, ms/GiB conversions, deterministic class/tape
  mapping, weighted global controller configuration, immutable experiment freeze.
- `physics.py`: delegate the original physical worker with a class-specific Config
  view; no copied worker or scheduling algorithm.
- `experiment.py`: paired runner, unchanged metric definitions, per-run audit CSVs.
- `audit.py` / `validation.py`: independent component, routing, memory, outcome,
  subgroup and statistical checks from exports.
- `analysis.py`: existing 10,000-resample seed-level bootstrap/Wilcoxon/Holm
  framework, negative results, 12 PNG/SVG/PDF figures and report.

`SIMULATOR_MAPPING.md` distinguishes physical stage times/memory from simulated
core/concurrency units. Controllers retain their original global timing interface;
actual workers are heterogeneous. That mismatch and the changed direct pressure
regime are disclosed limitations, not repaired by tuning.

All per-run request outcomes, slot/node trajectories, routing candidates, actions,
reservations and lifecycle events are under `results/hardware_grounded/runs/`.
All offered requests are counted and fully drained; no admission drops occur.
Class/tier means and quantiles are first computed per seed and then summarized,
never pooled as independent request-level statistical observations.

HW1/HW2/HW5 failed; HW3 passed the descriptive resource-increase guardrail and
HW4 passed the controller budget. Less resource use with worse QoS is not proof
of superior resource efficiency. No LARGE, pressure-preserving or p95-profile
sensitivity series is claimed for this first experiment.
