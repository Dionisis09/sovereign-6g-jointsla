"""CPU-only Phase 6 contract tests; all Kubernetes traffic uses MockTransport."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sovereign_maas.decision import decide, propose
from sovereign_maas.domain import ServiceBundle, SimulationRun, TypedIntent
from sovereign_maas.kubernetes import (
    CanaryObservation,
    ClusterUnavailable,
    DeploymentBinding,
    HamiMetricsReader,
    KubernetesDryRunAdapter,
    PlanDenied,
    ScalePlan,
    plan_scale,
    simulate_canary,
)
from sovereign_maas.simulation import execute, make_snapshot


def sample() -> tuple[ServiceBundle, SimulationRun, DeploymentBinding]:
    service = ServiceBundle(
        tenant_id="tenant-a",
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
        tenant_id="tenant-a",
        service_id=service.id,
        namespace="tenant-a-edge",
        deployment="vision-demo",
        node_id="edge-a",
        region="eu-gr",
        require_hami_nvidia=True,
    )
    return service, run, binding


def mock_objects(plan: ScalePlan) -> tuple[dict, dict]:
    metadata = {
        "name": plan.deployment,
        "namespace": plan.namespace,
        "uid": "deployment-uid",
        "resourceVersion": "123",
        "labels": {
            "sovereign-maas/tenant-id": plan.tenant_id,
            "sovereign-maas/service-id": plan.service_id,
        },
    }
    scale = {
        "apiVersion": "autoscaling/v1",
        "kind": "Scale",
        "metadata": metadata,
        "spec": {"replicas": plan.original_replicas},
    }
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": metadata,
        "spec": {
            "replicas": plan.original_replicas,
            "template": {
                "spec": {
                    "nodeSelector": {"sovereign-maas/region": plan.region},
                    "containers": [
                        {
                            "name": "inference",
                            "resources": {
                                "requests": {
                                    "cpu": "500m",
                                    "memory": "1Gi",
                                    "nvidia.com/gpu": "1",
                                    "nvidia.com/gpumem": "3000",
                                    "nvidia.com/gpucores": "50",
                                },
                                "limits": {
                                    "cpu": "1",
                                    "memory": "2Gi",
                                    "nvidia.com/gpu": "1",
                                    "nvidia.com/gpumem": "3000",
                                    "nvidia.com/gpucores": "50",
                                },
                            },
                        }
                    ],
                }
            },
        },
    }
    return deployment, scale


def test_plan_rechecks_tenant_action_residency_freshness_and_capacity():
    service, run, binding = sample()
    plan = plan_scale(service, run, binding)
    assert plan.evidence == "SIMULATED_PLAN"
    assert plan.target_replicas == 2
    assert plan.canary_replicas == 2
    assert plan.rollback_replicas == 1
    with pytest.raises(PlanDenied, match="TENANT_OR_SERVICE_MISMATCH"):
        plan_scale(service, run, binding.model_copy(update={"tenant_id": "tenant-b"}))
    with pytest.raises(PlanDenied, match="PLACEMENT_OR_RESIDENCY_DENIED"):
        plan_scale(service, run, binding.model_copy(update={"region": "eu-de"}))
    with pytest.raises(PlanDenied, match="NO_SCALE_CHANGE"):
        changed = run.model_copy(update={"snapshot": run.snapshot.model_copy(update={"replicas": 2})})
        plan_scale(service, changed, binding)
    with pytest.raises(PlanDenied, match="STALE_SIMULATED_SNAPSHOT"):
        stale = run.model_copy(
            update={
                "snapshot": run.snapshot.model_copy(
                    update={"observed_at": datetime.now(UTC) - timedelta(minutes=1)}
                )
            }
        )
        plan_scale(service, stale, binding)


def test_simulated_canary_commit_and_both_rollback_paths():
    service, run, binding = sample()
    plan = plan_scale(service, run, binding)
    good = CanaryObservation(ready_replicas=2, observed_p95_ms=140)
    trace = simulate_canary(plan, good)
    assert trace.committed and trace.final_replicas == 2 and trace.states[-1] == "COMMITTED"
    failed = simulate_canary(plan, CanaryObservation(ready_replicas=1, observed_p95_ms=250))
    assert not failed.committed and failed.final_replicas == 1 and failed.states[-1] == "ROLLED_BACK"
    expanded = ScalePlan.model_validate({**plan.model_dump(), "target_replicas": 3})
    final_failed = simulate_canary(expanded, good, CanaryObservation(ready_replicas=2, observed_p95_ms=120))
    assert not final_failed.committed and final_failed.reason == "TARGET_VERIFICATION_FAILED"
    final_good = simulate_canary(expanded, good, CanaryObservation(ready_replicas=3, observed_p95_ms=150))
    assert final_good.committed and final_good.final_replicas == 3


@pytest.mark.parametrize("target_replicas", [2, 3])
def test_kubernetes_dry_run_uses_ssar_bound_get_and_non_persisting_scale(target_replicas: int):
    service, run, binding = sample()
    plan = ScalePlan.model_validate(
        {**plan_scale(service, run, binding).model_dump(), "target_replicas": target_replicas}
    )
    deployment, scale = mock_objects(plan)
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        assert request.headers["Authorization"] == "Bearer cluster-secret"
        if request.url.path.endswith("selfsubjectaccessreviews"):
            attrs = json.loads(request.content)["spec"]["resourceAttributes"]
            assert attrs["namespace"] == plan.namespace and attrs["name"] == plan.deployment
            return httpx.Response(201, json={"status": {"allowed": True, "denied": False}})
        if request.method == "GET" and request.url.path.endswith("/scale"):
            return httpx.Response(200, json=scale)
        if request.method == "GET":
            return httpx.Response(200, json=deployment)
        assert request.method == "PUT"
        assert request.url.params["dryRun"] == "All"
        assert request.url.params["fieldValidation"] == "Strict"
        body = json.loads(request.content)
        assert body["metadata"]["resourceVersion"] == "123"
        return httpx.Response(200, json={**scale, "spec": {"replicas": body["spec"]["replicas"]}})

    adapter = KubernetesDryRunAdapter(
        "https://k8s.example", "cluster-secret", "unused-ca-in-mock", transport=httpx.MockTransport(handler)
    )
    try:
        receipt = adapter.preview(plan)
    finally:
        adapter.close()
    assert receipt.evidence == "MOCK_KUBERNETES_DRY_RUN"
    assert receipt.persisted is False
    assert receipt.hami_profile == "VALIDATED_RESOURCE_SHAPE"
    assert receipt.scheduler_capacity == "NOT_VERIFIED"
    assert [method for method, _ in seen] == ["POST", "POST", "POST", "GET", "GET"] + ["PUT"] * (
        target_replicas - 1
    )
    assert receipt.dry_run_replicas == tuple(range(2, target_replicas + 1))
    assert all(plan.namespace in url or "selfsubjectaccessreviews" in url for _, url in seen)


@pytest.mark.parametrize(
    "change,expected",
    [
        ("tenant_label", "DEPLOYMENT_OWNERSHIP_MISMATCH"),
        ("region", "DEPLOYMENT_REGION_SELECTOR_MISMATCH"),
        ("replicas", "REPLICA_PRECONDITION_CHANGED"),
        ("gpucores", "HAMI_RESOURCE_SHAPE_INVALID"),
    ],
)
def test_deployment_validation_fails_closed(change: str, expected: str):
    service, run, binding = sample()
    plan = plan_scale(service, run, binding)
    deployment, scale = mock_objects(plan)
    if change == "tenant_label":
        deployment["metadata"]["labels"]["sovereign-maas/tenant-id"] = "tenant-b"
    elif change == "region":
        deployment["spec"]["template"]["spec"]["nodeSelector"]["sovereign-maas/region"] = "eu-de"
    elif change == "replicas":
        deployment["spec"]["replicas"] = 3
    else:
        deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"][
            "nvidia.com/gpucores"
        ] = "101"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("selfsubjectaccessreviews"):
            return httpx.Response(201, json={"status": {"allowed": True}})
        if request.url.path.endswith("/scale"):
            return httpx.Response(200, json=scale)
        return httpx.Response(200, json=deployment)

    adapter = KubernetesDryRunAdapter(
        "https://k8s.example", "cluster-secret", "unused-ca-in-mock", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(PlanDenied, match=expected):
            adapter.preview(plan)
    finally:
        adapter.close()


def test_hami_host_metrics_are_read_only_scoped_and_provenanced():
    payload = """# HELP hami_host_gpu_utilization_ratio GPU utilization
