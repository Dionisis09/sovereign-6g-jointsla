"""Causal, interpretable request routing from observable candidate states."""
from dataclasses import dataclass
import math

NEW_POLICIES = ("sla_rr", "sla_shortest_queue", "joint_sla", "joint_no_queue", "joint_no_slack")
LABELS = dict(static="Static", reactive="Reactive", periodic="Periodic", sla_aware="SLA-aware",
              sla_rr="SLA-aware+RR", sla_shortest_queue="SLA-aware+ShortestQueue",
              joint_sla="JointSLA", joint_no_queue="JointSLA-no-queue", joint_no_slack="JointSLA-no-slack")


@dataclass(frozen=True)
class Settings:
    """Evaluation margins fixed before test seeds; no controller weight tuning."""
    virtual_batch_limit: int = 20
    p99_noninferiority_percent: float = 5.
    replica_increase_percent: float = 5.
    vram_increase_pp: float = 2.
    controller_mean_limit_ms: float = 10.
    routing_p95_limit_ms: float = 1.


def estimate(candidate, deadline, age_ms=0., no_queue=False, no_slack=False):
    """Variance/slack risk proxy, not a calibrated probability or oracle.

    Mean cycle observations contain only completed work. Service queue waiting
    and work_factor of the arriving request never enter those observations.
    Initial variance uses the existing nominal compute jitter parameter.
    """
    q = 0 if no_queue else candidate["queue_length"]
    remaining = 0. if no_queue else candidate["remaining_busy_ms"]
    queue = q*candidate["cycle_ms"]+remaining
    duration = candidate["network_ms"]+candidate["compute_ms"]+candidate["resource_wait_ms"]+candidate["penalty_ms"]
    completion = age_ms+candidate.get("available_in_ms",0.)+queue+duration
    slack = deadline-completion
    variance = candidate["cycle_variance_ms2"]*(q+1+(not no_queue and candidate["busy"]))
    risk = 1. if slack<=0 else variance/(variance+slack*slack)
    key = (completion,candidate["id"]) if no_slack else (risk,-slack,completion,candidate["id"])
    return dict(estimated_queue_wait_ms=queue, estimated_resource_wait_ms=candidate["resource_wait_ms"],
                estimated_completion_ms=completion, slack_ms=slack, risk_proxy=risk,
                estimated_variance_ms2=variance, key=key)


def choose(candidates, deadline, policy, rr_counter=0, age_ms=0.):
    """Eligible candidates only; busy active workers may receive queued work."""
    if not candidates:
        return None
    ordered=sorted(candidates,key=lambda c:c["id"])
    if policy=="sla_rr":
        return ordered[rr_counter%len(ordered)]["id"]
    if policy=="sla_shortest_queue":
        return min(ordered,key=lambda c:(c["queue_length"]+int(c["busy"]),c["id"]))["id"]
    return min(ordered,key=lambda c:estimate(c,deadline,age_ms,
               no_queue=policy=="joint_no_queue",no_slack=policy=="joint_no_slack")["key"])["id"]
