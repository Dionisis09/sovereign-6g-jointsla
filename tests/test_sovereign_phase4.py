"""Phase 4 TypeSafe contract mocks, safety gates and fixture comparison."""

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sovereign_maas.api import create_app, from_environment
from sovereign_maas.decision import propose
from sovereign_maas.domain import ServiceBundle, TypedIntent
from sovereign_maas.judgment import (
    DisabledJudgmentProvider,
    FixtureJudgmentProvider,
    TypeSafeJevProvider,
    sanitize_state,
)
from sovereign_maas.research_phase4 import evaluate
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
TEXT = (
    "service: vision-demo; tier: Gold; p95: 200; quality: 0.9; "
    "replicas: 4; regions: eu-gr; actions: scale_out"
)


def context():
    service = ServiceBundle(tenant_id="tenant-a", intent=TypedIntent.model_validate(INTENT))
    snapshot = make_snapshot(7)
    return service, snapshot, propose(service, snapshot)


def wire_response(questions):
    answers = {}
    for key, question in questions.items():
        if question["type"] == "noul":
            answers[key] = {"type": "noul", "noul": 0.7}
        elif question["type"] == "choice":
            options = list(question["criteria"])
            answers[key] = {
                "type": "choice",
                "choice": options[0],
                "confidence": 1.0,
                "probabilities": {option: float(index == 0) for index, option in enumerate(options)},
            }
        else:
            levels = question["criteria"]
            answers[key] = {
                "type": "score",
                "score": 1.0,
                "confidence": 1.0,
                "legend": {str(index): level for index, level in enumerate(levels)},
                "probabilities": {str(index): float(index == 1) for index in range(len(levels))},
            }
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 123, "output_tokens": 45}}


def test_sanitized_state_does_not_expose_identity_or_policy_text():
    service, snapshot, candidates = context()
    state = sanitize_state(service, snapshot, candidates)
    encoded = json.dumps(state)
    assert "tenant-a" not in encoded
    assert "vision-demo" not in encoded
    assert service.id not in encoded
    assert "allowed_regions" not in encoded
    assert len(state["candidates"]) == 3
    assert DisabledJudgmentProvider().judge(service, snapshot, candidates).status == "DISABLED"
    fixture = FixtureJudgmentProvider().judge(service, snapshot, candidates)
    assert fixture.source == "FIXTURE"
    assert fixture.reason == "SIMULATED_FIXTURE_NOT_JEV"
    assert fixture.incident_confidence == 0.0


def test_typesafe_live_wire_contract_with_mock_only():
    service, snapshot, candidates = context()
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        assert body["model"] == "jev-1.13.0"
        assert len(body["questions"]) == 14
        assert {question["type"] for question in body["questions"].values()} == {
            "choice",
            "score",
            "noul",
        }
        assert "tenant-a" not in request.content.decode()
        return httpx.Response(200, json=wire_response(body["questions"]))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TypeSafeJevProvider("test-key", "jev-1.13.0", {"tenant-a"}, client)
    judgment = provider.judge(service, snapshot, candidates)
    assert judgment.status == "AVAILABLE"
    assert judgment.source == "LIVE"
    assert judgment.model_version == "jev-1.13.0"
    assert judgment.input_tokens == 123
    assert judgment.output_tokens == 45
    assert set(judgment.candidate_post_sla_probability) == {item.id for item in candidates}
    assert calls[0].headers["authorization"] == "Bearer test-key"


