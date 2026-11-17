"""TypeSafe System One advisory adapter. No output here grants action authority."""

import re
import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .domain import ActionKind, CandidateAction, JudgmentRecord, ServiceBundle, TelemetrySnapshot
from .simulation import ttv_low_rule

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
INCIDENT_CLASSES = (
    "traffic_spike",
    "resource_exhaustion",
    "node_failure",
    "network_congestion",
    "model_regression",
    "unknown",
)
TTV_BINS = ("within_4s", "within_12s", "beyond_12s", "unknown")
TTR_BINS = ("under_2s", "under_5s", "over_5s", "unknown")
URGENCY_LEVELS = ("low", "medium", "high", "critical")
RISK_LEVELS = ("low", "medium", "high", "critical")
MAX_CANDIDATES = 3


class JudgmentProvider(Protocol):
    def judge(
        self,
        service: ServiceBundle,
        snapshot: TelemetrySnapshot,
        candidates: tuple[CandidateAction, ...],
    ) -> JudgmentRecord: ...


def sanitize_state(
    service: ServiceBundle,
    snapshot: TelemetrySnapshot,
    candidates: tuple[CandidateAction, ...],
) -> dict[str, Any]:
    """Allowlist numeric simulator features; no tenant, service name, tokens or free text."""
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("judgment candidate count out of bounds")
    if any(not re.fullmatch(r"[a-z0-9-]{1,64}", item.id) for item in candidates):
        raise ValueError("unsafe candidate identifier")
    return {
        "observed_p95_ms": snapshot.observed_p95_ms,
        "slo_p95_ms": service.intent.latency_p95_ms,
        "queue_depth": snapshot.queue_depth,
        "arrival_rps": snapshot.arrival_rps,
        "cycle_ms": snapshot.cycle_ms,
        "replicas": snapshot.replicas,
        "network_ms": next(node.network_ms for node in snapshot.nodes if node.id == snapshot.active_node),
        "candidates": [
            {
                "id": item.id,
                "kind": item.kind.value,
                "target_replicas": item.target_replicas,
                "estimated_ttr_s": item.ttr_high_s,
                "estimated_post_p95_ms": item.post_p95_rule_ms,
            }
            for item in candidates
        ],
        "evidence": "SIMULATED",
    }


class DisabledJudgmentProvider:
    def judge(
        self,
        service: ServiceBundle,
        snapshot: TelemetrySnapshot,
        candidates: tuple[CandidateAction, ...],
    ) -> JudgmentRecord:
        return JudgmentRecord(
            source="DISABLED",
            status="DISABLED",
            snapshot_id=snapshot.id,
            candidate_ids=tuple(item.id for item in candidates),
            reason="JEV_DISABLED",
        )


class FixtureJudgmentProvider:
    """Deterministic integration proxy; output is never a measurement of Jev."""

    def judge(
        self,
        service: ServiceBundle,
        snapshot: TelemetrySnapshot,
        candidates: tuple[CandidateAction, ...],
    ) -> JudgmentRecord:
        sanitize_state(service, snapshot, candidates)
        ttv = ttv_low_rule(service, snapshot)
        ttv_bin = "within_4s" if ttv <= 4 else "within_12s" if ttv <= 12 else "beyond_12s"
        incident = "traffic_spike" if snapshot.arrival_rps > 1000 / snapshot.cycle_ms else "unknown"
        ids = tuple(item.id for item in candidates)
        return JudgmentRecord(
            source="FIXTURE",
            status="AVAILABLE",
            model_version="fixture-rules-v1",
            snapshot_id=snapshot.id,
            candidate_ids=ids,
            incident_class=incident,
            incident_confidence=0.0,
            urgency_score=2.0 if ttv <= 4 else 1.0,
            urgency_confidence=0.0,
            review_probability=1.0,
            breach_probability_12s=0.8 if ttv <= 12 else 0.2,
            ttv_bin=ttv_bin,
            ttv_confidence=0.0,
            candidate_risk_score={
                item.id: 2.0
                if item.kind == ActionKind.MIGRATE
                else 1.0
                if item.kind == ActionKind.SCALE_OUT
                else 0.0
                for item in candidates
            },
            candidate_risk_confidence={item.id: 0.0 for item in candidates},
            candidate_ttr_bin={
                item.id: "under_2s"
                if item.ttr_high_s <= 2
                else "under_5s"
                if item.ttr_high_s <= 5
                else "over_5s"
                for item in candidates
            },
            candidate_post_sla_probability={
                item.id: 0.8 if item.post_p95_rule_ms <= service.intent.latency_p95_ms else 0.2
                for item in candidates
            },
            reason="SIMULATED_FIXTURE_NOT_JEV",
        )


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class _Noul(_WireModel):
    type: Literal["noul"]
    noul: Probability


