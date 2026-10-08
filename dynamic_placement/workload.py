"""Immutable exogenous inputs, generated once per seed for all four policies."""
from dataclasses import asdict, dataclass
import numpy as np
from placement_experiment.data_generation import (
    Application, Config as StaticConfig, EdgeServer, Scenario, generate_scenario)
from placement_experiment.algorithms import greedy_placement
from .config import Config


@dataclass(frozen=True)
class Service:
    service_id: int
    ingress: int
    cpu_cores: float
    gpu_vram_gb: float
    bandwidth_mbps: float
    base_rate_rps: float
    payload_mbit: float
    deadline_ms: float
    tier: str
    priority: int

    @property
    def reservation(self):
        return np.array([self.cpu_cores, self.gpu_vram_gb, self.bandwidth_mbps])


@dataclass(frozen=True)
class Request:
    request_id: int
    service_id: int
    arrival_s: float
    arrival_slot: int
    work_factor: float
    payload_mbit: float


@dataclass(frozen=True)
class Workload:
    seed: int
    scenario: Scenario
    services: tuple[Service, ...]
    gpu_units: tuple[int, ...]
    initial: dict
    requests: tuple[Request, ...]
    traffic: tuple[dict, ...]

    def to_dict(self):
        return dict(seed=self.seed, scenario=self.scenario.to_dict(),
                    services=[asdict(s) for s in self.services], gpu_units=list(self.gpu_units),
                    initial=self.initial, requests=[asdict(r) for r in self.requests], traffic=self.traffic)


def generate_workload(config: Config, seed: int) -> Workload:
    """Compound Poisson: Poisson cluster arrivals, geometric cluster sizes.

    Cluster intensity = rate / mean_batch; hence expected requests/second = rate.
    Bursts are periodic with seeded phase and duration, not independent Poisson noise.
    Traffic, request work and topology use separate deterministic RNG streams.
    """
    static_config = StaticConfig(node_count=config.node_count, application_count=config.service_count)
    original = generate_scenario(static_config, seed)
    nodes = tuple(EdgeServer(n.node_id, n.cpu_capacity / 10, n.gpu_capacity / 2,
                             n.bandwidth_capacity_mbps) for n in original.nodes)
    services, apps = [], []
    for a in original.applications:
        tier_index = a.application_id % 3
        service = Service(a.application_id, a.ingress_node, a.cpu_demand / 10,
                          a.gpu_demand / 2, a.bandwidth_demand_mbps * config.rate_multiplier * config.payload_multiplier,
                          a.traffic_load_rps * config.rate_multiplier,
                          a.bandwidth_demand_mbps / a.traffic_load_rps * config.payload_multiplier,
                          a.latency_requirement_ms * (1., 1.8, 3.)[tier_index],
                          ("Gold", "Silver", "Bronze")[tier_index], (3, 2, 1)[tier_index])
        services.append(service)
        apps.append(Application(service.service_id, service.ingress, service.cpu_cores,
                                service.gpu_vram_gb, service.bandwidth_mbps,
                                service.deadline_ms, service.base_rate_rps))
    scenario = Scenario(seed, nodes, tuple(apps), original.network_latency_ms)
    initial = greedy_placement(static_config, scenario, seed)
    traffic_rng, work_rng = [np.random.default_rng(np.random.SeedSequence([seed, salt])) for salt in (6101, 6102)]
    raw, traffic = [], []
    for s in services:
        phase = int(traffic_rng.integers(config.burst_phase_slots + 1))
        width = int(traffic_rng.integers(config.burst_min_slots, config.burst_max_slots + 1))
        for slot in range(config.slots):
            offset = slot - config.burst_start - phase
            burst = offset >= 0 and offset % config.burst_period < width
            noise = float(traffic_rng.lognormal(-config.noise_sigma ** 2 / 2, config.noise_sigma))
            rate = s.base_rate_rps * noise * (config.burst_multiplier if burst else 1.)
            clusters = int(traffic_rng.poisson(rate * config.slot_seconds / config.batch_mean))
            count = 0
            for _ in range(clusters):
                time = (slot + float(traffic_rng.random())) * config.slot_seconds
                batch = int(traffic_rng.geometric(1 / config.batch_mean))
                count += batch
                for _ in range(batch):
                    work = float(work_rng.lognormal(-config.work_sigma ** 2 / 2, config.work_sigma))
                    raw.append((time, s.service_id, slot, work, s.payload_mbit))
            traffic.append(dict(service_id=s.service_id, slot=slot, burst=bool(burst),
                                expected_rate_rps=rate, arrivals=count))
    raw.sort(key=lambda x: (x[0], x[1]))
    requests = tuple(Request(i, sid, t, slot, work, payload) for i, (t, sid, slot, work, payload) in enumerate(raw))
    gpu_units = tuple(2 if n.gpu_capacity < 25 else 3 for n in nodes)
    return Workload(seed, scenario, tuple(services), gpu_units, initial, requests, tuple(traffic))
