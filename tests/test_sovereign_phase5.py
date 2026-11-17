"""Tenant isolation, metrics, evidence, and shadow promotion gates."""

from pathlib import Path

from fastapi.testclient import TestClient

from sovereign_maas.api import create_app
from sovereign_maas.research_models import TrainedForecastProvider

INTENT = {
    "service_name": "phase-five-demo",
    "tier": "Silver",
    "latency_p95_ms": 200,
    "minimum_model_quality": 0.9,
    "max_replicas": 3,
    "allowed_regions": ["eu-gr"],
    "allowed_actions": ["noop", "scale_out"],
}
ROOT = Path(__file__).resolve().parents[1]


def test_list_pages_are_tenant_scoped_and_bounded(tmp_path):
    client = TestClient(create_app(tmp_path / "api.sqlite3", {"a": "a-secret", "b": "b-secret"}))
    a = {"X-Tenant-Token": "a-secret"}
    b = {"X-Tenant-Token": "b-secret"}
    service = client.post("/v1/intents", json=INTENT, headers=a).json()
    run = client.post(
        "/v1/simulations/run",
        json={"service_id": service["id"], "seed": 7},
        headers={**a, "Idempotency-Key": "phase5-run"},
    ).json()
    assert [row["id"] for row in client.get("/v1/services", headers=a).json()] == [service["id"]]
    assert [row["id"] for row in client.get("/v1/simulations", headers=a).json()] == [run["id"]]
    assert client.get("/v1/services", headers=b).json() == []
    assert client.get("/v1/simulations", headers=b).json() == []
    assert client.get("/v1/workflows", headers=b).json() == []
    assert client.get("/v1/services?limit=101", headers=a).status_code == 422
    assert client.get("/v1/services?offset=1", headers=a).json() == []
    assert client.get("/v1/monitoring", headers=a).json()["drift_status"] == "NOT_EVALUATED"
    assert client.get("/v1/monitoring", headers=a).json()["forecast_coverage"] == 0.0
    assert client.get("/v1/monitoring", headers=b).json()["recent_run_count"] == 0
    assert client.get("/v1/monitoring", headers=b).json()["simulated_slo_rate"] is None


def test_metrics_are_protected_and_do_not_label_tenants_or_ids(tmp_path):
    client = TestClient(
        create_app(tmp_path / "api.sqlite3", {"a": "a-secret"}, metrics_token="metrics-secret")
    )
    client.get("/v1/services", headers={"X-Tenant-Token": "a-secret"})
    assert client.get("/metrics").status_code == 403
    response = client.get("/metrics", headers={"X-Metrics-Token": "metrics-secret"})
    assert response.status_code == 200
    assert "version=0.0.4" in response.headers["content-type"]
    assert 'route="/v1/services"' in response.text
    assert "a-secret" not in response.text
    assert "tenant_id" not in response.text
    assert TestClient(create_app(tmp_path / "other.sqlite3", {})).get("/metrics").status_code == 503


def test_research_summary_reads_existing_artifacts_without_invention(tmp_path):
    client = TestClient(
        create_app(tmp_path / "api.sqlite3", {"a": "a-secret"}, research_dir=ROOT / "results")
    )
    response = client.get("/v1/research/summary", headers={"X-Tenant-Token": "a-secret"})
    assert response.status_code == 200
    summaries = response.json()["summaries"]
    assert summaries["phase2-v1"]["data_source"] == "SIMULATION_ONLY"
    assert summaries["phase4-v1"]["live_jev_accuracy"] is None
    assert client.get("/v1/research/summary").status_code == 401
    empty = TestClient(create_app(tmp_path / "empty.sqlite3", {"a": "a-secret"}, research_dir=tmp_path))
    assert empty.get("/v1/research/summary", headers={"X-Tenant-Token": "a-secret"}).status_code == 503


def test_model_shadow_approval_is_separate_and_persistent(tmp_path):
    predictor = TrainedForecastProvider(ROOT / "results" / "phase2-v1")
    kwargs = {
        "tenant_tokens": {"a": "a-secret", "b": "b-secret"},
        "approver_tokens": {"a": "approver-secret"},
        "predictor": predictor,
    }
    db_path = tmp_path / "api.sqlite3"
    client = TestClient(create_app(db_path, **kwargs))
    a = {"X-Tenant-Token": "a-secret"}
    model = client.get("/v1/models", headers=a).json()["models"][0]
    assert model["stage"] == "CANDIDATE"
    url = f"/v1/models/{model['model_version']}/promote-shadow"
    assert client.post(url, headers=a).status_code == 403
    assert client.post(url, headers={**a, "X-Approver-Token": "wrong"}).status_code == 403
    assert (
        client.post(url, headers={**a, "X-Approver-Token": "approver-secret"}).json()["stage"]
        == "APPROVED_SHADOW"
    )
    restarted = TestClient(create_app(db_path, **kwargs))
    promoted = restarted.get("/v1/models", headers=a).json()["models"][0]
    assert promoted["stage"] == "APPROVED_SHADOW"
    assert promoted["runtime"] == "CONFIGURED_BY_ENVIRONMENT"
    assert (
        restarted.post(url + "bad", headers={**a, "X-Approver-Token": "approver-secret"}).status_code == 404
    )
    assert (
        restarted.get("/v1/models", headers={"X-Tenant-Token": "b-secret"}).json()["models"][0]["stage"]
        == "APPROVED_SHADOW"
    )
