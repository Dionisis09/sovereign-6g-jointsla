"""Phase 1 API, policy and persistence acceptance tests."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from sovereign_maas.api import create_app
from sovereign_maas.decision import decide, propose
from sovereign_maas.domain import ServiceBundle, TypedIntent
from sovereign_maas.simulation import make_snapshot

INTENT = {
    "service_name": "vision-demo",
    "tier": "Gold",
    "latency_p95_ms": 200,
    "minimum_model_quality": 0.9,
    "max_replicas": 4,
    "allowed_regions": ["eu-gr"],
    "allowed_actions": ["scale_out"],
}


def test_end_to_end_simulation_and_persistent_idempotency(tmp_path):
    path = tmp_path / "maas.sqlite3"
    client = TestClient(create_app(path, {"tenant-a": "token-a"}))
    headers = {"X-Tenant-Token": "token-a"}
    service_response = client.post("/v1/intents", json=INTENT, headers=headers)
    assert service_response.status_code == 201
    service = service_response.json()
    assert service["tenant_id"] == "tenant-a"
    run_headers = {**headers, "Idempotency-Key": "run-7"}
    response = client.post(
        "/v1/simulations/run", json={"service_id": service["id"], "seed": 7}, headers=run_headers
    )
    assert response.status_code == 201
    run = response.json()
    assert run["snapshot"]["evidence"] == "SIMULATED"
    assert run["candidates"][0]["source"] == "joint_sla_v2_warm_headroom"
    assert run["decision"]["selected_candidate_id"] == "jointsla-scale"
    assert run["decision"]["correlation_id"]
    assert run["verification"]["slo_met"] is True
    assert run["verification"]["evidence"] == "SIMULATED"
    rejected = {r["candidate_id"]: r["reasons"] for r in run["decision"]["rejected"]}
    assert "RESIDENCY_DENIED" in rejected["heuristic-migrate"]
    replay = TestClient(create_app(path, {"tenant-a": "token-a"}))
    assert replay.get(f"/v1/simulations/{run['id']}", headers=headers).json() == run
    assert (
        replay.post(
            "/v1/simulations/run", json={"service_id": service["id"], "seed": 7}, headers=run_headers
        ).json()
        == run
    )
    conflict = replay.post(
        "/v1/simulations/run", json={"service_id": service["id"], "seed": 8}, headers=run_headers
    )
    assert conflict.status_code == 409


def test_deny_by_default_and_tenant_isolation(tmp_path):
    client = TestClient(create_app(tmp_path / "maas.sqlite3", {"a": "token-a", "b": "token-b"}))
    assert client.post("/v1/intents", json=INTENT).status_code == 401
    assert client.post("/v1/intents", json=INTENT, headers={"X-Tenant-Token": "wrong"}).status_code == 401
    created = client.post("/v1/intents", json=INTENT, headers={"X-Tenant-Token": "token-a"}).json()
    assert (
        client.get(f"/v1/services/{created['id']}", headers={"X-Tenant-Token": "token-b"}).status_code == 404
    )
    assert (
        client.post(
            "/v1/simulations/run",
            json={"service_id": created["id"], "seed": 1},
            headers={"X-Tenant-Token": "token-b", "Idempotency-Key": "one"},
        ).status_code
        == 404
    )


def test_invalid_intent_and_missing_idempotency_key(tmp_path):
    client = TestClient(create_app(tmp_path / "maas.sqlite3", {"a": "token-a"}))
    headers = {"X-Tenant-Token": "token-a"}
    assert client.post("/v1/intents", json={**INTENT, "unknown_slo": 1}, headers=headers).status_code == 422
    assert (
        client.post(
            "/v1/intents", json={**INTENT, "minimum_model_quality": 0.99}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/intents", json={**INTENT, "allowed_regions": ["us-east"]}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post("/v1/intents", json={**INTENT, "allowed_regions": ["eu-de"]}, headers=headers).status_code
        == 422
    )
    created = client.post("/v1/intents", json=INTENT, headers=headers).json()
    assert (
        client.post(
            "/v1/simulations/run", json={"service_id": created["id"], "seed": 1}, headers=headers
        ).status_code
        == 400
    )


def test_capacity_and_stale_telemetry_fall_back_to_noop():
    intent = TypedIntent.model_validate({**INTENT, "max_replicas": 1})
    bundle = ServiceBundle(tenant_id="a", intent=intent)
    snapshot = make_snapshot(7)
    decision = decide(bundle, snapshot, propose(bundle, snapshot))
    assert decision.selected_candidate_id == "baseline-noop"
    assert (
        "NO_SCALE_CHANGE" in next(r for r in decision.rejected if r.candidate_id == "jointsla-scale").reasons
    )
    normal = ServiceBundle(tenant_id="a", intent=TypedIntent.model_validate(INTENT))
    stale = snapshot.model_copy(update={"observed_at": datetime.now(UTC) - timedelta(seconds=31)})
    stale_decision = decide(normal, stale, propose(normal, stale))
    assert stale_decision.selected_candidate_id == "baseline-noop"
    assert all("STALE_TELEMETRY" in r.reasons for r in stale_decision.rejected)


def test_already_breached_enters_recovery_without_positive_ttv():
    bundle = ServiceBundle(tenant_id="a", intent=TypedIntent.model_validate({**INTENT, "latency_p95_ms": 60}))
    snapshot = make_snapshot(7)
    decision = decide(bundle, snapshot, propose(bundle, snapshot))
    assert decision.ttv_low_s == 0
    assert decision.selected_candidate_id == "jointsla-scale"
    assert decision.reasons == ("INCIDENT_RECOVERY",)


def test_healthy_but_too_close_to_breach_rejects_slow_action():
    bundle = ServiceBundle(
        tenant_id="a", intent=TypedIntent.model_validate({**INTENT, "latency_p95_ms": 120})
    )
    snapshot = make_snapshot(7)
    assert snapshot.observed_p95_ms < 120
    decision = decide(bundle, snapshot, propose(bundle, snapshot))
    assert decision.ttv_low_s == 0
    assert decision.selected_candidate_id == "baseline-noop"
    assert (
        "INSUFFICIENT_RECOVERY_SLACK"
        in next(r for r in decision.rejected if r.candidate_id == "jointsla-scale").reasons
    )


def test_unconfigured_api_is_unready_and_denies_intents(tmp_path):
    client = TestClient(create_app(tmp_path / "maas.sqlite3"))
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    assert client.post("/v1/intents", json=INTENT).status_code == 401
