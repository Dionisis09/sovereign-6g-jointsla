# Phase 2 simulation-only evaluation (2026-11-16)

## Reproduction and provenance

From the repository root, install `requirements-maas.txt` with Python 3.12 and run `python -m sovereign_maas.research_runner --output results/phase2-v1`. The command creates a 500-episode/1,500-action Parquet replay, trains models using train seeds 0–59 and validation seeds 60–79, then evaluates once on frozen test seeds 80–99. `docs/PHASE2_SPLITS.json` was written before generation; `results/phase2-v1/dataset_manifest.json`, `model_manifest.json` and `metrics.json` record hashes and exact metrics. The same episode/action file SHA-256 values were obtained in a separate development generation before the final run. Existing research outputs were not modified.

The first scikit-learn import failed because Windows Application Control blocked `_cython_blas`. The documented pre-test amendment replaced its estimator implementation with NumPy logistic and linear quantile models. All features and splits stayed fixed. Model coefficients are checked JSON. No test-label-dependent tuning or second holdout evaluation was performed.

## Held-out results

| Target | Metric | Result |
| --- | --- | ---: |
| Breach within 12 s, 100 episodes, 88 positives | Brier, calibrated logistic | 0.0862 |
| Same | Brier, constant prior | 0.1057 |
| Same | AUROC / PR-AUC, logistic | 0.9176 / 0.9890 |
| TTV, 88 observed and 12 right-censored | Integrated Brier, 1–12 s | 0.0767 |
| Same | q50 MAE, observed events only | 0.6023 s |
| TTR, 200 active action outcomes | q90 pinball / upper coverage | 0.0656 s / 92.5% |
| PostSLA, 300 action outcomes | Brier / AUROC | 0.0676 / 0.9756 |
| Decision replay, 100 episodes | selected scale / migrate / no-op | 3 / 0 / 97 |
| Same | simulated SLO success, selected / no-op | 16% / 16% |

These are held-out synthetic outcomes under one simplified queue generator. They do not estimate real hardware performance or guarantee calibration. TTV MAE and pinball are reported only for observed events and are selection-biased; integrated Brier uses the complete fixed 12-second administrative follow-up. PostSLA action outcomes share one seeded exogenous episode and are counterfactual **simulation**, not deployments. The tested policy produced no SLO-rate gain over no-op; no thresholds were changed after seeing that result.

## Remaining gaps

The model has no external telemetry or real serving measurements. The five scenario families share a toy queue model and one initial snapshot each. Calibration sets are small, and the q10/q90 labels do not imply a safety guarantee. PostgreSQL, hardware validation and deployable action adapters remain future work. Docker was not executed on this host because its CLI was unavailable.
