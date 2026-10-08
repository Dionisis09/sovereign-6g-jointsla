"""Seeded synthetic nodes, applications and a symmetric pairwise latency matrix."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class Config:
    node_count: int = 5
    application_count: int = 20
    trials: int = 30
    first_seed: int = 0
    cpu_capacity: tuple = (90., 120.)
    gpu_capacity: tuple = (40., 60.)
    bandwidth_capacity_mbps: tuple = (280., 420.)
    cpu_demand: tuple = (8., 20.)
    gpu_demand: tuple = (4., 14.)
    traffic_load_rps: tuple = (20., 80.)
    payload_megabits: tuple = (.5, 2.5)
    latency_requirement_ms: tuple = (25., 65.)
    network_latency_ms: tuple = (4., 25.)
    base_processing_ms: float = 12.
    latency_weight: float = 1.
    headroom_weight: float = .35
    sla_risk_weight: float = 3.

    def __post_init__(self):
        for name in ("node_count", "application_count", "trials", "first_seed"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "first_seed" else 1):
                raise ValueError(f"{name} must be a {'nonnegative' if name == 'first_seed' else 'positive'} integer")
        if self.trials < 30:
            raise ValueError("at least 30 trials are required")
        for name, values in asdict(self).items():
            if isinstance(values, (list, tuple)):
                if len(values) != 2 or not all(math.isfinite(v) and v > 0 for v in values) or values[0] > values[1]:
                    raise ValueError(f"{name} must be a positive finite [minimum, maximum] range")
                object.__setattr__(self, name, tuple(values))
        for name in ("base_processing_ms", "latency_weight", "headroom_weight", "sla_risk_weight"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0 or (name == "base_processing_ms" and value == 0):
                raise ValueError(f"invalid {name}")
        if self.latency_weight + self.headroom_weight + self.sla_risk_weight == 0:
            raise ValueError("at least one heuristic weight must be positive")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class EdgeServer:
    node_id: int
    cpu_capacity: float
    gpu_capacity: float
    bandwidth_capacity_mbps: float

    @property
    def capacity(self):
        return np.array([self.cpu_capacity, self.gpu_capacity, self.bandwidth_capacity_mbps])


@dataclass(frozen=True)
class Application:
    application_id: int
    ingress_node: int
    cpu_demand: float
    gpu_demand: float
    bandwidth_demand_mbps: float
    latency_requirement_ms: float
    traffic_load_rps: float

    @property
    def demand(self):
        return np.array([self.cpu_demand, self.gpu_demand, self.bandwidth_demand_mbps])


@dataclass(frozen=True)
class Scenario:
    seed: int
    nodes: tuple[EdgeServer, ...]
    applications: tuple[Application, ...]
    network_latency_ms: np.ndarray

    @property
    def capacities(self):
        return np.array([node.capacity for node in self.nodes])

    def to_dict(self):
        return dict(seed=self.seed, nodes=[asdict(n) for n in self.nodes],
                    applications=[asdict(a) for a in self.applications],
                    network_latency_ms=self.network_latency_ms.tolist())


def generate_scenario(config: Config, seed: int) -> Scenario:
    """Draw each input once; algorithm RNG never affects these paired inputs."""
    rng = np.random.default_rng(seed)
    nodes = tuple(EdgeServer(i, float(rng.uniform(*config.cpu_capacity)),
                             float(rng.uniform(*config.gpu_capacity)),
                             float(rng.uniform(*config.bandwidth_capacity_mbps)))
                  for i in range(config.node_count))
    matrix = np.zeros((config.node_count, config.node_count))
    for i in range(config.node_count):
        for j in range(i + 1, config.node_count):
            matrix[i, j] = matrix[j, i] = rng.uniform(*config.network_latency_ms)
    matrix.setflags(write=False)
    applications = []
    for i in range(config.application_count):
        load = float(rng.uniform(*config.traffic_load_rps))
        payload = float(rng.uniform(*config.payload_megabits))
        applications.append(Application(i, int(rng.integers(config.node_count)),
                                        float(rng.uniform(*config.cpu_demand)),
                                        float(rng.uniform(*config.gpu_demand)),
                                        load * payload,
                                        float(rng.uniform(*config.latency_requirement_ms)), load))
    return Scenario(seed, nodes, tuple(applications), matrix)


def estimate_latency(config: Config, scenario: Scenario, app: Application,
                     node_index: int, node_usage: np.ndarray) -> float:
    """Network RTT plus linear utilization penalty; synthetic, not a queue model.

    CPU/GPU are reserved demand units, bandwidth is Mbps, traffic is requests/s.
    `node_usage` includes the candidate application (or the complete final placement).
    """
    cpu, gpu, bandwidth = node_usage / scenario.nodes[node_index].capacity
    processing = config.base_processing_ms * (1 + cpu + .8 * gpu + .3 * bandwidth)
    return float(scenario.network_latency_ms[app.ingress_node, node_index] + processing)

