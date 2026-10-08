"""SimPy request pipelines; orchestration happens only at discrete slot boundaries."""
from dataclasses import dataclass
from time import perf_counter_ns
import numpy as np
import simpy
from .policies import POLICIES


class BusyIntegral:
    """Exact piecewise-constant busy-resource integral, including slot crossings."""
    def __init__(self, env):
        self.env, self.last, self.busy, self.total = env, 0., 0., 0.

    def value(self):
        return self.total + self.busy * (self.env.now - self.last)

    def change(self, delta):
        self.total = self.value()
        self.last = self.env.now
        self.busy += delta
        if self.busy < -1e-8:
            raise AssertionError("negative busy resources")


class Node:
    def __init__(self, env, spec, gpu_units):
        # Integer 0.1-millicore tokens avoid floating-point Container.put stalls.
        cpu_tokens = int(np.floor(spec.cpu_capacity * 10_000))
        self.cpu = simpy.Container(env, capacity=cpu_tokens, init=cpu_tokens)
        self.gpu = simpy.Resource(env, capacity=gpu_units)
        self.network = simpy.Resource(env, capacity=1)
        self.integrals = [BusyIntegral(env) for _ in range(3)]
        self.previous = np.zeros(3)
        self.gpu_units = gpu_units
        self.spec = spec

    def sample(self, seconds):
        values = np.array([x.value() for x in self.integrals])
        utilization = (values - self.previous) / seconds / np.array([self.spec.cpu_capacity, self.gpu_units, 1.])
        self.previous = values
        if np.any(utilization < -1e-8) or np.any(utilization > 1 + 1e-8):
            raise AssertionError("physical resource overbooking")
        return np.clip(utilization, 0, 1)


@dataclass
class Replica:
    replica_id: int
    service_id: int
    node: int
    ready: bool = False
    busy: bool = False
    pending_target: int | None = None
    retiring: bool = False
    penalty_ms: float = 0.
    signal: object = None


