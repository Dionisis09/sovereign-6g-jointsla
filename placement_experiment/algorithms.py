"""Four interchangeable placement functions returning application ID -> node ID/None."""
import numpy as np
from .data_generation import Config, Scenario, estimate_latency


def _place(config, scenario, order, cost=None, rng=None):
    """Common feasibility path: reserve resources only after a feasible choice."""
    usage = np.zeros((len(scenario.nodes), 3))
    assignments = {}
    capacities = scenario.capacities
    for app in order:
        projected = usage + app.demand
        feasible = np.flatnonzero(np.all(projected <= capacities + 1e-9, axis=1))
        if not len(feasible):
            assignments[app.application_id] = None
            continue
        if rng is not None:
            chosen = int(rng.choice(feasible))
        else:
            chosen = min(feasible, key=lambda i: (cost(app, int(i), projected[i]), int(i)))
        assignments[app.application_id] = scenario.nodes[chosen].node_id
        usage[chosen] += app.demand
    return assignments


def random_placement(config: Config, scenario: Scenario, seed: int):
    """Randomize application order and choose uniformly among feasible nodes."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 2026]))
    order = [scenario.applications[i] for i in rng.permutation(len(scenario.applications))]
    return _place(config, scenario, order, rng=rng)


def greedy_placement(config: Config, scenario: Scenario, seed: int):
    """Largest dominant demand first, then the least-utilized feasible node.

    CPU/GPU/bandwidth all contribute; network distance and SLA do not.
    """
    reference = scenario.capacities.mean(axis=0)
    order = sorted(scenario.applications, key=lambda a: (-float(np.max(a.demand / reference)), a.application_id))
    return _place(config, scenario, order,
                  cost=lambda app, i, projected: float(np.mean(projected / scenario.nodes[i].capacity)))


def shortest_latency_placement(config: Config, scenario: Scenario, seed: int):
    """Input order; choose the lowest estimated post-placement latency."""
    return _place(config, scenario, scenario.applications,
                  cost=lambda app, i, projected: estimate_latency(config, scenario, app, i, projected))


def sla_weighted_placement(config: Config, scenario: Scenario, seed: int):
    """Prioritize load/SLA, then minimize normalized latency + headroom + SLA risk.

    Score = w_latency * (latency/SLA)
          + w_headroom * mean(projected CPU/GPU utilization)
          + w_risk * max(0, latency/SLA - 1)^2.
    Lower score is better; node ID breaks ties. `seed` is ignored intentionally.
    """
    order = sorted(scenario.applications,
                   key=lambda a: (-a.traffic_load_rps / a.latency_requirement_ms,
                                  a.latency_requirement_ms, a.application_id))

    def cost(app, i, projected):
        ratio = estimate_latency(config, scenario, app, i, projected) / app.latency_requirement_ms
        utilization = projected / scenario.nodes[i].capacity
        return (config.latency_weight * ratio + config.headroom_weight * float(utilization[:2].mean())
                + config.sla_risk_weight * max(0., ratio - 1.) ** 2)

    return _place(config, scenario, order, cost=cost)


ALGORITHMS = dict(random=random_placement, greedy=greedy_placement,
                  shortest_latency=shortest_latency_placement, sla_weighted=sla_weighted_placement)

