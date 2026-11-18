"""Offline, exact small-budget pod allocation from explicit per-action forecasts.

This module never actuates Kubernetes. Forecast probabilities are inputs, not
inferred from the uncalibrated JointSLA service risk (SVRS) or router proxy.
"""

from dataclasses import dataclass
from itertools import product
from math import isfinite

from .domain import Tier


@dataclass(frozen=True)
class TierPolicy:
    minimum_replicas: int
    maximum_breach_probability: float
    breach_weight: float


DEFAULT_TIERS = {
    Tier.GOLD: TierPolicy(2, 0.10, 10.0),
    Tier.SILVER: TierPolicy(1, 0.25, 4.0),
    Tier.BRONZE: TierPolicy(1, 0.40, 1.0),
}


@dataclass(frozen=True)
class PodForecast:
    """Predictions for one target replica count on the same forecast horizon."""

    target_replicas: int
    post_breach_probability: float
    ttr_q90_s: float
    ready_s: float
    post_slo_probability: float


@dataclass(frozen=True)
class SubscriptionService:
    service_id: str
    tier: Tier
    current_replicas: int
    max_replicas: int
    risk_score: float
    ttv_q10_s: float
    forecast_age_s: float
    ood: bool
    incident: bool
    options: tuple[PodForecast, ...]


@dataclass(frozen=True)
class Allocation:
    targets: tuple[tuple[str, int], ...]
    score: float
    pod_count: int
    considered: int


def _check_service(service: SubscriptionService) -> None:
    if not service.service_id or service.current_replicas < 1 or service.max_replicas < 1:
        raise ValueError("invalid service identity or replica count")
    if service.current_replicas > service.max_replicas:
        raise ValueError("current replicas exceed service maximum")
    if service.risk_score < 0 or not isfinite(service.risk_score):
        raise ValueError("risk_score must be finite and nonnegative")
    if service.ttv_q10_s < 0 or not isfinite(service.ttv_q10_s):
        raise ValueError("invalid service TTV")
    if service.forecast_age_s < 0 or not isfinite(service.forecast_age_s):
        raise ValueError("invalid forecast age")
    if not service.options or len({o.target_replicas for o in service.options}) != len(service.options):
        raise ValueError("missing or duplicate replica options")
    if service.current_replicas not in {o.target_replicas for o in service.options}:
        raise ValueError("current allocation forecast is required")
    for option in service.options:
        values = (
            option.post_breach_probability,
            option.ttr_q90_s,
            option.ready_s,
            option.post_slo_probability,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("nonfinite forecast")
        if not 0 <= option.post_breach_probability <= 1 or not 0 <= option.post_slo_probability <= 1:
            raise ValueError("invalid forecast probability")
        if min(option.ttr_q90_s, option.ready_s) < 0:
            raise ValueError("negative forecast time")


def allowed_options(
    service: SubscriptionService,
    *,
    tiers: dict[Tier, TierPolicy] = DEFAULT_TIERS,
    max_forecast_age_s: float = 30.0,
    slack_guard_s: float = 0.5,
) -> tuple[PodForecast, ...]:
    """Return only actions allowed by tier, fresh forecast and recovery timing.

    Keep-current remains available when the forecast is stale or out of domain.
    A strict tier target can be infeasible; optimize() reports that explicitly.
    """
    _check_service(service)
    policy = tiers[service.tier]
    current = next(o for o in service.options if o.target_replicas == service.current_replicas)
    if service.ood or service.forecast_age_s > max_forecast_age_s:
        return (current,)
    accepted = []
    for option in service.options:
        target = option.target_replicas
        if not policy.minimum_replicas <= target <= service.max_replicas:
            continue
        if option.post_breach_probability > policy.maximum_breach_probability:
            continue
        if option.post_slo_probability < 1 - policy.maximum_breach_probability:
            continue
        if target < service.current_replicas:
            # A downscale is reversible only if recovery can precede early breach.
            if service.incident or service.ttv_q10_s <= option.ready_s + option.ttr_q90_s + slack_guard_s:
                continue
        elif (
            target > service.current_replicas
            and not service.incident
            and service.ttv_q10_s <= option.ready_s + option.ttr_q90_s + slack_guard_s
        ):
            # If already too late, keep the action available for recovery only when incident.
            continue
        accepted.append(option)
    return tuple(sorted(accepted, key=lambda o: o.target_replicas))


def optimize(
    services: tuple[SubscriptionService, ...],
    *,
    pod_budget: int,
    pod_price: float = 0.05,
    change_price: float = 0.02,
    tiers: dict[Tier, TierPolicy] = DEFAULT_TIERS,
    max_combinations: int = 100_000,
) -> Allocation:
    """Enumerate all valid small allocations and return the exact minimum score.

    The optimum is conditional on supplied forecasts, tier policy and prices.
    It is not an end-to-end SLA guarantee or a learned global optimum.
    """
    if (
        not services
        or pod_budget < 1
        or max_combinations < 1
        or not all(isfinite(value) and value >= 0 for value in (pod_price, change_price))
    ):
        raise ValueError("invalid optimization input")
    if len({service.service_id for service in services}) != len(services):
        raise ValueError("duplicate service ID")
    ordered = tuple(sorted(services, key=lambda s: s.service_id))
    choices = tuple(allowed_options(s, tiers=tiers) for s in ordered)
    if any(not options for options in choices):
        raise ValueError("NO_TIER_SAFE_ALLOCATION")
    search_space = 1
    for options in choices:
        search_space *= len(options)
        if search_space > max_combinations:
            raise ValueError("SEARCH_SPACE_TOO_LARGE")
    best: tuple[float, int, float, tuple[int, ...]] | None = None
    considered = 0
    for combination in product(*choices):
        pods = sum(option.target_replicas for option in combination)
        if pods > pod_budget:
            continue
        considered += 1
        score = (
            sum(
                tiers[service.tier].breach_weight * option.post_breach_probability
                + change_price * abs(option.target_replicas - service.current_replicas)
                for service, option in zip(ordered, combination, strict=True)
            )
            + pod_price * pods
        )
        target = tuple(option.target_replicas for option in combination)
        # The uncalibrated JointSLA service risk (SVRS) influences only exact ties:
        # avoid taking capacity away from a higher-risk service first.
        downscale_risk = sum(
            service.risk_score * max(0, service.current_replicas - option.target_replicas)
            for service, option in zip(ordered, combination, strict=True)
        )
        candidate = (round(score, 12), pods, downscale_risk, target)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise ValueError("POD_BUDGET_INFEASIBLE")
    return Allocation(
        targets=tuple(zip((s.service_id for s in ordered), best[3], strict=True)),
        score=best[0],
        pod_count=best[1],
        considered=considered,
    )