class Simulator:
    """All policies share FIFO service queues and finite CPU/GPU/link schedulers.

    CPU and VRAM reservations are admission limits, not utilization measurements.
    A migration reserves its target before release of the source, finishes an
    in-flight request at source, then pauses the replica before target activation.
    Other replicas continue serving; waiting requests remain in the shared queue.
    """
    def __init__(self, config, workload, policy):
        self.config, self.workload, self.policy = config, workload, policy
        self.env = simpy.Environment()
        self.nodes = [Node(self.env, n, g) for n, g in zip(workload.scenario.nodes, workload.gpu_units)]
        self.services = workload.services
        self.capacities = workload.scenario.capacities
        self.reserved = np.zeros_like(self.capacities)
        self.max_reserved_fraction = np.zeros(3)
        self.queues = [simpy.Store(self.env) for _ in self.services]
        self.replicas = {}
        self.next_replica = 0
        self.last_action = np.full(len(self.services), -config.cooldown_slots)
        self.rates = np.array([s.base_rate_rps for s in self.services])
        self.recent_latency = np.array([config.preprocess_ms + config.inference_ms + config.postprocess_ms
                                       + workload.scenario.network_latency_ms[s.ingress, workload.initial[s.service_id]]
                                       if workload.initial[s.service_id] is not None else s.deadline_ms * 2
                                       for s in self.services])
        self.observed_arrivals = np.zeros(len(self.services))
        self.recent_completions = [[] for _ in self.services]
        self.utilization = np.zeros((len(self.nodes), 2))
        self.slot, self.outcomes, self.actions, self.slots, self.node_rows = 0, [], [], [], []
        self.reservation_events, self.lifecycle_events = [], []
        self.finished = self.env.event()
        self.replica_integral = BusyIntegral(self.env)
        self.memory_integral = BusyIntegral(self.env)
        self.rejected_actions = 0
        for sid, node in workload.initial.items():
            if node is not None:
                self.add_replica(sid, node, warm=True)
        if not workload.requests:
            self.finished.succeed()

    def _reserve(self, sid, node, sign):
        change = self.services[sid].reservation * sign
        self.reserved[node] += change
        if np.any(self.reserved < -1e-8) or np.any(self.reserved > self.capacities + 1e-8):
            raise AssertionError("CPU/VRAM/bandwidth reservation overflow")
        self.max_reserved_fraction = np.maximum(self.max_reserved_fraction,
                                                (self.reserved / self.capacities).max(axis=0))
        self.memory_integral.change(change[1])
        self.reservation_events.append(dict(time_s=self.env.now, service_id=sid, node=node, sign=sign,
                                            cpu_reserved=self.reserved[node, 0],
                                            gpu_vram_reserved=self.reserved[node, 1],
                                            bandwidth_reserved=self.reserved[node, 2]))

    def add_replica(self, sid, node, warm=False):
        self._reserve(sid, node, 1)
        replica = Replica(self.next_replica, sid, node, ready=warm,
                          penalty_ms=0 if warm else self.config.cold_penalty_ms, signal=self.env.event())
        self.next_replica += 1
        self.replicas[replica.replica_id] = replica
        self.replica_integral.change(1)
        self.env.process(self.worker(replica, warm))
        return replica

    def snapshot(self):
        """Copies expose only current/past state; never the arrival tape or burst plan."""
        replicas = {s.service_id: [] for s in self.services}
        for r in self.replicas.values():
            if not r.retiring:
                replicas[r.service_id].append(dict(id=r.replica_id, node=r.node,
                                                   ready=r.ready and r.pending_target is None, busy=r.busy))
        return dict(slot=self.slot, services=self.services, capacities=self.capacities.copy(),
                    reserved=self.reserved.copy(), utilization=self.utilization.copy(), replicas=replicas,
                    rates=self.rates.copy(), latency_ms=self.recent_latency.copy(), last_action=self.last_action.copy(),
                    queue_lengths=np.array([len(q.items) for q in self.queues]),
                    oldest_wait_ms=np.array([(self.env.now - q.items[0].arrival_s) * 1000 if q.items else 0 for q in self.queues]),
                    network_ms=self.workload.scenario.network_latency_ms.copy())

    def apply(self, action):
        """Validate actions sequentially, including competing target reservations."""
        c, sid = self.config, action.service_id
        if sid < 0 or sid >= len(self.services) or self.slot - self.last_action[sid] < c.cooldown_slots:
            self.rejected_actions += 1
            return False
        existing = [r for r in self.replicas.values() if r.service_id == sid]
        replica = self.replicas.get(action.replica_id)
        valid_replica = replica is not None and replica.service_id == sid and replica.ready and replica.pending_target is None and not replica.retiring
        if action.kind in ("scale_up", "migrate"):
            target = action.target
            if target is None or not 0 <= target < len(self.nodes) or np.any(
                    self.reserved[target] + self.services[sid].reservation > self.capacities[target] + 1e-9):
                self.rejected_actions += 1
                return False
            if action.kind == "scale_up":
                if len(existing) >= c.max_replicas:
                    self.rejected_actions += 1
                    return False
                replica = self.add_replica(sid, target)
            else:
                if not valid_replica or target == replica.node:
                    self.rejected_actions += 1
                    return False
                self._reserve(sid, target, 1)
                replica.pending_target = target
                if not replica.signal.triggered:
                    replica.signal.succeed()
        elif action.kind == "scale_down":
            if not valid_replica or replica.busy or sum(not r.retiring for r in existing) <= 1 or self.queues[sid].items:
                self.rejected_actions += 1
                return False
            replica.retiring = True
            if not replica.signal.triggered:
                replica.signal.succeed()
        else:
            raise ValueError(f"unknown action {action.kind}")
        self.last_action[sid] = self.slot
        self.actions.append(dict(slot=self.slot, time_s=self.env.now, kind=action.kind, service_id=sid,
                                 replica_id=replica.replica_id, source_node=replica.node,
                                 target_node=action.target, risk=action.risk))
        return True

    def worker(self, replica, warm):
        c, sid = self.config, replica.service_id
        if not warm:
            self.lifecycle_events.append(dict(kind="cold_start", replica_id=replica.replica_id,
                                               start_s=self.env.now, ready_s=self.env.now + c.cold_start_slots * c.slot_seconds))
            yield self.env.timeout(c.cold_start_slots * c.slot_seconds)
            replica.ready = True
        while True:
            if replica.retiring:
                self._reserve(sid, replica.node, -1)
                self.replica_integral.change(-1)
                del self.replicas[replica.replica_id]
                return
            if replica.pending_target is not None:
                replica.ready = False
                self._reserve(sid, replica.node, -1)
                replica.node = replica.pending_target
                replica.pending_target = None
                self.lifecycle_events.append(dict(kind="migration_downtime", replica_id=replica.replica_id,
                                                   start_s=self.env.now, ready_s=self.env.now + c.migration_down_slots * c.slot_seconds))
                yield self.env.timeout(c.migration_down_slots * c.slot_seconds)
                replica.penalty_ms = c.migration_penalty_ms
                replica.ready = True
            replica.signal = self.env.event()
            get = self.queues[sid].get()
            yield get | replica.signal
            # If a simultaneous queue get has fired, finish that job before lifecycle changes.
            if not get.triggered:
                get.cancel()
                continue
            request = get.value
            replica.busy = True
            service_queue_s = self.env.now - request.arrival_s
            node = self.nodes[replica.node]
            s = self.services[sid]
            network_s = self.workload.scenario.network_latency_ms[s.ingress, replica.node] / 1000
            node_queue_s = 0.
            started = self.env.now
            with node.network.request() as token:
                yield token
                node_queue_s += self.env.now - started
                transmission_s = request.payload_mbit / node.spec.bandwidth_capacity_mbps
                node.integrals[2].change(1)
                yield self.env.timeout(transmission_s)
                node.integrals[2].change(-1)
            network_s += transmission_s
            yield self.env.timeout(network_s - transmission_s)
            penalty_s = replica.penalty_ms / 1000
            replica.penalty_ms = 0.
            if penalty_s:
                yield self.env.timeout(penalty_s)
            compute_s = 0.
            for stage, duration_ms in (("cpu", c.preprocess_ms), ("gpu", c.inference_ms), ("cpu", c.postprocess_ms)):
                started = self.env.now
                cpu_tokens = max(1, int(np.floor(s.cpu_cores * 10_000 * (c.gpu_stage_cpu_fraction if stage == "gpu" else 1.))))
                cpu_cores = cpu_tokens / 10_000
                if stage == "gpu":
                    with node.gpu.request() as token:
                        yield token
                        yield node.cpu.get(cpu_tokens)
                        node_queue_s += self.env.now - started
                        node.integrals[0].change(cpu_cores)
                        node.integrals[1].change(1)
                        duration_s = duration_ms * request.work_factor / 1000
                        yield self.env.timeout(duration_s)
                        compute_s += duration_s
                        node.integrals[0].change(-cpu_cores)
                        node.integrals[1].change(-1)
                        yield node.cpu.put(cpu_tokens)
                else:
                    yield node.cpu.get(cpu_tokens)
                    node_queue_s += self.env.now - started
                    node.integrals[0].change(cpu_cores)
                    duration_s = duration_ms * request.work_factor / 1000
                    yield self.env.timeout(duration_s)
                    compute_s += duration_s
                    node.integrals[0].change(-cpu_cores)
                    yield node.cpu.put(cpu_tokens)
            latency_ms = (self.env.now - request.arrival_s) * 1000
            components_ms = (service_queue_s + node_queue_s + compute_s + network_s + penalty_s) * 1000
            if abs(latency_ms - components_ms) > 1e-6:
                raise AssertionError(f"latency components do not sum: {latency_ms}, {components_ms}, "
                                     f"{service_queue_s}, {node_queue_s}, {compute_s}, {network_s}, {penalty_s}")
            self.outcomes.append(dict(request_id=request.request_id, service_id=sid, tier=s.tier,
                                      arrival_slot=request.arrival_slot, arrival_s=request.arrival_s,
                                      completion_s=self.env.now, node=replica.node, replica_id=replica.replica_id,
                                      deadline_ms=s.deadline_ms, latency_ms=latency_ms,
                                      service_queue_ms=service_queue_s * 1000, node_queue_ms=node_queue_s * 1000,
                                      compute_ms=compute_s * 1000, network_ms=network_s * 1000,
                                      lifecycle_penalty_ms=penalty_s * 1000,
                                      breach=bool(latency_ms > s.deadline_ms), unplaced=False))
            self.recent_completions[sid].append(latency_ms)
            replica.busy = False
            self._finish_if_done()

    def _finish_if_done(self):
        if len(self.outcomes) == len(self.workload.requests) and not self.finished.triggered:
            self.finished.succeed()

    def source(self):
        for request in self.workload.requests:
            yield self.env.timeout(max(0., request.arrival_s - self.env.now))
            sid = request.service_id
            self.observed_arrivals[sid] += 1
            if self.workload.initial[sid] is None:
                s = self.services[sid]
                self.outcomes.append(dict(request_id=request.request_id, service_id=sid, tier=s.tier,
                                          arrival_slot=request.arrival_slot, arrival_s=request.arrival_s,
                                          completion_s=None, node=None, replica_id=None, deadline_ms=s.deadline_ms,
                                          latency_ms=None, service_queue_ms=None, node_queue_ms=None,
                                          compute_ms=None, network_ms=None, lifecycle_penalty_ms=None,
                                          breach=True, unplaced=True))
                self._finish_if_done()
            else:
                yield self.queues[sid].put(request)

    def decisions(self):
        c = self.config
        for slot in range(c.slots):
            self.slot = slot
            snapshot = self.snapshot()
            started = perf_counter_ns()
            actions = POLICIES[self.policy](c, snapshot)
            if len(actions) > c.action_budget:
                raise ValueError("policy exceeded common per-step action budget")
            accepted = sum(self.apply(action) for action in actions)
            runtime_ms = (perf_counter_ns() - started) / 1e6
            yield self.env.timeout(c.slot_seconds)
            observed = self.observed_arrivals.copy()
            self.rates = c.ewma_alpha * observed / c.slot_seconds + (1 - c.ewma_alpha) * self.rates
            self.observed_arrivals[:] = 0
            for sid, completed in enumerate(self.recent_completions):
                if completed:
                    self.recent_latency[sid] = float(np.mean(completed))
                completed.clear()
            utilization = np.array([n.sample(c.slot_seconds) for n in self.nodes])
            self.utilization = utilization[:, :2]
            snapshot_end = self.snapshot()
            offered = np.zeros((len(self.nodes), 3))
            for s in self.services:
                replicas = snapshot_end["replicas"][s.service_id]
                count = len(replicas)
                for r in replicas:
                    rate = observed[s.service_id] / c.slot_seconds / count
                    cpu_work = s.cpu_cores * (c.preprocess_ms + c.postprocess_ms + c.gpu_stage_cpu_fraction * c.inference_ms) / 1000
                    offered[r["node"]] += rate * np.array([cpu_work / self.capacities[r["node"], 0],
                                                          c.inference_ms / 1000 / self.workload.gpu_units[r["node"]],
                                                          s.payload_mbit / self.capacities[r["node"], 2]])
            for n in range(len(self.nodes)):
                self.node_rows.append(dict(slot=slot, node=n, cpu_utilization=utilization[n, 0],
                                           gpu_utilization=utilization[n, 1], bandwidth_utilization=utilization[n, 2],
                                           cpu_offered_ratio=offered[n, 0], gpu_offered_ratio=offered[n, 1],
                                           bandwidth_offered_ratio=offered[n, 2],
                                           cpu_reserved_fraction=self.reserved[n, 0] / self.capacities[n, 0],
                                           gpu_vram_reserved_fraction=self.reserved[n, 1] / self.capacities[n, 1]))
            self.slots.append(dict(slot=slot, observed_arrivals=int(observed.sum()),
                                   waiting_requests=sum(len(q.items) for q in self.queues),
                                   replicas=len(self.replicas), proposed_actions=len(actions), accepted_actions=accepted,
                                   decision_runtime_ms=runtime_ms))

    def run(self):
        """Observe T slots, then drain all requests without further orchestration."""
        started = perf_counter_ns()
        self.env.process(self.source())
        horizon = self.env.process(self.decisions())
        self.env.run(until=horizon)
        horizon_replica_seconds = self.replica_integral.value()
        horizon_vram_gb_seconds = self.memory_integral.value()
        self.env.run(until=self.finished)
        if len({r["request_id"] for r in self.outcomes}) != len(self.workload.requests):
            raise AssertionError("request duplication or loss")
        return dict(outcomes=self.outcomes, slots=self.slots, nodes=self.node_rows, actions=self.actions,
                    reservations=self.reservation_events, lifecycle=self.lifecycle_events,
                    diagnostics=dict(drain_seconds=max(0., self.env.now - self.config.slots * self.config.slot_seconds),
                                     replica_seconds=horizon_replica_seconds,
                                     vram_gb_seconds=horizon_vram_gb_seconds,
                                     max_cpu_reserved_fraction=self.max_reserved_fraction[0],
                                     max_gpu_vram_reserved_fraction=self.max_reserved_fraction[1],
                                     max_bandwidth_reserved_fraction=self.max_reserved_fraction[2],
                                     rejected_actions=self.rejected_actions,
                                     total_simulation_runtime_ms=(perf_counter_ns() - started) / 1e6))
