"""Behavioral checks for the offline multi-tier allocation boundary."""

import pytest

from sovereign_maas.domain import Tier
from sovereign_maas.subscription_optimizer import (
    PodForecast,
    SubscriptionService,
    allowed_options,
    optimize,
)


def option(replicas: int, breach: float, ttr: float = 2.0) -> PodForecast:
    return PodForecast(replicas, breach, ttr, 3.0, 1 - breach)


def service(
    name: str,
    tier: Tier,
    current: int,
    options: tuple[PodForecast, ...],
    *,
    ttv: float = 30.0,
    age: float = 1.0,
    incident: bool = False,
) -> SubscriptionService:
    return SubscriptionService(name, tier, current, 4, 0.5, ttv, age, False, incident, options)


def test_exact_budget_allocation_prefers_gold_marginal_benefit() -> None:
    gold = service("gold", Tier.GOLD, 2, (option(2, 0.09), option(3, 0.02)))
    silver = service("silver", Tier.SILVER, 1, (option(1, 0.20), option(2, 0.10)))
    bronze = service("bronze", Tier.BRONZE, 1, (option(1, 0.35), option(2, 0.10)))
    result = optimize((silver, bronze, gold), pod_budget=5)
    assert result.targets == (("bronze", 1), ("gold", 3), ("silver", 1))
    assert result.pod_count == 5
    assert result.considered == 4


def test_scale_down_requires_time_to_recover_before_early_breach() -> None:
    risky = service("bronze", Tier.BRONZE, 2, (option(1, 0.20), option(2, 0.10)), ttv=4.0)
    assert tuple(o.target_replicas for o in allowed_options(risky)) == (2,)
    safe = service("bronze", Tier.BRONZE, 2, (option(1, 0.20), option(2, 0.10)), ttv=20.0)
    assert tuple(o.target_replicas for o in allowed_options(safe)) == (1, 2)


def test_proactive_scale_out_must_finish_before_ttv() -> None:
    late = service("silver", Tier.SILVER, 1, (option(1, 0.20), option(2, 0.10)), ttv=4.0)
    assert tuple(o.target_replicas for o in allowed_options(late)) == (1,)
    incident = service("silver", Tier.SILVER, 1, (option(1, 0.20), option(2, 0.10)), ttv=0, incident=True)
    assert tuple(o.target_replicas for o in allowed_options(incident)) == (1, 2)


def test_stale_or_ood_forecast_keeps_current_allocation() -> None:
    stale = service("silver", Tier.SILVER, 2, (option(1, 0.1), option(2, 0.2)), age=31)
    assert tuple(o.target_replicas for o in allowed_options(stale)) == (2,)
    ood = SubscriptionService(
        "silver", Tier.SILVER, 2, 4, 0.5, 30, 1, True, False, (option(1, 0.1), option(2, 0.2))
    )
    assert tuple(o.target_replicas for o in allowed_options(ood)) == (2,)


def test_gold_floor_and_tier_probability_gate() -> None:
    gold = service("gold", Tier.GOLD, 2, (option(1, 0.01), option(2, 0.09), option(3, 0.20)))
    assert tuple(o.target_replicas for o in allowed_options(gold)) == (2,)


def test_infeasible_capacity_is_explicit() -> None:
    gold = service("gold", Tier.GOLD, 2, (option(2, 0.09),))
    silver = service("silver", Tier.SILVER, 1, (option(1, 0.20),))
    with pytest.raises(ValueError, match="POD_BUDGET_INFEASIBLE"):
        optimize((gold, silver), pod_budget=2)


def test_unsafe_forecast_is_not_silently_optimized() -> None:
    gold = service("gold", Tier.GOLD, 2, (option(2, 0.30),))
    with pytest.raises(ValueError, match="NO_TIER_SAFE_ALLOCATION"):
        optimize((gold,), pod_budget=4)


def test_invalid_probability_is_rejected() -> None:
    bronze = service("bronze", Tier.BRONZE, 1, (option(1, 1.2),))
    with pytest.raises(ValueError, match="invalid forecast probability"):
        optimize((bronze,), pod_budget=4)


def test_service_svrs_is_not_mistaken_for_probability() -> None:
    gold = SubscriptionService("gold", Tier.GOLD, 2, 4, 2.7, 30, 1, False, False, (option(2, 0.09),))
    assert optimize((gold,), pod_budget=2).targets == (("gold", 2),)


def test_search_space_is_bounded() -> None:
    services = tuple(
        service(f"bronze-{i}", Tier.BRONZE, 1, (option(1, 0.30), option(2, 0.10))) for i in range(8)
    )
    with pytest.raises(ValueError, match="SEARCH_SPACE_TOO_LARGE"):
        optimize(services, pod_budget=16, max_combinations=100)
