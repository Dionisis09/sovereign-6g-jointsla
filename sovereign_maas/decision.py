"""JointSLA recommendation adapter and deterministic local authority."""

from datetime import UTC, datetime

from prototype.controller import plan

from .domain import (
    ActionKind,
    CandidateAction,
    DecisionRecord,
    ForecastBundle,
    Rejection,
    ServiceBundle,
    TelemetrySnapshot,
)
from .forecast import invalid_reason
from .simulation import candidate_post_latency, ttv_low_rule


def propose(bundle: ServiceBundle, snapshot: TelemetrySnapshot) -> tuple[CandidateAction, ...]:
    state = {"ready": True, "queue": snapshot.queue_depth, "busy": False, "cycle_ms": snapshot.cycle_ms}
    recommendation = plan(
        [state],
        snapshot.arrival_rps,
        bundle.intent.latency_p95_ms,
        cold_seconds=10.0,
        max_replicas=bundle.intent.max_replicas,
        tier=bundle.intent.tier.value,
    )
    scale_target = max(snapshot.replicas, recommendation.desired_replicas)
    return (
        CandidateAction(
            id="jointsla-scale",
            source="joint_sla_v2_warm_headroom",
            kind=ActionKind.SCALE_OUT,
            target_node="edge-a",
            target_replicas=scale_target,
            ttr_high_s=1.0,
            post_p95_rule_ms=candidate_post_latency(snapshot, ActionKind.SCALE_OUT, scale_target),
        ),
        CandidateAction(
            id="heuristic-migrate",
            source="heuristic",
            kind=ActionKind.MIGRATE,
            target_node="cloud-a",
            target_replicas=1,
            ttr_high_s=2.0,
            post_p95_rule_ms=candidate_post_latency(snapshot, ActionKind.MIGRATE, 1),
        ),
        CandidateAction(
            id="baseline-noop",
            source="baseline",
            kind=ActionKind.NOOP,
            target_node="edge-a",
            target_replicas=1,
            ttr_high_s=0.0,
            post_p95_rule_ms=candidate_post_latency(snapshot, ActionKind.NOOP, 1),
        ),
    )


def decide(
    bundle: ServiceBundle,
    snapshot: TelemetrySnapshot,
    candidates: tuple[CandidateAction, ...],
    forecast: ForecastBundle | None = None,
    require_forecast: bool = False,
) -> DecisionRecord:
    age_s = (datetime.now(UTC) - snapshot.observed_at).total_seconds()
    model_mode = require_forecast or forecast is not None
    if model_mode:
        reason = invalid_reason(forecast, bundle, snapshot, candidates)
        if reason is not None:
            return DecisionRecord(
                policy_version="phase2-policy-v1",
                status="SIMULATED",
                selected_candidate_id="baseline-noop",
                ttv_low_s=None,
                recovery_slack_s=None,
                rejected=tuple(
                    Rejection(candidate_id=candidate.id, reasons=(reason,))
                    for candidate in candidates
                    if candidate.kind != ActionKind.NOOP
                ),
                reasons=(reason, "NO_SAFE_AUTOMATED_ACTION"),
                prediction_source="SIMULATION_TRAINED_UNUSABLE",
            )
    ttv = forecast.ttv_q10_s if model_mode and forecast is not None else ttv_low_rule(bundle, snapshot)
    if ttv is None:
        raise AssertionError("validated forecast requires TTV while healthy")
    incident = snapshot.observed_p95_ms >= bundle.intent.latency_p95_ms
    rejected: list[Rejection] = []
    eligible: list[tuple[float, float, CandidateAction, float]] = []
    for candidate in candidates:
        reasons: list[str] = []
        node = next(n for n in snapshot.nodes if n.id == candidate.target_node)
        if age_s > 30 or age_s < -1:
            reasons.append("STALE_TELEMETRY")
        if candidate.kind != ActionKind.NOOP and candidate.kind not in bundle.intent.allowed_actions:
            reasons.append("ACTION_NOT_ALLOWED")
        if node.region not in bundle.intent.allowed_regions:
            reasons.append("RESIDENCY_DENIED")
        if candidate.target_replicas > min(bundle.intent.max_replicas, node.replica_capacity):
            reasons.append("CAPACITY_DENIED")
        if candidate.kind == ActionKind.SCALE_OUT and candidate.target_replicas <= snapshot.replicas:
            reasons.append("NO_SCALE_CHANGE")
        if bundle.intent.minimum_model_quality > 0.95:
            reasons.append("QUALITY_DENIED")
        ttr = (
            forecast.ttr_q90_s[candidate.id] if model_mode and forecast is not None else candidate.ttr_high_s
        )
        slack = ttv - ttr - 0.5
        if candidate.kind != ActionKind.NOOP:
            if model_mode and forecast is not None:
                if forecast.breach_probability_12s < 0.3 and not incident:
                    reasons.append("LOW_PREDICTED_BREACH_RISK")
                if forecast.post_sla_probability[candidate.id] < 0.8:
                    reasons.append("POST_SLA_PROBABILITY_TOO_LOW")
            if not incident and slack <= 0:
                reasons.append("INSUFFICIENT_RECOVERY_SLACK")
            if candidate.post_p95_rule_ms > bundle.intent.latency_p95_ms:
                reasons.append("POST_SLO_RULE_FAIL")
        if reasons:
            rejected.append(Rejection(candidate_id=candidate.id, reasons=tuple(reasons)))
        elif candidate.kind != ActionKind.NOOP:
            success = (
                forecast.post_sla_probability[candidate.id] if model_mode and forecast is not None else 1.0
            )
            eligible.append((-success, candidate.post_p95_rule_ms, candidate, slack))
    if eligible:
        _, _, chosen, slack = min(eligible, key=lambda row: (row[0], row[1], row[2].id))
        return DecisionRecord(
            policy_version="phase2-policy-v1" if model_mode else "phase1-policy-v1",
            status="SIMULATED",
            selected_candidate_id=chosen.id,
            ttv_low_s=ttv,
            recovery_slack_s=slack,
            rejected=tuple(rejected),
            reasons=("INCIDENT_RECOVERY" if incident else "ELIGIBLE_LOWEST_POST_P95_RULE",),
            model_version=forecast.model_version if forecast is not None else None,
            prediction_source="SIMULATION_TRAINED" if model_mode else "SIMULATED_RULE",
        )
    return DecisionRecord(
        policy_version="phase2-policy-v1" if model_mode else "phase1-policy-v1",
        status="SIMULATED",
        selected_candidate_id="baseline-noop",
        ttv_low_s=ttv,
        recovery_slack_s=None,
        rejected=tuple(rejected),
        reasons=("NO_SAFE_AUTOMATED_ACTION",),
        model_version=forecast.model_version if forecast is not None else None,
        prediction_source="SIMULATION_TRAINED" if model_mode else "SIMULATED_RULE",
    )
