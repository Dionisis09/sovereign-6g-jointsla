# Offline subscription pod optimizer (prototype)

This module is a **CPU-only decision study**, not a deployed controller. It solves
the small, finite allocation problem exactly *conditional on supplied action
forecasts*. No multi-service TTV/TTR or PostSLA model has been validated here.

## Why this matches the proposal

The proposal has three Pillars, not a Pillar 4. **Innovation Area 4** concerns
agentic AI/MARL for RCA, remediation and resource orchestration. **WP4** covers
DSO closed loops, the inference fabric, and smart resource management. This
prototype supplies a deterministic allocation authority beneath possible agent
or RL proposals. It does not implement federation, MARL or live remediation.

## Mathematical decision

For each service `s`, forecasts supply one option per integer target replica
count `n`. The service carries early pre-action TTV (q10). Each option carries
predicted post-action breach probability `p(s,n)`, post-SLO probability,
conservative action TTR (q90), and readiness delay. A tier policy supplies minimum replicas, maximum acceptable breach risk,
and a loss weight. Feasible downscale requires:

`TTV_q10(s) > ready(s,n) + TTR_q90(s,n) + 0.5 s`.

The same timing check applies to proactive scale-out. Existing incidents may
scale out for recovery. A stale or out-of-domain forecast permits only the
current allocation. Every option must pass its tier breach and PostSLO gates.
The optimizer enumerates the Cartesian product of feasible options and the
shared pod budget, minimizing:

`sum_s tier_weight(s)*p(s,n_s) + 0.05*sum_s n_s + 0.02*sum_s abs(n_s-current_s)`.

The coefficients and tier thresholds in `DEFAULT_TIERS` are **illustrative
research settings**, not contractual Bronze/Silver/Gold prices or tuned values.
The result is exact for the forecast table and objective, not globally optimal
under unknown future arrivals. If no allocation satisfies all hard tier and
budget constraints, it returns an explicit error instead of quietly degrading
a subscriber. JointSLA's service risk score (SVRS) and router variance/slack
`risk_proxy` are uncalibrated ranking signals. The supplied service SVRS only
breaks exact objective ties against downscaling higher-risk services; neither
is substituted for `p(s,n)`.
Enumeration stops if the candidate product exceeds 100,000 combinations; a
larger deployment would need a bounded integer optimizer and a separate gate.

## Evidence boundary and next experiment

The tests use hand-authored numerical cases to verify allocation, timing,
budget and fail-closed behavior. They do **not** demonstrate SLA improvement.
Before choosing contractual tier thresholds or promoting a policy, freeze a
multi-tenant workload protocol with common traffic tapes, seed-disjoint
development/validation/test sets, cold-start and rollback observations,
calibrated per-action outcomes, and a pod-time budget. Compare against the
unchanged JointSLA, fixed floors, and reactive scaling on held-out episodes.
Report per-tier all-offered failures, pod-seconds, fairness, paired intervals,
and calibration; then validate on actual GPU/HAMi infrastructure.