hami_host_gpu_utilization_ratio{device_uuid="GPU-a",node="gpu-a"} 37
hami_host_gpu_memory_used_bytes{node="gpu-a",device_uuid="GPU-a"} 2.5e8
hami_host_gpu_utilization_ratio{node="gpu-b",device_uuid="GPU-b"} 90
hami_host_gpu_memory_used_bytes{node="gpu-b",device_uuid="GPU-b"} 500"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.path == "/metrics"
        return httpx.Response(200, text=payload)

    reader = HamiMetricsReader(
        "https://hami.example/metrics", {"gpu-a"}, transport=httpx.MockTransport(handler)
    )
    try:
        samples = reader.read()
    finally:
        reader.close()
    assert len(samples) == 1
    assert samples[0].evidence == "MOCK_HAMI_EXPORTER"
    assert samples[0].node == "gpu-a"
    assert samples[0].utilization_pct == 37
    assert samples[0].memory_used_bytes == 250_000_000
    with pytest.raises(ValueError, match="configured metrics URL"):
        HamiMetricsReader("http://hami.example/metrics", {"gpu-a"})


def test_hami_missing_or_invalid_metrics_fail_closed():
    for payload in (
        'hami_host_gpu_utilization_ratio{node="gpu-a",device_uuid="GPU-a"} 45',
        """hami_host_gpu_utilization_ratio{node="gpu-a",device_uuid="GPU-a"} 120
hami_host_gpu_memory_used_bytes{node="gpu-a",device_uuid="GPU-a"} 100""",
    ):

        def handler(request: httpx.Request, selected_payload: str = payload) -> httpx.Response:
            return httpx.Response(200, text=selected_payload)

        reader = HamiMetricsReader(
            "https://hami.example/metrics",
            {"gpu-a"},
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ClusterUnavailable, match="HAMI_METRICS_INCOMPLETE"):
                reader.read()
        finally:
            reader.close()


