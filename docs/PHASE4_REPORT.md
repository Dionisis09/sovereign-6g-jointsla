# Phase 4 TypeSafe/Jev advisory and fixture comparison (2026-11-16)

## Implemented contract

`JudgmentProvider` has `DisabledJudgmentProvider`, `FixtureJudgmentProvider`, and `TypeSafeJevProvider`. The live adapter follows the official [System One HTTP reference](https://docs.typesafe.ai/api/system-one.md): one authenticated `POST https://api.typesafe.ai/v1/systemone` with explicit `model`, a bounded structured `state`, and 14 named typed questions for three candidates. It asks `Choice` incident class and TTV bin, `Score` urgency and each candidate's risk, and `Noul` review, breach warning and each candidate's post-SLA chance. Candidate TTR is a `Choice` bin. Answers, distributions, legends, selected options, token usage and model name are validated against the request. Noul has no vendor confidence field; its probability is kept distinct from Choice/Score confidence.

`sanitize_state()` sends only allowlisted numeric simulator fields and candidate IDs/kinds. Tenant ID, service name, tokens, raw intent text, policy text and region lists are excluded. Live calls require `SOVEREIGN_JEV_MODE=live`, a `TYPESAFE_API_KEY`, explicit model and `SOVEREIGN_JEV_ALLOWED_TENANTS`; a missing key/model keeps the mode disabled. Tenant denial, telemetry older than 30 seconds, unsafe input, local rate limit, open circuit, timeout, HTTP or schema failure return an explicit `UNAVAILABLE` advisory. The adapter uses a 5-second HTTP timeout, at most one retry for 429/5xx, a 60-request/minute local limit and a 30-second circuit after three failures. No API key or raw exception is returned to clients.

The `POST /v1/judgments/evaluate` endpoint and existing simulation/workflow records expose the advisory. `decide()` remains the independent deterministic policy. A fixture or Jev answer cannot waive tenant auth, capacity, residency, allowed actions, trained-forecast freshness or separate approval. The offline `fixture` is explicitly named `SIMULATED_FIXTURE_NOT_JEV` and its confidence fields are zero because it is deterministic test code, not a measured model.

## Matched synthetic comparison

The preregistered comparison reused the frozen Phase 2 test seeds 80–99 across five scenario families (100 snapshots), with the same checked model and action-outcome Parquet files. No Phase 2 file was modified. `results/phase4-v1/metrics.json` carries SHA-256 hashes for the dataset, model, evaluator, fixture, policy and per-episode decisions. The same command was rerun and reproduced the file contents.

| Arm | Breach Brier | Selected scale / migrate / no-op | Simulated SLO rate | Review rate |
| --- | ---: | ---: | ---: | ---: |
| Classic Phase 2 ML | 0.08623 | 3 / 0 / 97 | 16% | n/a |
| Fixture-only warning; conservative no-op | 0.124, uncalibrated proxy | 0 / 0 / 100 | 16% | 100% |
| Classic ML plus fixture advisory | same ML predictor | 3 / 0 / 97 | 16% | 100% |

The paired seed-bootstrap 95% interval for fixture-minus-ML Brier is −0.0137 to 0.0888. The paired simulated SLO-rate difference is 0, with interval 0 to 0, because the three ML scale choices did not change the SLO outcome in this toy replay. These numbers show **no downstream benefit** from attaching this fixture advisory. They do not measure Jev. The test set was used in Phase 2 already, so this is a transparent follow-up comparison rather than a fresh independent holdout. Fixture-only runs no action because a categorical TTV/TTR bin cannot satisfy the existing calibrated quantitative forecast gate.

Live Jev accuracy, latency, cost and confidence calibration are **unmeasured**. The mocked response in tests checks typed parsing and token accounting, not service performance or price. True Jev-only and hybrid prediction arms require authorized live responses on a separately frozen evaluation set. No hardware or cloud-edge action was executed.

## Tests actually executed

From this Windows Python 3.12 environment:

| Check | Outcome |
| --- | --- |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q tests/test_sovereign_phase4.py` | 13 passed |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q` | 391 passed |
| `python -m ruff check` on the new package and four test modules | passed |
| `python -m ruff format --check` on the same paths | passed |
| `python -m mypy sovereign_maas` | no issues in 18 source files |
| `python -m pip check` | no broken requirements |
| `python -m sovereign_maas.phase4_demo` | fixture advisory available; `jointsla-scale`; `SIMULATED` verification |
| `python -m sovereign_maas.research_phase4 --models results/phase2-v1 --output results/phase4-v1` | created and revalidated the same metrics |
| GitHub Actions YAML parse | passed |

Tests use `httpx.MockTransport`; they make no external TypeSafe calls. The host's Windows Application Control still blocks LangSmith's auto-loaded pytest plugin; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` avoids that plugin without skipping project tests. Docker Compose and a live Jev account were unavailable, so neither was exercised.
