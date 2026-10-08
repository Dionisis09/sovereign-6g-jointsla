"""Small, validated JSON protocol; all time parameters are explicit."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Config:
    trials: int = 30
    first_seed: int = 0
    slots: int = 100
    slot_seconds: float = .1
    node_count: int = 5
    service_count: int = 20
    burst_start: int = 20
    burst_period: int = 30
    burst_min_slots: int = 5
    burst_max_slots: int = 10
    burst_phase_slots: int = 4
    burst_multiplier: float = 3.
    batch_mean: float = 2.
    noise_sigma: float = .15
    work_sigma: float = .1
    rate_multiplier: float = .4
    payload_multiplier: float = .1
    preprocess_ms: float = 2.
    inference_ms: float = 10.
    postprocess_ms: float = 2.
    gpu_stage_cpu_fraction: float = .25
    cold_start_slots: int = 1
    migration_down_slots: int = 1
    cold_penalty_ms: float = 5.
    migration_penalty_ms: float = 10.
    max_replicas: int = 3
    action_budget: int = 2
    cooldown_slots: int = 3
    rebalance_period: int = 10
    high_threshold: float = .8
    low_threshold: float = .2
    ewma_alpha: float = .5
    risk_threshold: float = .8
    headroom_weight: float = .35
    overhead_weight: float = .25

    def __post_init__(self):
        integer_names = {"trials", "first_seed", "slots", "node_count", "service_count",
                         "burst_start", "burst_period", "burst_min_slots", "burst_max_slots",
                         "burst_phase_slots", "cold_start_slots", "migration_down_slots",
                         "max_replicas", "action_budget", "cooldown_slots", "rebalance_period"}
        zero_allowed = {"first_seed", "burst_start", "burst_phase_slots", "cold_start_slots",
                        "migration_down_slots", "cooldown_slots"}
        for name, value in asdict(self).items():
            if name in integer_names:
                if type(value) is not int or value < (0 if name in zero_allowed else 1):
                    raise ValueError(f"invalid integer {name}")
            elif not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid finite nonnegative {name}")
        if self.trials < 30:
            raise ValueError("at least 30 paired trials required")
        if not 0 < self.low_threshold < self.high_threshold < 1:
            raise ValueError("require 0 < low_threshold < high_threshold < 1")
        if not 0 < self.ewma_alpha <= 1 or not 0 < self.gpu_stage_cpu_fraction <= 1:
            raise ValueError("EWMA and CPU fractions must be in (0,1]")
        if self.batch_mean < 1 or self.burst_multiplier < 1 or self.burst_max_slots < self.burst_min_slots:
            raise ValueError("invalid burst or batch parameters")
        for name in ("slot_seconds", "rate_multiplier", "payload_multiplier", "preprocess_ms",
                     "inference_ms", "postprocess_ms", "risk_threshold"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