def test_rbac_denial_and_bad_cluster_response_stop_before_write():
    service, run, binding = sample()
    plan = plan_scale(service, run, binding)
    seen: list[str] = []

    def deny(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(201, json={"status": {"allowed": False, "denied": True}})

    adapter = KubernetesDryRunAdapter(
        "https://k8s.example", "secret", "mock-ca", transport=httpx.MockTransport(deny)
    )
    try:
        with pytest.raises(PlanDenied, match="KUBERNETES_RBAC_DENIED"):
            adapter.preview(plan)
    finally:
        adapter.close()

    expired = ScalePlan.model_validate(
        {**plan.model_dump(), "created_at": datetime.now(UTC) - timedelta(minutes=1)}
    )
    adapter = KubernetesDryRunAdapter(
        "https://k8s.example", "secret", "mock-ca", transport=httpx.MockTransport(deny)
    )
    try:
        with pytest.raises(PlanDenied, match="PLAN_EXPIRED"):
            adapter.preview(expired)
    finally:
        adapter.close()
    stale_snapshot = ScalePlan.model_validate(
        {**plan.model_dump(), "snapshot_observed_at": datetime.now(UTC) - timedelta(minutes=1)}
    )
    adapter = KubernetesDryRunAdapter(
        "https://k8s.example", "secret", "mock-ca", transport=httpx.MockTransport(deny)
    )
    try:
        with pytest.raises(PlanDenied, match="STALE_SIMULATED_SNAPSHOT"):
            adapter.preview(stale_snapshot)
    finally:
        adapter.close()
    assert seen == ["POST"]
    with pytest.raises(ValueError, match="HTTPS origin"):
        KubernetesDryRunAdapter("http://k8s.example", "secret", "mock-ca")

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "secret server details"})

    adapter = KubernetesDryRunAdapter(
        "https://k8s.example", "secret", "mock-ca", transport=httpx.MockTransport(broken)
    )
    try:
        with pytest.raises(ClusterUnavailable, match="KUBERNETES_REQUEST_FAILED") as error:
            adapter.preview(plan)
        assert "secret server details" not in str(error.value)
    finally:
        adapter.close()
