"""Causal periodic-burst forecast from ten-slot moving averages."""
from dataclasses import dataclass, asdict
import math
import numpy as np
from .policies import Action, sla_aware


@dataclass(frozen=True)
class ScenarioConfig:
    moving_average_slots: int = 10
    prewarm_lead_slots: int = 2
    burst_detection_ratio: float = 1.5
    admission_threshold: float = .8
    capacity_additions: tuple = (1, 2)
    sla_target_pct: float = 15.

    def __post_init__(self):
        if type(self.moving_average_slots) is not int or self.moving_average_slots < 2:
            raise ValueError("moving average window must be an integer >=2")
        if type(self.prewarm_lead_slots) is not int or self.prewarm_lead_slots not in (1, 2):
            raise ValueError("prewarm lead must be one or two slots")
        if not math.isfinite(self.burst_detection_ratio) or self.burst_detection_ratio <= 1:
            raise ValueError("burst detection ratio must exceed one")
        if not 0 < self.admission_threshold < 1 or not 0 < self.sla_target_pct < 100:
            raise ValueError("invalid admission threshold or SLA target")
        if tuple(self.capacity_additions) != (1, 2):
            raise ValueError("this protocol compares one and two additional nodes")


class PredictivePrewarming:
    """Learn phase from a past MA crossing; known period is a protocol parameter.

    Detect a burst when aggregate ten-slot MA exceeds 1.5 times declared mean.
    Approximate onset by subtracting half the MA window from the crossing slot.
    Forecast the next onset using the known period, and scale out 1–2 slots
    before it. Per-service peak MA determines replica need. There is no first-
    burst prediction, no arrival tape access, and no knowledge of actual phase.
    Cold starts, first-request penalties, action budgets and cooldowns all apply.
    """
    def __init__(self, settings):
        self.settings = settings
        self.last_onset = None
        self.last_detection = -10_000
        self.crossing = False
        self.forecasts = []
        self.prewarm_proposals = []
        self.protected_until = {}
        self.last_ma = None

    def __call__(self, config, snapshot):
        slot, history = snapshot["slot"], snapshot["arrival_history"]
        window = self.settings.moving_average_slots
        base = np.array([s.base_rate_rps for s in snapshot["services"]])
        moving = history[-window:].mean(axis=0) / config.slot_seconds if len(history) >= window else base.copy()
        elevated = len(history) >= window and moving.sum() > base.sum() * self.settings.burst_detection_ratio
        if elevated and not self.crossing and slot - self.last_detection >= config.burst_period // 2:
            self.last_onset = max(0, slot - window // 2)
            self.last_detection = slot
        self.crossing = bool(elevated)
        self.last_ma = moving
        predicted = None
        if self.last_onset is not None:
            predicted = self.last_onset + config.burst_period
            while predicted < slot:
                predicted += config.burst_period
        lead = predicted - slot if predicted is not None else None
        warm = []
        forecast = moving.copy()
        if lead is not None and 1 <= lead <= self.settings.prewarm_lead_slots:
            # Only past MA windows contribute to the forecast peak.
            start = max(0, len(history) - config.burst_period - window)
            past = history[start:]
            if len(past) >= window:
                peak = np.max([past[i:i+window].mean(axis=0) / config.slot_seconds
                               for i in range(len(past)-window+1)], axis=0)
                forecast = np.maximum(base, peak)
            ranked = sorted(snapshot["services"], key=lambda s: (-s.priority * forecast[s.service_id] / s.deadline_ms,
                                                                 -s.priority, s.service_id))
            reserved = snapshot["reserved"].copy()
            for service in ranked:
                sid, replicas = service.service_id, snapshot["replicas"][service.service_id]
                if not replicas or slot - snapshot["last_action"][sid] < config.cooldown_slots:
                    continue
                network = min(snapshot["network_ms"][service.ingress, r["node"]] for r in replicas)
                pipeline_s = (network + config.preprocess_ms + config.inference_ms + config.postprocess_ms) / 1000
                desired = min(config.max_replicas, max(1, math.ceil(forecast[sid] * pipeline_s / config.high_threshold)))
                if len(replicas) >= desired:
                    continue
                targets = [n for n in range(len(reserved))
                           if np.all(reserved[n] + service.reservation <= snapshot["capacities"][n] + 1e-9)]
                if not targets:
                    continue
                def score(n):
                    fraction = (reserved[n] + service.reservation) / snapshot["capacities"][n]
                    return (snapshot["network_ms"][service.ingress, n] / service.deadline_ms
                            + config.headroom_weight * float(fraction[:2].mean())
                            + float(max(snapshot["utilization"][n])))
                target = min(targets, key=lambda n: (score(n), n))
                warm.append(Action("scale_up", sid, target, risk=float(forecast[sid] * pipeline_s)))
                reserved[target] += service.reservation
                self.protected_until[sid] = predicted + window
                self.prewarm_proposals.append(dict(slot=slot, service_id=sid, target=target,
                                                   predicted_burst_slot=predicted, lead_slots=lead,
                                                   forecast_rate_rps=float(forecast[sid])))
                if len(warm) == config.action_budget:
                    break
        self.forecasts.append(dict(slot=slot, aggregate_ma_rps=float(moving.sum()), detected=elevated,
                                   predicted_burst_slot=predicted, prewarm_proposed=len(warm)))
        warm_ids = {a.service_id for a in warm}
        reactive = [a for a in sla_aware(config, snapshot) if a.service_id not in warm_ids
                    and not (a.kind == "scale_down" and slot < self.protected_until.get(a.service_id, -1))]
        return (warm + reactive)[:config.action_budget]
