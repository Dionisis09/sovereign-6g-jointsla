"""Strict, versioned contracts for the local orchestration slice."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Tier(StrEnum):
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"


class ActionKind(StrEnum):
    SCALE_OUT = "scale_out"
    MIGRATE = "migrate"
    NOOP = "noop"


class TypedIntent(StrictModel):
    service_name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
    tier: Tier
    latency_p95_ms: float = Field(gt=0, le=1000)
    minimum_model_quality: float = Field(ge=0, le=1)
    max_replicas: int = Field(ge=1, le=4)
    allowed_regions: tuple[str, ...] = Field(min_length=1)
    allowed_actions: tuple[ActionKind, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def supported_scope(self) -> "TypedIntent":
        if len(set(self.allowed_regions)) != len(self.allowed_regions):
            raise ValueError("duplicate regions")
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("duplicate actions")
        if not set(self.allowed_regions) <= {"eu-gr", "eu-de"}:
            raise ValueError("unsupported region")
        if "eu-gr" not in self.allowed_regions:
            raise ValueError("initial simulated placement requires eu-gr residency")
        if self.minimum_model_quality > 0.95:
            raise ValueError("local simulated model quality is 0.95")
        return self


class ServiceBundle(StrictModel):
    schema_version: int = 1
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    created_at: datetime = Field(default_factory=utc_now)
    intent: TypedIntent
    model_id: str = "simulated-vision-small-v1"
    evidence: str = "SIMULATED"


class TopologyNode(StrictModel):
    id: str
    region: str
    network_ms: float = Field(ge=0)
    replica_capacity: int = Field(ge=0)


class TelemetrySnapshot(StrictModel):
    schema_version: int = 1
    id: str = Field(default_factory=lambda: str(uuid4()))
    seed: int = Field(ge=0)
    observed_at: datetime = Field(default_factory=utc_now)
    scenario_version: str = "phase1-queue-v1"
    evidence: str = "SIMULATED"
    active_node: str = "edge-a"
    replicas: int = 1
    queue_depth: int = Field(ge=0)
    arrival_rps: float = Field(ge=0)
    cycle_ms: float = Field(gt=0)
    observed_p95_ms: float = Field(ge=0)
    nodes: tuple[TopologyNode, ...]


class CandidateAction(StrictModel):
    id: str
    source: str
    kind: ActionKind
    target_node: str
    target_replicas: int
    ttr_high_s: float = Field(ge=0)
    post_p95_rule_ms: float = Field(ge=0)
    rule_version: str = "phase1-rules-v1"
    evidence: str = "SIMULATED_RULE"


class Rejection(StrictModel):
    candidate_id: str
    reasons: tuple[str, ...]


class DecisionRecord(StrictModel):
    policy_version: str = "phase1-policy-v1"
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    model_version: str | None = None
    prediction_source: str = "SIMULATED_RULE"
    status: str
    selected_candidate_id: str
    ttv_low_s: float | None
    recovery_slack_s: float | None
    rejected: tuple[Rejection, ...]
    reasons: tuple[str, ...]


class ForecastBundle(StrictModel):
    schema_version: int = 1
    snapshot_id: str
    service_id: str
    valid_until: datetime
    model_version: str
    dataset_sha256: str
    evidence: Literal["SIMULATION_TRAINED"] = "SIMULATION_TRAINED"
    calibration: str = "sigmoid-validation"
    breach_probability_12s: float = Field(ge=0, le=1)
    ttv_q10_s: float | None = Field(default=None, ge=0)
    ttr_q90_s: dict[str, float]
    post_sla_probability: dict[str, float]
    ood: bool = False

    @model_validator(mode="after")
    def valid_candidate_values(self) -> "ForecastBundle":
        if any(value < 0 for value in self.ttr_q90_s.values()):
            raise ValueError("negative TTR")
        if any(not 0 <= value <= 1 for value in self.post_sla_probability.values()):
            raise ValueError("post-SLA probability outside [0,1]")
        if self.valid_until.tzinfo is None:
            raise ValueError("valid_until must have a timezone")
        return self


class JudgmentRecord(StrictModel):
    """Advisory only; values cannot satisfy deterministic policy predicates."""

    schema_version: int = 1
    source: Literal["DISABLED", "FIXTURE", "LIVE"]
    status: Literal["DISABLED", "AVAILABLE", "UNAVAILABLE"]
    snapshot_id: str
    candidate_ids: tuple[str, ...]
    model_version: str | None = None
    incident_class: str | None = None
    incident_confidence: float | None = Field(default=None, ge=0, le=1)
    urgency_score: float | None = Field(default=None, ge=0, le=3)
    urgency_confidence: float | None = Field(default=None, ge=0, le=1)
    review_probability: float | None = Field(default=None, ge=0, le=1)
    breach_probability_12s: float | None = Field(default=None, ge=0, le=1)
    ttv_bin: str | None = None
    ttv_confidence: float | None = Field(default=None, ge=0, le=1)
    candidate_risk_score: dict[str, float] = Field(default_factory=dict)
    candidate_risk_confidence: dict[str, float] = Field(default_factory=dict)
    candidate_ttr_bin: dict[str, str] = Field(default_factory=dict)
    candidate_post_sla_probability: dict[str, float] = Field(default_factory=dict)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    reason: str | None = None

    @model_validator(mode="after")
    def consistent_advisory(self) -> "JudgmentRecord":
        if self.status == "AVAILABLE":
            if self.incident_class not in {
                "traffic_spike",
                "resource_exhaustion",
                "node_failure",
                "network_congestion",
                "model_regression",
                "unknown",
            }:
                raise ValueError("invalid incident class")
            if self.ttv_bin not in {"within_4s", "within_12s", "beyond_12s", "unknown"}:
                raise ValueError("invalid TTV bin")
            if any(
                value is None
                for value in (
                    self.incident_confidence,
                    self.urgency_score,
                    self.urgency_confidence,
                    self.review_probability,
                    self.breach_probability_12s,
                    self.ttv_confidence,
                )
            ):
                raise ValueError("incomplete judgment")
            expected = set(self.candidate_ids)
            for values in (
                self.candidate_risk_score,
                self.candidate_risk_confidence,
                self.candidate_ttr_bin,
                self.candidate_post_sla_probability,
            ):
                if set(values) != expected:
                    raise ValueError("candidate judgment mismatch")
            if any(not 0 <= value <= 3 for value in self.candidate_risk_score.values()):
                raise ValueError("invalid candidate risk score")
            if any(not 0 <= value <= 1 for value in self.candidate_risk_confidence.values()):
                raise ValueError("invalid candidate risk confidence")
            if any(not 0 <= value <= 1 for value in self.candidate_post_sla_probability.values()):
                raise ValueError("invalid candidate post-SLA probability")
            if any(
                value not in {"under_2s", "under_5s", "over_5s", "unknown"}
                for value in self.candidate_ttr_bin.values()
            ):
                raise ValueError("invalid candidate TTR bin")
        return self


class Verification(StrictModel):
    evidence: str = "SIMULATED"
    measured_p95_ms: float
    slo_met: bool
    final_replicas: int
    final_node: str


class SimulationRun(StrictModel):
    schema_version: int = 1
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    service_id: str
    created_at: datetime = Field(default_factory=utc_now)
    seed: int
    snapshot: TelemetrySnapshot
    candidates: tuple[CandidateAction, ...]
    decision: DecisionRecord
    verification: Verification
    forecast: ForecastBundle | None = None
    judgment: JudgmentRecord | None = None


class RunRequest(StrictModel):
    service_id: str
    seed: int = Field(ge=0, le=1_000_000)


class NaturalIntentRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000)


class ParsedIntent(StrictModel):
    intent: TypedIntent
    parser: str
    evidence: str = "EXPLICIT_REQUEST_TEXT"


class WorkflowRequest(NaturalIntentRequest):
    seed: int = Field(ge=0, le=1_000_000)


class ApprovalRequest(StrictModel):
    approved: bool


class WorkflowRecord(StrictModel):
    id: str
    tenant_id: str
    status: Literal["PENDING", "NEEDS_APPROVAL", "VERIFIED", "REJECTED", "FAILED"]
    parser: str
    intent: TypedIntent | None = None
    service_id: str | None = None
    selected_candidate_id: str | None = None
    decision: DecisionRecord | None = None
    run_id: str | None = None
    citations: tuple[str, ...] = ()
    reason: str | None = None
    judgment: JudgmentRecord | None = None