class _Choice(_WireModel):
    type: Literal["choice"]
    choice: str
    confidence: Probability
    probabilities: dict[str, Probability]

    @model_validator(mode="after")
    def valid_distribution(self) -> "_Choice":
        if self.choice not in self.probabilities or not 0.98 <= sum(self.probabilities.values()) <= 1.02:
            raise ValueError("invalid choice distribution")
        return self


class _Score(_WireModel):
    type: Literal["score"]
    score: float
    confidence: Probability
    legend: dict[str, str]
    probabilities: dict[str, Probability]

    @model_validator(mode="after")
    def valid_distribution(self) -> "_Score":
        keys = {str(index) for index in range(len(self.legend))}
        if set(self.legend) != keys or set(self.probabilities) != keys:
            raise ValueError("invalid score levels")
        if not 0.98 <= sum(self.probabilities.values()) <= 1.02:
            raise ValueError("invalid score distribution")
        if not 0 <= self.score <= len(keys) - 1:
            raise ValueError("invalid score")
        expected = sum(index * self.probabilities[str(index)] for index in range(len(keys)))
        if abs(self.score - expected) > 0.06:
            raise ValueError("score differs from probability-weighted levels")
        return self


class _Usage(_WireModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class _Response(_WireModel):
    model: str = Field(min_length=1)
    answers: dict[str, dict[str, Any]]
    usage: _Usage


def _choice(raw: dict[str, Any], options: tuple[str, ...]) -> _Choice:
    answer = _Choice.model_validate(raw)
    if set(answer.probabilities) != set(options):
        raise ValueError("choice options mismatch")
    return answer


def _score(raw: dict[str, Any], levels: tuple[str, ...]) -> _Score:
    answer = _Score.model_validate(raw)
    if answer.legend != {str(index): value for index, value in enumerate(levels)}:
        raise ValueError("score legend mismatch")
    return answer


def _questions(candidates: tuple[CandidateAction, ...]) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {
        "incident_class": {
            "type": "choice",
            "instructions": "Which incident class best matches this simulated state?",
            "criteria": {
                "traffic_spike": "Arrivals exceed current service capacity",
                "resource_exhaustion": "Insufficient computing capacity",
                "node_failure": "A serving node has failed",
                "network_congestion": "Network delay dominates",
                "model_regression": "Model quality or behavior regressed",
                "unknown": "Insufficient evidence for another class",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is remediation?",
            "criteria": list(URGENCY_LEVELS),
        },
        "requires_human_review": {"type": "noul", "instructions": "Does this state warrant human review?"},
        "breach_12s": {"type": "noul", "instructions": "Will p95 exceed the stated SLO within 12 seconds?"},
        "ttv_bin": {
            "type": "choice",
            "instructions": "If healthy now, when might first SLO breach occur?",
            "criteria": {
                "within_4s": "Within 4 seconds",
                "within_12s": "After 4 and within 12 seconds",
                "beyond_12s": "After 12 seconds",
                "unknown": "Insufficient evidence or already breached",
            },
        },
    }
    for item in candidates:
        questions[f"risk_{item.id}"] = {
            "type": "score",
            "instructions": f"How risky is candidate {item.id}?",
            "criteria": list(RISK_LEVELS),
        }
        questions[f"ttr_{item.id}"] = {
            "type": "choice",
            "instructions": f"How long might candidate {item.id} take to recover?",
            "criteria": {
                "under_2s": "At most 2 seconds",
                "under_5s": "More than 2 and at most 5 seconds",
                "over_5s": "More than 5 seconds",
                "unknown": "Insufficient evidence",
            },
        }
        questions[f"post_{item.id}"] = {
            "type": "noul",
            "instructions": f"Would candidate {item.id} meet the stated p95 SLO after recovery?",
        }
    return questions


class TypeSafeJevProvider:
    """Optional HTTPX client for the documented TypeSafe System One wire contract."""

    def __init__(
        self,
        api_key: str,
        model: str,
        allowed_tenants: set[str],
        client: httpx.Client | None = None,
    ):
        if not api_key or not model or not allowed_tenants:
            raise ValueError("Jev key, model and tenant allowlist are required")
        self.api_key = api_key
        self.model = model
        self.allowed_tenants = frozenset(allowed_tenants)
        self.client = client or httpx.Client(timeout=5.0)
        self._lock = threading.Lock()
        self._requests: deque[float] = deque()
        self._failures = 0
        self._open_until = 0.0

    def _reserve(self) -> str | None:
        now = time.monotonic()
        with self._lock:
            if now < self._open_until:
                return "CIRCUIT_OPEN"
            while self._requests and self._requests[0] <= now - 60:
                self._requests.popleft()
            if len(self._requests) >= 60:
                return "RATE_LIMITED_LOCALLY"
            self._requests.append(now)
        return None

    def _failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= 3:
                self._open_until = time.monotonic() + 30

    def _unavailable(
        self,
        snapshot: TelemetrySnapshot,
        candidates: tuple[CandidateAction, ...],
        reason: str,
        latency_ms: float = 0.0,
    ) -> JudgmentRecord:
        return JudgmentRecord(
            source="LIVE",
            status="UNAVAILABLE",
            snapshot_id=snapshot.id,
            candidate_ids=tuple(item.id for item in candidates),
            model_version=self.model,
            latency_ms=latency_ms,
            reason=reason,
        )

    def judge(
        self,
        service: ServiceBundle,
        snapshot: TelemetrySnapshot,
        candidates: tuple[CandidateAction, ...],
    ) -> JudgmentRecord:
        if service.tenant_id not in self.allowed_tenants:
            return self._unavailable(snapshot, candidates, "TENANT_EGRESS_DENIED")
        age_s = (datetime.now(UTC) - snapshot.observed_at).total_seconds()
        if age_s > 30 or age_s < -1:
            return self._unavailable(snapshot, candidates, "STALE_TELEMETRY")
        try:
            state = sanitize_state(service, snapshot, candidates)
        except ValueError:
            return self._unavailable(snapshot, candidates, "UNSAFE_STATE")
        reason = self._reserve()
        if reason is not None:
            return self._unavailable(snapshot, candidates, reason)
        questions = _questions(candidates)
        started = time.perf_counter()
        for attempt in range(2):
            try:
                response = self.client.post(
                    "https://api.typesafe.ai/v1/systemone",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "state": state, "questions": questions},
                )
                if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                    time.sleep(0.1)
                    continue
                response.raise_for_status()
                payload = _Response.model_validate(response.json())
                if set(payload.answers) != set(questions):
                    raise ValueError("answer names mismatch")
                incident = _choice(payload.answers["incident_class"], INCIDENT_CLASSES)
                urgency = _score(payload.answers["urgency"], URGENCY_LEVELS)
                review = _Noul.model_validate(payload.answers["requires_human_review"])
                breach = _Noul.model_validate(payload.answers["breach_12s"])
                ttv = _choice(payload.answers["ttv_bin"], TTV_BINS)
                risk = {
                    item.id: _score(payload.answers[f"risk_{item.id}"], RISK_LEVELS) for item in candidates
                }
                ttr = {item.id: _choice(payload.answers[f"ttr_{item.id}"], TTR_BINS) for item in candidates}
                post = {
                    item.id: _Noul.model_validate(payload.answers[f"post_{item.id}"]) for item in candidates
                }
                record = JudgmentRecord(
                    source="LIVE",
                    status="AVAILABLE",
                    snapshot_id=snapshot.id,
                    candidate_ids=tuple(item.id for item in candidates),
                    model_version=payload.model,
                    incident_class=incident.choice,
                    incident_confidence=incident.confidence,
                    urgency_score=urgency.score,
                    urgency_confidence=urgency.confidence,
                    review_probability=review.noul,
                    breach_probability_12s=breach.noul,
                    ttv_bin=ttv.choice,
                    ttv_confidence=ttv.confidence,
                    candidate_risk_score={key: value.score for key, value in risk.items()},
                    candidate_risk_confidence={key: value.confidence for key, value in risk.items()},
                    candidate_ttr_bin={key: value.choice for key, value in ttr.items()},
                    candidate_post_sla_probability={key: value.noul for key, value in post.items()},
                    input_tokens=payload.usage.input_tokens,
                    output_tokens=payload.usage.output_tokens,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                with self._lock:
                    self._failures = 0
                return record
            except (httpx.HTTPError, ValueError, ValidationError):
                self._failure()
                return self._unavailable(
                    snapshot,
                    candidates,
                    "UPSTREAM_OR_SCHEMA_ERROR",
                    (time.perf_counter() - started) * 1000,
                )
        self._failure()
        return self._unavailable(
            snapshot,
            candidates,
            "UPSTREAM_OR_SCHEMA_ERROR",
            (time.perf_counter() - started) * 1000,
        )
