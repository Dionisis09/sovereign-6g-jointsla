"""One event schema and policy-independent immutable request tapes."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import Field, model_validator
from .contracts import Intent, StrictModel
from .reused import digest


class Config(StrictModel):
    intent: Intent
    duration_s: float = Field(gt=0)
    arrival_rate_rps: float = Field(gt=0)
    network_base_ms: float = Field(ge=0)
    network_jitter_ms: float = Field(ge=0)
    gateway_ms: float = Field(ge=0)
    v1_service_ms: float = Field(gt=0)
    v2_service_ms: float = Field(gt=0)
    v1_quality: float = Field(ge=0, le=1)
    v2_quality: float = Field(ge=0, le=1)
    request_timeout_ms: float = Field(gt=0)
    rollout_start_s: float = Field(ge=0)
    rollout_stage_hold_s: float = Field(gt=0)
    rollout_overhead_ms: float = Field(ge=0)
    rollout_disruption_s: float = Field(ge=0)
    stress_start_s: float = Field(ge=0)
    stress_end_s: float = Field(gt=0)
    tick_s: float = Field(gt=0)
    metric_window_s: float = Field(gt=0)
    local_inference_limit_ms: float = Field(gt=0)
    local_network_limit_ms: float = Field(gt=0)
    scale_high_utilization: float = Field(gt=0, le=1)
    scale_low_utilization: float = Field(ge=0, lt=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    load_stress_levels: tuple[float, float, float]
    network_stress_levels_ms: tuple[float, float, float]
    compound_load_levels: tuple[float, float, float]
    compound_network_levels_ms: tuple[float, float, float]

    @model_validator(mode="after")
    def coherent(self):
        if not self.rollout_start_s < self.stress_start_s < self.stress_end_s < self.duration_s:
            raise ValueError("require rollout < stress start < stress end < duration")
        if self.scale_low_utilization >= self.scale_high_utilization:
            raise ValueError("hysteresis low must be below high")
        if self.metric_window_s < self.tick_s:
            raise ValueError("measurement window must cover a tick")
        if abs(self.duration_s / self.tick_s - round(self.duration_s / self.tick_s)) > 1e-9:
            raise ValueError("duration must be a whole number of ticks")
        if len(set(self.seeds)) != len(self.seeds) or min(self.seeds) < 0:
            raise ValueError("unique nonnegative seeds required")
        if min(*self.load_stress_levels, *self.compound_load_levels) < 1:
            raise ValueError("stress multipliers must be >=1")
        if min(*self.network_stress_levels_ms, *self.compound_network_levels_ms) < 0:
            raise ValueError("network delays must be nonnegative")
        return self


class Event(StrictModel):
    time_s: float = Field(ge=0)
    load_multiplier: float | None = Field(default=None, gt=0)
    network_extra_delay_ms: float | None = Field(default=None, ge=0)
    rollout_enabled: bool | None = None
    capacity_reduction: float | None = Field(default=None, ge=0, lt=1)


class Scenario(StrictModel):
    family: Literal["S0", "S1", "S2", "S3"]
    level: int = Field(ge=0, le=3)
    rollout_enabled: bool = True
    events: tuple[Event, ...] = ()

    @model_validator(mode="after")
    def ordered(self):
        times = [e.time_s for e in self.events]
        if times != sorted(set(times)):
            raise ValueError("events must have unique increasing timestamps")
        return self

    def state_at(self, time_s):
        state = dict(load_multiplier=1., network_extra_delay_ms=0.,
                     rollout_enabled=self.rollout_enabled, capacity_reduction=0.)
        for event in self.events:
            if event.time_s > time_s:
                break
            state.update(event.model_dump(exclude_none=True, exclude={"time_s"}))
        return state


@dataclass(frozen=True)
class Request:
    request_id: int
    time_s: float
    version_draw: float
    service_factor: float
    network_draw: float


@dataclass(frozen=True)
class Tape:
    requests: tuple[Request, ...]
    sha256: str


def workload(config: Config, scenario: Scenario, seed: int) -> Tape:
    arrivals, models, services, network = [np.random.default_rng(s) for s in
                                          np.random.SeedSequence(seed).spawn(4)]
    maximum = max([1.] + [e.load_multiplier for e in scenario.events
                         if e.load_multiplier is not None])
    time_s, requests = 0., []
    while True:
        time_s += float(arrivals.exponential(1 / (config.arrival_rate_rps * maximum)))
        if time_s >= config.duration_s:
            break
        if arrivals.random() * maximum > scenario.state_at(time_s)["load_multiplier"]:
            continue
        requests.append(Request(len(requests), time_s, float(models.random()),
                                float(services.uniform(.8, 1.2)), float(network.random())))
    frozen = tuple(requests)
    return Tape(frozen, digest(frozen))


def matrix(config: Config):
    # Healthy low-load control: 10 rps, v2 mean utilization 0.18 per worker.
    yield Scenario(family="S0", level=0, events=(Event(time_s=0., load_multiplier=.25),))
    for family in ("S1", "S2", "S3"):
        for i in range(3):
            load = config.load_stress_levels[i] if family == "S1" else (
                config.compound_load_levels[i] if family == "S3" else 1.)
            delay = config.network_stress_levels_ms[i] if family == "S2" else (
                config.compound_network_levels_ms[i] if family == "S3" else 0.)
            yield Scenario(family=family, level=i + 1, events=(
                Event(time_s=config.stress_start_s, load_multiplier=load,
                      network_extra_delay_ms=delay),
                Event(time_s=config.stress_end_s, load_multiplier=1., network_extra_delay_ms=0.)))


def load_config(path="configs/phase0.json"):
    return Config.model_validate_json(Path(path).read_text(encoding="utf-8"))
