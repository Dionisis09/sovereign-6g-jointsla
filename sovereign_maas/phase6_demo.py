"""One-command CPU-only canary and rollback demonstration; no cluster calls."""

import json

from .decision import decide, propose
from .domain import ServiceBundle, SimulationRun, TypedIntent
from .kubernetes import CanaryObservation, DeploymentBinding, plan_scale, simulate_canary
from .simulation import execute, make_snapshot


def main() -> None:
    service = ServiceBundle(
        tenant_id="local-demo",
        intent=TypedIntent(
            service_name="vision-demo",
            tier="Gold",
            latency_p95_ms=200,
            minimum_model_quality=0.9,
            max_replicas=4,
            allowed_regions=("eu-gr",),
            allowed_actions=("scale_out",),
        ),
    )
    snapshot = make_snapshot(7)
    candidates = propose(service, snapshot)
    decision = decide(service, snapshot, candidates)
    chosen = next(item for item in candidates if item.id == decision.selected_candidate_id)
    run = SimulationRun(
        tenant_id=service.tenant_id,
        service_id=service.id,
        seed=7,
        snapshot=snapshot,
        candidates=candidates,
        decision=decision,
        verification=execute(service, snapshot, chosen),
    )
    binding = DeploymentBinding(
        tenant_id=service.tenant_id,
        service_id=service.id,
        namespace="local-demo-edge",
        deployment=service.intent.service_name,
        node_id="edge-a",
        region="eu-gr",
        require_hami_nvidia=True,
    )
    plan = plan_scale(service, run, binding)
    committed = simulate_canary(
        plan, CanaryObservation(ready_replicas=plan.canary_replicas, observed_p95_ms=140)
    )
    rolled_back = simulate_canary(
        plan, CanaryObservation(ready_replicas=0, observed_p95_ms=250, inject_failure=True)
    )
    print(
        json.dumps(
            {
                "plan": plan.model_dump(mode="json"),
                "simulated_success": committed.model_dump(mode="json"),
                "simulated_failure": rolled_back.model_dump(mode="json"),
                "cluster_called": False,
                "gpu_metrics_available": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
