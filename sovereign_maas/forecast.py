"""Validated simulation-trained forecast contract and conservative freshness gate."""

from datetime import UTC, datetime
from typing import Protocol

from .domain import CandidateAction, ForecastBundle, ServiceBundle, TelemetrySnapshot


class ForecastProvider(Protocol):
    def predict(
        self, service: ServiceBundle, snapshot: TelemetrySnapshot, candidates: tuple[CandidateAction, ...]
    ) -> ForecastBundle: ...


def invalid_reason(
    forecast: ForecastBundle | None,
    service: ServiceBundle,
    snapshot: TelemetrySnapshot,
    candidates: tuple[CandidateAction, ...],
) -> str | None:
    if forecast is None:
        return "PREDICTION_MISSING"
    if forecast.snapshot_id != snapshot.id or forecast.service_id != service.id:
        return "PREDICTION_LINEAGE_MISMATCH"
    if forecast.ood:
        return "PREDICTION_OOD"
    if datetime.now(UTC) >= forecast.valid_until:
        return "PREDICTION_EXPIRED"
    ids = {candidate.id for candidate in candidates}
    if not ids <= forecast.ttr_q90_s.keys() or not ids <= forecast.post_sla_probability.keys():
        return "PREDICTION_INCOMPLETE"
    if snapshot.observed_p95_ms < service.intent.latency_p95_ms and forecast.ttv_q10_s is None:
        return "TTV_QUANTILE_UNAVAILABLE"
    return None
