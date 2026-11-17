# Phase 7 sequential CPU follow-up (2026-11-17)

## 1. Repository facts discovered

The earlier Phase 7 experiment was a one-step contextual bandit. Its source and outputs remain frozen. The existing deterministic JointSLA decision gate and synthetic workload generator can be reused without editing them. This host has no discrete NVIDIA GPU or accessible HAMi cluster.

## 2. Implemented

`PHASE7_SEQUENCE_PROTOCOL.json` was committed as `08d889a` before outcome generation. `research_phase7_sequence.py` adds a twelve-step stateful queue environment, two-tick scale readiness, persistent scale state, deterministic 5% action failure, one scale attempt per episode, and the existing current-state action gate. Masked linear Q-learning uses seeds 120–159; validation selects one of three policy seeds on 160–179; test is held out on 180–199. No scenario identifier, seed, or future state is in the policy features. The three comparison policies are no-op, a 70 ms headroom threshold, and the JointSLA gate. Outputs include weights, per-episode observations, metrics, and source/output hashes under `results/phase7-sequence-v1`.

## 3. How to run

From the repository root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m sovereign_maas.research_phase7_sequence
& .\.venv\Scripts\python.exe -m sovereign_maas.evidence
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; & .\.venv\Scripts\python.exe -m pytest -q tests/test_sovereign_phase7_sequence.py tests/test_sovereign_evidence.py
```

The experiment command verifies existing output hashes and refuses to overwrite nonempty output. To run an independent copy, pass `--output` with a new directory.

## 4. Tests actually executed

Five focused sequential tests passed. Ruff check and format, mypy, and the read-only evidence gate passed locally. The gate now verifies 40 hashes. Ubuntu CI is the repository-wide test environment because Windows Application Control blocks the local `ormsgpack` native extension; record the exact CI run after it completes.

## 5. Evidence and limitations

All figures are **SIMULATION_ONLY_CPU**. The selected seed-23 Q policy and JointSLA each had a 0.62 rate of episodes with any simulated SLO breach among 100 matched test episodes. The paired reduction was 0.00 with a 95% bootstrap interval [0.00, 0.00]. The Q policy took 0.91 scale actions per episode versus 0.99 for JointSLA, but its breach-tick rate was worse: 0.219 versus 0.163. No-op had 0.87 episode breach rate; the 70 ms threshold had 0.74. The strict preregistered improvement gate failed: **do not promote**. The model is absent from the runtime decision path.

The simulator is a deliberately small queue model. Failure is deterministic per episode, not a measured hardware failure process. It does not model GPU contention, inference quality changes, real traffic, energy, live LLM reward proposals, or transfer to an NVIDIA/HAMi cluster. A bootstrap interval of [0, 0] here means paired binary outcomes matched on these synthetic episodes; it is not proof of equivalence elsewhere.

## 6. Architecture decisions

The environment calls the existing deterministic gate on the current observation; invalid scale actions cannot be sampled or executed. Scale readiness is applied after two simulated ticks. Splits are seed-disjoint from the earlier 0–119 research and from each other. Validation selects the policy; test data is used once for the final comparison. The trained weights are research artifacts and have no production switch.

## 7. What I should learn

Review Markov state design, temporal-difference learning, action masking, seed-disjoint evaluation, and paired bootstrap intervals. A useful exercise is to change only the scale delay in a **new versioned protocol**, predict how the policies should change, and compare matched episodes without changing the current frozen result.

## 8. Next phase

Hardware work requires an authorized NVIDIA/HAMi test cluster. Live reward proposals require a configured provider and a separate bounded evaluation protocol. Neither is a prerequisite for reproducing this CPU experiment. Any future policy proposal should first beat the JointSLA gate on new held-out scenarios and receive manual review before runtime integration.
