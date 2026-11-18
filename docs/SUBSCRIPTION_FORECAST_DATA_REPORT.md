# Multi-service forecast data: CPU preparation (2026-11-18)

## What is new

Protocol `SUBSCRIPTION_FORECAST_PROTOCOL.json` was committed as `41f38c7`
before data generation. `research_subscription_data.py` replays the already
frozen 20-tick Bronze/Silver/Gold workload tapes under fixed-floor, reactive,
and JointSLA warm-headroom behavior policies. At eligible pre-action snapshots
it evaluates every single-service integer replica target that respects the
shared seven-pod budget. Future arrivals are used **only for labels**.

| Split | Seeds | Rows | Observed first breach | Observed return to SLO | Post-SLO positive |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 240–279 | 45,246 | 21,223 | 37,641 | 33,065 |
| Validation | 280–299 | 22,666 | 10,689 | 18,864 | 16,542 |
| Test | 300–319 | 22,660 | 10,628 | 18,852 | 16,581 |

TTV is the first future no-action breach tick, or censored if none occurs in
four ticks. TTR is the first future action tick at or below the SLO, or
censored if none occurs. It is zero when the service is already healthy. The
other labels are SLO status at tick four and any breach during the window.
Each snapshot is repeated across feasible targets, so rows are **not
independent episodes**. No family, seed, behavior policy, or future traffic
may be used as a model feature. Split-level evaluation must group by episode
and avoid confidence intervals that treat action rows as independent.

## Boundary

These labels come from a simple CPU queue simulator. They are exact only
relative to its deterministic counterfactual transition and known exogenous
traffic tape. Each row changes **one** service target while the others hold
their current replica counts; it does not evaluate all joint actions. The
dataset does not establish calibrated hardware TTV/TTR, GPU contention,
real pod readiness, request-level SLA, or subscription prices. No model has
been promoted or wired to runtime decisions.

## Validation and next gate

The generator writes deterministic compressed JSONL, split counts and eight
SHA-256 source/output hashes. Tests check split separation, invariant
pre-action TTV across candidate targets, shared budget, future-only labels,
compression determinism and all frozen hashes. The next CPU gate is to fit
TTV, TTR and PostSLO predictors **only on train**, calibrate/select on
validation, and report test calibration and action-level policy effect once.
Hardware data can then replace simulator outcomes under a new protocol.
