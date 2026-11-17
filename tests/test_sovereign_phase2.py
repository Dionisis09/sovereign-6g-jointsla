"""Simulation replay, censoring, model lineage and conservative decision gates."""

from datetime import UTC, datetime, timedelta
from shutil import copytree

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sovereign_maas.api import create_app
from sovereign_maas.decision import decide, propose
from sovereign_maas.domain import ForecastBundle, ServiceBundle, TypedIntent
from sovereign_maas.research_data import episode, generate, split_plan
from sovereign_maas.research_models import (
    TrainedForecastProvider,
    binary_metrics,
    decision_metrics,
    fit_logistic,
    fit_quantile,
    hazard_matrix,
    load_frames,
    load_models,
    predict_logistic,
    predict_quantile,
    quantile_time,
    train,
)
from sovereign_maas.simulation import make_snapshot

INTENT = TypedIntent(
    service_name="vision-demo",
    tier="Gold",
    latency_p95_ms=200,
    minimum_model_quality=0.9,
    max_replicas=4,
    allowed_regions=("eu-gr",),
    allowed_actions=("scale_out",),
)


@pytest.fixture(scope="module")
def trained_output(tmp_path_factory):
    output = tmp_path_factory.mktemp("phase2-model")
    generate(output)
    train(output)
    return output


def test_split_groups_and_censored_ttv_are_distinct():
    plan = split_plan()
    assert not (set(plan["train_seeds"]) & set(plan["test_seeds"]))
    rows = [episode("steady", seed, "train", plan["horizon_s"])[0] for seed in plan["train_seeds"]]
    assert any(row["ttv_censored"] for row in rows)
    assert any(not row["ttv_censored"] for row in rows)
    assert all(row["observed_p95_ms"] < row["slo_ms"] for row in rows)
    assert all(
        row["ttv_observed_s"] is None and row["followup_s"] == 12 for row in rows if row["ttv_censored"]
    )


def test_hazard_risk_set_stops_at_event_and_keeps_censor_rows():
    frame = pd.DataFrame(
        [
            {
                "queue_depth": 1,
                "arrival_rps": 50,
                "cycle_ms": 20,
                "network_ms": 10,
                "slo_ms": 100,
                "headroom_ms": 50,
                "followup_s": 2,
                "ttv_censored": False,
                "ttv_observed_s": 2,
            },
            {
                "queue_depth": 2,
                "arrival_rps": 45,
                "cycle_ms": 20,
                "network_ms": 10,
                "slo_ms": 100,
                "headroom_ms": 40,
                "followup_s": 3,
                "ttv_censored": True,
                "ttv_observed_s": None,
            },
        ]
    )
    matrix, labels = hazard_matrix(frame, training=True)
    assert matrix.shape == (5, 7)
    assert labels is not None and labels.tolist() == [0, 1, 0, 0, 0]


def test_numpy_estimators_produce_finite_probabilities_and_action_quantiles():
    x = np.asarray([[float(i), float(i % 3)] for i in range(40)])
    y = (x[:, 0] >= 20).astype(int)
    model = (
        fit_logistic(x[:30], y[:30], x[30:], y[30:])
        if len(np.unique(y[30:])) == 2
        else fit_logistic(x[::2], y[::2], x[1::2], y[1::2])
    )
    predictions = predict_logistic(model, x)
    assert np.isfinite(predictions).all()
    assert ((predictions >= 0) & (predictions <= 1)).all()
    quantile = fit_quantile(x, 1 + 0.1 * x[:, 0])
    assert np.isfinite(predict_quantile(quantile, x)).all()


def test_metric_math_and_validation_only_downstream_decisions(trained_output):
    scores = binary_metrics(np.asarray([0, 1]), np.asarray([0.1, 0.9]))
    assert scores["brier"] == pytest.approx(0.01)
    assert scores["auroc"] == pytest.approx(1.0)
    assert scores["pr_auc"] == pytest.approx(1.0)
    assert quantile_time(np.asarray([[0.05, 0.12], [0.01, 0.02]]), 0.1)[0] == 2
    episodes, actions, _ = load_frames(trained_output)
    validation = episodes[episodes["split"] == "validation"]
    validation_actions = actions[actions["split"] == "validation"]
    downstream = decision_metrics(trained_output, validation, validation_actions)
    assert downstream["n"] == 100
    assert sum(downstream["selected_actions"].values()) == 100


def test_dataset_hashes_and_model_artifact_are_verified(trained_output, tmp_path):
    provider = TrainedForecastProvider(trained_output)
    service = ServiceBundle(tenant_id="a", intent=INTENT)
    snapshot = make_snapshot(7)
    forecast = provider.predict(service, snapshot, propose(service, snapshot))
    assert forecast.evidence == "SIMULATION_TRAINED"
    assert forecast.model_version
    assert 0 <= forecast.breach_probability_12s <= 1
    copy = tmp_path / "copy"
    copytree(trained_output, copy)
    (copy / "models.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum"):
        load_models(copy)


def test_missing_stale_ood_and_incomplete_predictions_fail_closed():
    service = ServiceBundle(tenant_id="a", intent=INTENT)
    snapshot = make_snapshot(7)
    candidates = propose(service, snapshot)
    base = ForecastBundle(
        snapshot_id=snapshot.id,
        service_id=service.id,
        valid_until=datetime.now(UTC) + timedelta(seconds=30),
        model_version="test-model",
        dataset_sha256="test-data",
        breach_probability_12s=0.9,
        ttv_q10_s=10,
        ttr_q90_s={candidate.id: 1 for candidate in candidates},
        post_sla_probability={candidate.id: 0.9 for candidate in candidates},
    )
    assert decide(service, snapshot, candidates, base).selected_candidate_id == "jointsla-scale"
    cases = (
        (None, "PREDICTION_MISSING"),
        (base.model_copy(update={"ood": True}), "PREDICTION_OOD"),
        (
            base.model_copy(update={"valid_until": datetime.now(UTC) - timedelta(seconds=1)}),
            "PREDICTION_EXPIRED",
        ),
        (base.model_copy(update={"ttr_q90_s": {}}), "PREDICTION_INCOMPLETE"),
        (base.model_copy(update={"snapshot_id": "wrong"}), "PREDICTION_LINEAGE_MISMATCH"),
    )
    for forecast, reason in cases:
        decision = decide(service, snapshot, candidates, forecast, require_forecast=True)
        assert decision.selected_candidate_id == "baseline-noop"
        assert reason in decision.reasons


def test_trained_model_api_exposes_lineage_and_conservative_decision(trained_output, tmp_path):
    provider = TrainedForecastProvider(trained_output)
    client = TestClient(create_app(tmp_path / "api.sqlite3", {"tenant-a": "token-a"}, provider))
    headers = {"X-Tenant-Token": "token-a"}
    service = client.post("/v1/intents", json=INTENT.model_dump(mode="json"), headers=headers).json()
    forecast_response = client.post(
        "/v1/predictions/evaluate", json={"service_id": service["id"], "seed": 7}, headers=headers
    )
    assert forecast_response.status_code == 200
    assert forecast_response.json()["evidence"] == "SIMULATION_TRAINED"
    run = client.post(
        "/v1/simulations/run",
        json={"service_id": service["id"], "seed": 7},
        headers={**headers, "Idempotency-Key": "model-run"},
    ).json()
    assert run["forecast"]["model_version"] == run["decision"]["model_version"]
    assert run["decision"]["prediction_source"] == "SIMULATION_TRAINED"
    assert run["decision"]["selected_candidate_id"] == "baseline-noop"
