"""One synthetic service model; scheduling and FIFO queues are provided by SimPy."""
from collections import deque
from dataclasses import asdict
import simpy
from .contracts import ServiceState, compile_contract
from .policies import Action, Snapshot, TargetView, decide
from .reused import digest, quantile


class Engine:
    def __init__(self, config, scenario, tape, policy, forced=None):
        self.config, self.scenario, self.tape, self.policy = config, scenario, tape, policy
        self.forced = forced  # Audit only: (tick timestamp, action); never controller input.
        self.env = simpy.Environment()
        self.contract = compile_contract(config.intent)
        self.pools = [simpy.Store(self.env, capacity=2) for _ in range(2)]
        self.workers = [1, 1]
        for pool in self.pools:
            pool.put(object())
        self.active, self.fraction = 0, 0.
        self.last_rollout = -config.rollout_stage_hold_s
        self.last_reroute = -config.rollout_stage_hold_s
        self.overhead_until, self.unavailable_until = 0., 0.
        self.completed_at = None
        self.pressure, self.reactive = False, False
        self.arrivals, self.recent = deque(), deque()
        self.pending, self.outcomes = {}, []
        self.decisions, self.samples, self.outages = [], [], []
        self.worker_seconds, self.rollback_count = 0., 0

    def serve(self, request):
        config, env = self.config, self.env
        self.arrivals.append(request.time_s)
        self.pending[request.request_id] = request.time_s
        target, fraction = self.active, self.fraction
        version = "v2" if request.version_draw < fraction else "v1"
        network = (config.network_base_ms + 4 * target +
                   self.scenario.state_at(env.now)["network_extra_delay_ms"] +
                   config.network_jitter_ms * request.network_draw)
        yield env.timeout(network / 1000)
        yield env.timeout(config.gateway_ms / 1000)
        if env.now < self.unavailable_until:
            yield env.timeout(self.unavailable_until - env.now)
        entered = env.now
        token = yield self.pools[target].get()
        service = config.v2_service_ms if version == "v2" else config.v1_service_ms
        service *= request.service_factor / (1 - self.scenario.state_at(env.now)["capacity_reduction"])
        if env.now < self.overhead_until:
            service += config.rollout_overhead_ms
        yield env.timeout(service / 1000)
        yield self.pools[target].put(token)
        latency = 1000 * (env.now - request.time_s)
        row = dict(request_id=request.request_id, arrival_s=request.time_s, completion_s=env.now,
                   target=target, version=version, latency_ms=latency,
                   inference_ms=1000 * (env.now - entered), network_ms=network,
                   quality=config.v2_quality if version == "v2" else config.v1_quality,
                   timely=latency <= config.request_timeout_ms)
        self.outcomes.append(row)
        self.recent.append(row)
        del self.pending[request.request_id]

    def source(self):
        for request in self.tape.requests:
            yield self.env.timeout(request.time_s - self.env.now)
            self.env.process(self.serve(request))

    def observe(self):
        now, config = self.env.now, self.config
        while self.recent and self.recent[0]["completion_s"] <= now - config.metric_window_s:
            self.recent.popleft()
        while self.arrivals and self.arrivals[0] <= now - config.metric_window_s:
            self.arrivals.popleft()
        rows = list(self.recent)
        overdue = sum(now - t > config.request_timeout_ms / 1000 for t in self.pending.values())
        denominator = len(rows) + overdue
        disruption = max([0.] + [end - start for start, end in self.outages
                                   if end > now - config.metric_window_s and start < now])
        state = ServiceState(quantile([r["latency_ms"] for r in rows], .99) or 0.,
                             min([r["quality"] for r in rows], default=1.),
                             sum(r["timely"] for r in rows) / denominator if denominator else 1.,
                             disruption)
        current = self.scenario.state_at(now)
        targets = tuple(TargetView(self.workers[i], len(self.pools[i].get_queue),
                                  quantile([r["inference_ms"] for r in rows if r["target"] == i], .99) or
                                  1.2 * config.v1_service_ms / (1 - current["capacity_reduction"]),
                                  config.network_base_ms + 4 * i + current["network_extra_delay_ms"] +
                                  .99 * config.network_jitter_ms) for i in range(2))
        snapshot = Snapshot(now, targets, self.active, self.fraction,
                            len(self.arrivals) / min(now, config.metric_window_s),
                            current["capacity_reduction"], current["rollout_enabled"],
                            self.last_rollout, self.last_reroute, now < self.overhead_until,
                            bool(self.contract.violations(state)), self.pressure)
        return state, snapshot

    def apply(self, action):
        now, config = self.env.now, self.config
        if action == Action.SCALE_OUT:
            if self.workers[self.active] >= 2:
                raise ValueError("scale exceeds target capacity")
            self.workers[self.active] += 1
            self.pools[self.active].put(object())
        elif action == Action.REROUTE:
            self.active = 1 - self.active
            self.last_reroute = now
        elif action == Action.START_OR_CONTINUE_ROLLOUT:
            self.fraction = min(1., self.fraction + .25)
            self.last_rollout = now
            self.overhead_until = now + config.tick_s
            if config.rollout_disruption_s:
                self.unavailable_until = now + config.rollout_disruption_s
                self.outages.append((now, self.unavailable_until))
            if self.fraction == 1.:
                self.completed_at = now
        elif action == Action.ROLLBACK:
            self.fraction = 0.
            self.last_rollout = now
            self.overhead_until = now
            self.completed_at = None
            self.rollback_count += 1

    def controls(self):
        config = self.config
        for _ in range(round(config.duration_s / config.tick_s)):
            yield self.env.timeout(config.tick_s)
            self.worker_seconds += sum(self.workers) * config.tick_s
            state, snapshot = self.observe()
            violations = self.contract.violations(state)
            self.samples.append(dict(time_s=self.env.now, violations=list(violations), **asdict(state)))
            if self.env.now >= config.duration_s:
                break  # No zero-exposure lifecycle action at the observation boundary.
            forced = self.forced[1] if self.forced and self.forced[0] == self.env.now else None
            action, self.pressure, rejected, prediction = decide(
                config, snapshot, self.policy, self.reactive, forced)
            self.apply(action)
            self.decisions.append(dict(time_s=self.env.now, action=action.value,
                                       snapshot=asdict(snapshot), prediction=asdict(prediction),
                                       rejected=[{**r, "prediction": asdict(r["prediction"])} for r in rejected]))
            self.reactive = self.policy == "A2" and bool(violations)

    def run(self, stop_at=None):
        self.env.process(self.source())
        self.env.process(self.controls())
        if stop_at is None:
            self.env.run()  # Drain every admitted request, including late completions.
            assert len(self.outcomes) == len(self.tape.requests) and not self.pending
        else:
            self.env.run(until=stop_at + 1e-8)
        return self

    def summary(self):
        config = self.config
        blocks = [r for d in self.decisions for r in d["rejected"]]
        outcomes = sorted(self.outcomes, key=lambda r: r["request_id"])
        return dict(policy=self.policy, family=self.scenario.family, level=self.scenario.level,
                    tape_hash=self.tape.sha256, outcomes_hash=digest(outcomes),
                    total_service_contract_breach_seconds=sum(bool(s["violations"]) for s in self.samples) * config.tick_s,
                    p99_latency_ms=quantile([r["latency_ms"] for r in outcomes], .99),
                    sla_violation_rate=sum(r["latency_ms"] > config.intent.end_to_end_latency_ms for r in outcomes) / len(outcomes) if outcomes else 0.,
                    rollout_completed=self.fraction == 1. and self.completed_at is not None,
                    rollout_completion_time_s=self.completed_at - config.rollout_start_s if self.completed_at is not None else None,
                    interruption_time_s=sum(end - start for start, end in self.outages),
                    blocked_actions=len(blocks), local_blocks=sum(r["source"] == "local" for r in blocks),
                    contract_blocks=sum(r["source"] == "contract" for r in blocks),
                    rollback_count=self.rollback_count, request_count=len(outcomes), rejected_requests=0,
                    worker_seconds=self.worker_seconds)