def test_external_egress_denial_happens_before_network():
    service, snapshot, candidates = context()

    def handler(request):
        raise AssertionError("network must not be reached")

    provider = TypeSafeJevProvider(
        "test-key",
        "jev-1.13.0",
        {"other-tenant"},
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.judge(service, snapshot, candidates)
    assert result.status == "UNAVAILABLE"
    assert result.reason == "TENANT_EGRESS_DENIED"


def test_stale_snapshot_denied_before_external_call():
    service, snapshot, candidates = context()
    stale = snapshot.model_copy(update={"observed_at": datetime.now(UTC) - timedelta(seconds=31)})

    def handler(request):
        raise AssertionError("stale state must not reach network")

    provider = TypeSafeJevProvider(
        "test-key",
        "jev-1.13.0",
        {"tenant-a"},
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.judge(service, stale, candidates)
    assert result.status == "UNAVAILABLE"
    assert result.reason == "STALE_TELEMETRY"


@pytest.mark.parametrize("corruption", ["missing", "wrong_type", "bad_distribution", "bad_score"])
def test_malformed_live_answers_fail_closed(corruption):
    service, snapshot, candidates = context()

    def handler(request):
        questions = json.loads(request.content)["questions"]
        payload = wire_response(questions)
        if corruption == "missing":
            del payload["answers"]["ttv_bin"]
        elif corruption == "wrong_type":
            payload["answers"]["breach_12s"] = {"type": "choice", "choice": "yes"}
        elif corruption == "bad_distribution":
            payload["answers"]["incident_class"]["probabilities"] = {
                option: 0.5 for option in questions["incident_class"]["criteria"]
            }
        else:
            payload["answers"]["urgency"]["score"] = 3.0
        return httpx.Response(200, json=payload)

    provider = TypeSafeJevProvider(
        "test-key", "jev-1.13.0", {"tenant-a"}, httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = provider.judge(service, snapshot, candidates)
    assert result.status == "UNAVAILABLE"
    assert result.reason == "UPSTREAM_OR_SCHEMA_ERROR"
    assert result.candidate_post_sla_probability == {}


def test_transient_retry_then_circuit_breaker():
    service, snapshot, candidates = context()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    provider = TypeSafeJevProvider(
        "test-key", "jev-1.13.0", {"tenant-a"}, httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert provider.judge(service, snapshot, candidates).status == "UNAVAILABLE"
    assert len(calls) == 2
    provider.judge(service, snapshot, candidates)
    provider.judge(service, snapshot, candidates)
    assert len(calls) == 6
    assert provider.judge(service, snapshot, candidates).reason == "CIRCUIT_OPEN"
    assert len(calls) == 6


def test_local_rate_limit_and_timeout_fail_closed():
    service, snapshot, candidates = context()
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("mock timeout")

    provider = TypeSafeJevProvider(
        "test-key",
        "jev-1.13.0",
        {"tenant-a"},
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.judge(service, snapshot, candidates)
    assert result.status == "UNAVAILABLE"
    assert result.reason == "UPSTREAM_OR_SCHEMA_ERROR"
    assert len(calls) == 1
    provider._requests.extend([time.monotonic()] * 60)
    assert provider.judge(service, snapshot, candidates).reason == "RATE_LIMITED_LOCALLY"
    assert len(calls) == 1


def test_fixture_is_advisory_for_api_and_workflow(tmp_path):
    client = TestClient(
        create_app(
            tmp_path / "maas.sqlite3",
            {"tenant-a": "operator"},
            approver_tokens={"tenant-a": "approver"},
            judgment_provider=FixtureJudgmentProvider(),
        )
    )
    headers = {"X-Tenant-Token": "operator"}
    service = client.post("/v1/intents", json=INTENT, headers=headers).json()
    advisory = client.post(
        "/v1/judgments/evaluate", json={"service_id": service["id"], "seed": 7}, headers=headers
    )
    assert advisory.status_code == 200
    assert advisory.json()["source"] == "FIXTURE"
    run = client.post(
        "/v1/simulations/run",
        json={"service_id": service["id"], "seed": 7},
        headers={**headers, "Idempotency-Key": "run-7"},
    ).json()
    assert run["decision"]["selected_candidate_id"] == "jointsla-scale"
    assert run["judgment"]["source"] == "FIXTURE"
    baseline = TestClient(create_app(tmp_path / "baseline.sqlite3", {"tenant-a": "operator"}))
    baseline_service = baseline.post("/v1/intents", json=INTENT, headers=headers).json()
    baseline_run = baseline.post(
        "/v1/simulations/run",
        json={"service_id": baseline_service["id"], "seed": 7},
        headers={**headers, "Idempotency-Key": "run-7"},
    ).json()
    assert baseline_run["decision"]["selected_candidate_id"] == run["decision"]["selected_candidate_id"]
    workflow = client.post(
        "/v1/workflows", json={"text": TEXT, "seed": 7}, headers={**headers, "Idempotency-Key": "flow-7"}
    ).json()
    assert workflow["status"] == "NEEDS_APPROVAL"
    assert workflow["judgment"]["source"] == "FIXTURE"
    assert client.get(f"/v1/workflows/{workflow['id']}", headers=headers).json() == workflow


def test_no_key_live_request_reports_disabled_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_DB_PATH", str(tmp_path / "maas.sqlite3"))
    monkeypatch.setenv("SOVEREIGN_TENANT_TOKENS", '{"tenant-a":"operator"}')
    monkeypatch.setenv("SOVEREIGN_JEV_MODE", "live")
    monkeypatch.setenv("SOVEREIGN_JEV_ALLOWED_TENANTS", "tenant-a")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("SOVEREIGN_JEV_MODEL", raising=False)
    client = TestClient(from_environment())
    ready = client.get("/health/ready").json()
    assert ready["judgment_provider"] == "DisabledJudgmentProvider"


def test_phase4_fixture_comparison_is_reproducible(tmp_path):
    model_dir = Path(__file__).resolve().parents[1] / "results" / "phase2-v1"
    first = evaluate(model_dir, tmp_path / "phase4")
    second = evaluate(model_dir, tmp_path / "phase4")
    assert first == second
    assert first["n_episodes"] == 100
    assert first["evidence"] == "SIMULATION_ONLY_FIXTURE_PROXY_NOT_JEV"
    assert first["hybrid_advisory_only"]["same_actions_as_classic_ml"] is True
    assert first["live_jev_accuracy"] is None
