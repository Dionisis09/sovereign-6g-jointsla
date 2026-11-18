# Bronze/Silver/Gold matched CPU simulation (2026-11-18)

## Scope and ownership

This follow-up implements a **new synthetic multi-service study** around the
offline exact allocator. It does not change the frozen JointSLA experiment,
runtime MaaS decision path, Kubernetes adapter, or subscription contracts.
The protocol was committed first (`3dcd33a`), before outcome generation. The
implementation, test, output hashes, and this report are the new work.

## Experimental design

Three simultaneous services share seven pod slots. Each episode has 20 one-second
ticks. The policy sees the previous tick's arrival rate and current queue, never
the next arrivals. Steady, ramp and burst tapes are generated once per seed and
replayed under all four policies. Development seeds 200–219 and held-out test
seeds 220–239 are disjoint. The simulator has a two-tick scale readiness delay.

The comparison policies are fixed floors (Gold 2, Silver 1, Bronze 1), a simple
reactive threshold, the existing `required_warm` function with a shared budget,
and the new subscription optimizer. The `jointsla_warm` arm is **only the warm
headroom function**, not the complete JointSLA routing/Kubernetes controller.
The optimizer receives current-state-only analytic logistic scores labelled
**uncalibrated synthetic heuristic forecasts**. These are not the Phase 2 model
and are not empirical multi-service TTV/TTR estimates. Its tier thresholds and
cost weights are illustrative settings frozen in the first implementation.

The outcome is a **service-tick** latency-threshold breach, not an all-offered
request SLA failure. Pod-ticks sum ready replicas across the 20-tick episode.

## Held-out results: 60 matched episodes

| Policy | Gold breach ticks | Silver | Bronze | All service-ticks | Pod-ticks / episode |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed floor | 46.75% | 89.92% | 34.92% | 57.19% | 80.00 |
| Reactive | 37.25% | 62.83% | 27.25% | 42.44% | 92.87 |
| JointSLA warm rule | **0.00%** | **5.50%** | 30.08% | **11.86%** | 121.07 |
| Subscription optimizer | 20.58% | 22.17% | **12.92%** | 18.56% | **102.33** |

The optimizer uses about 15.5% fewer pod-ticks than the warm rule and reduces
Bronze breach ticks by 17.17 percentage points. It has 6.69 percentage points
**more** overall breach ticks, including worse Gold and Silver results. Its
hard tier/forecast gates had no feasible action at 389 of 1,200 control steps;
the simulator kept the current allocation in those steps. The development split
shows the same direction; no parameters were retuned after viewing it. There is
**no promotion** or runtime loading of the allocator.

## Interpretation and next decision

An exact minimum of the allocator's one-step forecast cost is not an optimal
long-horizon policy. The current heuristic forecasts are uncalibrated and the
strict illustrative tier gates frequently reject every option. The Bronze
improvement cannot justify the Gold/Silver regression. The next useful study
needs measured or well-calibrated **per-action** TTV, TTR, readiness and PostSLA
outcomes for concurrent services, plus subscription-specific SLO and resource
contracts. Then freeze a new protocol and test a constrained multi-step policy
against this unchanged warm-rule baseline, including per-tier failure and
pod-time Pareto curves. GPU/HAMi validation remains separate.

## Reproduction

`python -m sovereign_maas.research_subscription --output results/subscription-v1`
refuses to overwrite an existing nonempty directory. The output contains
development and test episode rows, summary values, and SHA-256 hashes for the
protocol, implementation and outputs. The 14 focused tests, Ruff, mypy, and
the read-only legacy evidence verifier passed locally. Full Ubuntu CI is
reported by the matching commit's GitHub Actions run.
