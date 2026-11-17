"""Tenant-bound Deployment scale planning and Kubernetes server dry-run only."""

import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import ActionKind, ServiceBundle, SimulationRun, StrictModel, utc_now


class PlanDenied(ValueError):
    """A deterministic local precondition rejected a cluster proposal."""


class ClusterUnavailable(RuntimeError):
    """A bounded cluster request or validation failed without exposing credentials."""


class DeploymentBinding(StrictModel):
    """Trusted operator configuration, never filled from an intent or LLM."""

    tenant_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    namespace: str = Field(max_length=63, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    deployment: str = Field(max_length=63, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    node_id: str = Field(min_length=1)
    region: str = Field(min_length=1)
    require_hami_nvidia: bool = False


class ScalePlan(StrictModel):
    evidence: Literal["SIMULATED_PLAN"] = "SIMULATED_PLAN"
    created_at: datetime = Field(default_factory=utc_now)
    snapshot_observed_at: datetime
    run_id: str
    tenant_id: str
    service_id: str
    namespace: str
    deployment: str
    node_id: str
    region: str
    original_replicas: int = Field(ge=0)
    canary_replicas: int = Field(ge=1)
    target_replicas: int = Field(ge=1)
    rollback_replicas: int = Field(ge=0)
    latency_p95_target_ms: float = Field(gt=0)
    require_hami_nvidia: bool

    @model_validator(mode="after")
    def coherent(self) -> "ScalePlan":
        if self.created_at.tzinfo is None or self.snapshot_observed_at.tzinfo is None:
            raise ValueError("plan timestamps must be timezone-aware")
        if not (
            self.rollback_replicas == self.original_replicas < self.canary_replicas <= self.target_replicas
        ):
            raise ValueError("invalid canary/target/rollback sequence")
        return self


class CanaryObservation(StrictModel):
    evidence: Literal["SIMULATED"] = "SIMULATED"
    ready_replicas: int = Field(ge=0)
    observed_p95_ms: float = Field(ge=0)
    observed_at: datetime = Field(default_factory=utc_now)
    inject_failure: bool = False


class CanaryTrace(StrictModel):
    evidence: Literal["SIMULATED"] = "SIMULATED"
    states: tuple[str, ...]
    final_replicas: int = Field(ge=0)
    committed: bool
    reason: str


class DryRunReceipt(StrictModel):
    evidence: Literal["KUBERNETES_SERVER_DRY_RUN", "MOCK_KUBERNETES_DRY_RUN"]
    namespace: str
    deployment: str
    resource_version: str
    dry_run_replicas: tuple[int, ...]
    persisted: Literal[False] = False
    hami_profile: Literal["VALIDATED_RESOURCE_SHAPE", "NOT_REQUESTED"]
    scheduler_capacity: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"


def plan_scale(service: ServiceBundle, run: SimulationRun, binding: DeploymentBinding) -> ScalePlan:
    """Recheck simulator decision and trusted tenant/placement binding."""
    if (
        service.id != run.service_id
        or service.tenant_id != run.tenant_id
        or binding.tenant_id != service.tenant_id
        or binding.service_id != service.id
    ):
        raise PlanDenied("TENANT_OR_SERVICE_MISMATCH")
    age = (datetime.now(UTC) - run.snapshot.observed_at).total_seconds()
    if age < -1 or age > 30:
        raise PlanDenied("STALE_SIMULATED_SNAPSHOT")
    if run.decision.status != "SIMULATED":
        raise PlanDenied("DECISION_NOT_SIMULATED")
    candidate = next((item for item in run.candidates if item.id == run.decision.selected_candidate_id), None)
    if candidate is None or candidate.kind != ActionKind.SCALE_OUT:
        raise PlanDenied("SELECTED_ACTION_NOT_SCALE")
    if any(item.candidate_id == candidate.id for item in run.decision.rejected):
        raise PlanDenied("SELECTED_ACTION_REJECTED")
    if ActionKind.SCALE_OUT not in service.intent.allowed_actions:
        raise PlanDenied("ACTION_NOT_ALLOWED")
    if binding.region not in service.intent.allowed_regions or binding.node_id != candidate.target_node:
        raise PlanDenied("PLACEMENT_OR_RESIDENCY_DENIED")
    node = next((item for item in run.snapshot.nodes if item.id == binding.node_id), None)
    if node is None or node.region != binding.region:
        raise PlanDenied("SIMULATED_NODE_MISMATCH")
    if candidate.target_replicas <= run.snapshot.replicas:
        raise PlanDenied("NO_SCALE_CHANGE")
    if candidate.target_replicas > min(service.intent.max_replicas, node.replica_capacity):
        raise PlanDenied("SIMULATED_CAPACITY_DENIED")
    if not run.verification.slo_met:
        raise PlanDenied("SIMULATED_VERIFICATION_FAILED")
    return ScalePlan(
        run_id=run.id,
        snapshot_observed_at=run.snapshot.observed_at,
        tenant_id=service.tenant_id,
        service_id=service.id,
        namespace=binding.namespace,
        deployment=binding.deployment,
        node_id=binding.node_id,
        region=binding.region,
        original_replicas=run.snapshot.replicas,
        canary_replicas=run.snapshot.replicas + 1,
        target_replicas=candidate.target_replicas,
        rollback_replicas=run.snapshot.replicas,
        latency_p95_target_ms=service.intent.latency_p95_ms,
        require_hami_nvidia=binding.require_hami_nvidia,
    )


def simulate_canary(
    plan: ScalePlan,
    canary: CanaryObservation,
    final: CanaryObservation | None = None,
) -> CanaryTrace:
    """Exercise canary, verification, and compensation with simulated observations."""
    states = ["PLANNED", "CANARY_APPLIED"]

    def healthy(observation: CanaryObservation, replicas: int) -> bool:
        age = (datetime.now(UTC) - observation.observed_at).total_seconds()
        return (
            not observation.inject_failure
            and -1 <= age <= 30
            and observation.ready_replicas >= replicas
            and observation.observed_p95_ms <= plan.latency_p95_target_ms
        )

    if not healthy(canary, plan.canary_replicas):
        return CanaryTrace(
            states=(*states, "CANARY_FAILED", "ROLLBACK_APPLIED", "ROLLED_BACK"),
            final_replicas=plan.rollback_replicas,
            committed=False,
            reason="CANARY_VERIFICATION_FAILED",
        )
    states.append("CANARY_VERIFIED")
    if plan.target_replicas > plan.canary_replicas:
        states.append("TARGET_APPLIED")
        if final is None or not healthy(final, plan.target_replicas):
            return CanaryTrace(
                states=(*states, "TARGET_FAILED", "ROLLBACK_APPLIED", "ROLLED_BACK"),
                final_replicas=plan.rollback_replicas,
                committed=False,
                reason="TARGET_VERIFICATION_FAILED",
            )
        states.append("TARGET_VERIFIED")
    return CanaryTrace(
        states=(*states, "COMMITTED"),
        final_replicas=plan.target_replicas,
        committed=True,
        reason="SIMULATED_VERIFICATION_PASSED",
    )


class KubeMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    namespace: str
    uid: str
    resourceVersion: str
    labels: dict[str, str] = Field(default_factory=dict)


class KubeResources(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requests: dict[str, str | int] = Field(default_factory=dict)
    limits: dict[str, str | int] = Field(default_factory=dict)


class KubeContainer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    resources: KubeResources


class KubePodSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nodeSelector: dict[str, str]
    containers: list[KubeContainer] = Field(min_length=1)


class KubeTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    spec: KubePodSpec


class KubeDeploymentSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    replicas: int = Field(ge=0)
    template: KubeTemplate


class KubeDeployment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    apiVersion: Literal["apps/v1"]
    kind: Literal["Deployment"]
    metadata: KubeMeta
    spec: KubeDeploymentSpec


class KubeScaleSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    replicas: int = Field(ge=0)


class KubeScale(BaseModel):
    model_config = ConfigDict(extra="ignore")
    apiVersion: Literal["autoscaling/v1"]
    kind: Literal["Scale"]
    metadata: KubeMeta
    spec: KubeScaleSpec


def _integer_resource(resources: KubeResources, key: str, low: int, high: int | None = None) -> bool:
    value = resources.limits.get(key)
    request = resources.requests.get(key)
    if value is None or request is None or str(value) != str(request):
        return False
    try:
        number = int(str(value))
    except ValueError:
        return False
    return number >= low and (high is None or number <= high)


def validate_deployment(plan: ScalePlan, deployment: KubeDeployment, scale: KubeScale) -> str:
    """Require ownership, placement, current state and explicit resource shape."""
    metadata = deployment.metadata
    if (
        metadata.name != plan.deployment
        or metadata.namespace != plan.namespace
        or metadata.labels.get("sovereign-maas/tenant-id") != plan.tenant_id
        or metadata.labels.get("sovereign-maas/service-id") != plan.service_id
    ):
        raise PlanDenied("DEPLOYMENT_OWNERSHIP_MISMATCH")
    if (
        scale.metadata.name != plan.deployment
        or scale.metadata.namespace != plan.namespace
        or scale.metadata.uid != metadata.uid
        or scale.metadata.resourceVersion != metadata.resourceVersion
    ):
        raise PlanDenied("SCALE_IDENTITY_MISMATCH")
    if deployment.spec.replicas != plan.original_replicas or scale.spec.replicas != plan.original_replicas:
        raise PlanDenied("REPLICA_PRECONDITION_CHANGED")
    selector = deployment.spec.template.spec.nodeSelector
    if selector.get("sovereign-maas/region") != plan.region:
        raise PlanDenied("DEPLOYMENT_REGION_SELECTOR_MISMATCH")
    gpu_found = False
    for container in deployment.spec.template.spec.containers:
        resources = container.resources
        if not all(
            str(resources.requests.get(key, "")) not in ("", "0")
            and str(resources.limits.get(key, "")) not in ("", "0")
            for key in ("cpu", "memory")
        ):
            raise PlanDenied("CPU_MEMORY_RESOURCES_MISSING")
        if "nvidia.com/gpu" in resources.limits:
            gpu_found = True
            if not all(
                (
                    _integer_resource(resources, "nvidia.com/gpu", 1),
                    _integer_resource(resources, "nvidia.com/gpumem", 1),
                    _integer_resource(resources, "nvidia.com/gpucores", 1, 100),
                )
            ):
                raise PlanDenied("HAMI_RESOURCE_SHAPE_INVALID")
    if plan.require_hami_nvidia and not gpu_found:
        raise PlanDenied("HAMI_GPU_RESOURCE_MISSING")
    return "VALIDATED_RESOURCE_SHAPE" if gpu_found else "NOT_REQUESTED"


class KubernetesDryRunAdapter:
    """Typed REST adapter. Only GET, SSAR and PUT with dryRun=All are possible."""

    def __init__(
        self,
        server_url: str,
        bearer_token: str,
        ca_bundle: str | Path,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = httpx.URL(server_url)
        if url.scheme != "https" or url.path not in ("", "/") or url.query:
            raise ValueError("Kubernetes server URL must be an HTTPS origin")
        if not bearer_token or not str(ca_bundle):
            raise ValueError("Kubernetes token and CA bundle required")
        self.client = httpx.Client(
            base_url=server_url,
            headers={"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"},
            verify=str(ca_bundle),
            timeout=httpx.Timeout(5.0),
            follow_redirects=False,
            transport=transport,
        )
        self.mock_transport = transport is not None

    def close(self) -> None:
        self.client.close()

    def _json(self, method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> dict:
        try:
            response = self.client.request(method, path, json=body, params=params)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ClusterUnavailable("KUBERNETES_REQUEST_FAILED") from error
        if not isinstance(data, dict):
            raise ClusterUnavailable("KUBERNETES_RESPONSE_INVALID")
        return data

    def _check_access(self, plan: ScalePlan, resource: str, verb: str) -> None:
        review = self._json(
            "POST",
            "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
            body={
                "apiVersion": "authorization.k8s.io/v1",
                "kind": "SelfSubjectAccessReview",
                "spec": {
                    "resourceAttributes": {
                        "namespace": plan.namespace,
                        "group": "apps",
                        "resource": "deployments",
                        "subresource": resource,
                        "name": plan.deployment,
                        "verb": verb,
                    }
                },
            },
        )
        status = review.get("status")
        if (
            not isinstance(status, dict)
            or status.get("allowed") is not True
            or status.get("denied") is True
            or status.get("evaluationError")
        ):
            raise PlanDenied("KUBERNETES_RBAC_DENIED")

    def preview(self, plan: ScalePlan) -> DryRunReceipt:
        age = (datetime.now(UTC) - plan.created_at).total_seconds()
        if age < -1 or age > 30:
            raise PlanDenied("PLAN_EXPIRED")
        snapshot_age = (datetime.now(UTC) - plan.snapshot_observed_at).total_seconds()
        if snapshot_age < -1 or snapshot_age > 30:
            raise PlanDenied("STALE_SIMULATED_SNAPSHOT")
        for subresource, verb in (("", "get"), ("scale", "get"), ("scale", "update")):
            self._check_access(plan, subresource, verb)
        path = f"/apis/apps/v1/namespaces/{plan.namespace}/deployments/{plan.deployment}"
        try:
            deployment = KubeDeployment.model_validate(self._json("GET", path))
            scale = KubeScale.model_validate(self._json("GET", path + "/scale"))
        except ValueError as error:
            raise ClusterUnavailable("KUBERNETES_RESPONSE_INVALID") from error
        hami_profile = validate_deployment(plan, deployment, scale)
        attempts = tuple(dict.fromkeys((plan.canary_replicas, plan.target_replicas)))
        for replicas in attempts:
            payload = {
                "apiVersion": "autoscaling/v1",
                "kind": "Scale",
                "metadata": {
                    "name": plan.deployment,
                    "namespace": plan.namespace,
                    "resourceVersion": scale.metadata.resourceVersion,
                },
                "spec": {"replicas": replicas},
            }
            try:
                checked = KubeScale.model_validate(
                    self._json(
                        "PUT",
                        path + "/scale",
                        body=payload,
                        params={"dryRun": "All", "fieldValidation": "Strict"},
                    )
                )
            except ValueError as error:
                raise ClusterUnavailable("KUBERNETES_RESPONSE_INVALID") from error
            if (
                checked.spec.replicas != replicas
                or checked.metadata.uid != scale.metadata.uid
                or checked.metadata.name != plan.deployment
                or checked.metadata.namespace != plan.namespace
            ):
                raise ClusterUnavailable("KUBERNETES_DRY_RUN_MISMATCH")
        return DryRunReceipt(
            evidence="MOCK_KUBERNETES_DRY_RUN" if self.mock_transport else "KUBERNETES_SERVER_DRY_RUN",
            namespace=plan.namespace,
            deployment=plan.deployment,
            resource_version=scale.metadata.resourceVersion,
            dry_run_replicas=attempts,
            hami_profile=hami_profile,
        )


class HamiGpuSample(StrictModel):
    evidence: Literal["HAMI_EXPORTER_MEASURED", "MOCK_HAMI_EXPORTER"]
    node: str
    device_uuid: str
    utilization_pct: float = Field(ge=0, le=100)
    memory_used_bytes: int = Field(ge=0)
    scraped_at: datetime = Field(default_factory=utc_now)


_METRIC = re.compile(
    r"^(hami_host_gpu_utilization_ratio|hami_host_gpu_memory_used_bytes)\{([^}]*)\}\s+"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:\s+\d+)?$"
)
_NODE = re.compile(r'(?:^|,)node="([a-zA-Z0-9.-]+)"(?:,|$)')
_DEVICE = re.compile(r'(?:^|,)device_uuid="([a-zA-Z0-9-]+)"(?:,|$)')


class HamiMetricsReader:
    """Read exact HAMi host metrics from an operator-configured exporter URL."""

    def __init__(
        self,
        endpoint: str,
        allowed_nodes: set[str],
        *,
        allow_plain_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = httpx.URL(endpoint)
        if (
            url.scheme not in (("https", "http") if allow_plain_http else ("https",))
            or url.path != "/metrics"
            or url.query
            or url.fragment
            or url.userinfo
            or not allowed_nodes
        ):
            raise ValueError("HAMi endpoint must be a configured metrics URL with allowed nodes")
        self.allowed_nodes = set(allowed_nodes)
        self.endpoint = endpoint
        self.mock_transport = transport is not None
        self.client = httpx.Client(timeout=httpx.Timeout(3.0), follow_redirects=False, transport=transport)

    def close(self) -> None:
        self.client.close()

    def read(self) -> tuple[HamiGpuSample, ...]:
        try:
            response = self.client.get(self.endpoint)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ClusterUnavailable("HAMI_METRICS_UNAVAILABLE") from error
        if len(response.content) > 1_000_000:
            raise ClusterUnavailable("HAMI_METRICS_TOO_LARGE")
        values: dict[tuple[str, str], dict[str, float]] = {}
        for line in response.text.splitlines():
            match = _METRIC.fullmatch(line.strip())
            if match is None:
                continue
            node_match = _NODE.search(match[2])
            device_match = _DEVICE.search(match[2])
            if node_match is None or device_match is None or node_match[1] not in self.allowed_nodes:
                continue
            value = float(match[3])
            if not math.isfinite(value):
                raise ClusterUnavailable("HAMI_METRIC_INVALID")
            values.setdefault((node_match[1], device_match[1]), {})[match[1]] = value
        samples = []
        for (node, device), metrics in sorted(values.items()):
            utilization = metrics.get("hami_host_gpu_utilization_ratio")
            memory = metrics.get("hami_host_gpu_memory_used_bytes")
            if (
                utilization is None
                or memory is None
                or not 0 <= utilization <= 100
                or memory < 0
                or not memory.is_integer()
            ):
                raise ClusterUnavailable("HAMI_METRICS_INCOMPLETE")
            samples.append(
                HamiGpuSample(
                    evidence="MOCK_HAMI_EXPORTER" if self.mock_transport else "HAMI_EXPORTER_MEASURED",
                    node=node,
                    device_uuid=device,
                    utilization_pct=utilization,
                    memory_used_bytes=int(memory),
                )
            )
        if not samples:
            raise ClusterUnavailable("HAMI_METRICS_UNAVAILABLE")
        return tuple(samples)
