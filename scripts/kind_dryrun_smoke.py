"""Validate Phase 6 admission against an ephemeral CPU-only kind API server."""

import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from sovereign_maas.decision import decide, propose
from sovereign_maas.domain import ServiceBundle, SimulationRun, TypedIntent
from sovereign_maas.kubernetes import DeploymentBinding, KubernetesDryRunAdapter, PlanDenied, plan_scale
from sovereign_maas.simulation import execute, make_snapshot

CONTEXT = "kind-sovereign-maas-ci"
NAMESPACE = "sovereign-maas-ci"
DEPLOYMENT = "vision-demo"
PREVIEW_SA = "sovereign-maas-dryrun"
DENIED_SA = "sovereign-maas-denied"


def kubectl(*args: str, body: dict[str, Any] | None = None) -> str:
    completed = subprocess.run(
        ["kubectl", "--context", CONTEXT, *args],
        input=json.dumps(body) if body is not None else None,
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    )
    return completed.stdout.strip()


def apply(item: dict[str, Any]) -> None:
    kubectl("apply", "-f", "-", body=item)


def fixture(service: ServiceBundle) -> None:
    apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}})
    for name in (PREVIEW_SA, DENIED_SA):
        apply(
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {"name": name, "namespace": NAMESPACE},
            }
        )
    apply(
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {"name": "scale-preview", "namespace": NAMESPACE},
            "rules": [
                {
                    "apiGroups": ["apps"],
                    "resources": ["deployments"],
                    "resourceNames": [DEPLOYMENT],
                    "verbs": ["get"],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": ["deployments/scale"],
                    "resourceNames": [DEPLOYMENT],
                    "verbs": ["get", "update"],
                },
            ],
        }
    )
    apply(
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": "scale-preview", "namespace": NAMESPACE},
            "subjects": [{"kind": "ServiceAccount", "name": PREVIEW_SA, "namespace": NAMESPACE}],
            "roleRef": {"kind": "Role", "name": "scale-preview", "apiGroup": "rbac.authorization.k8s.io"},
        }
    )
    apply(
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {"name": "sovereign-maas-ci-self-review"},
            "rules": [
                {
                    "apiGroups": ["authorization.k8s.io"],
                    "resources": ["selfsubjectaccessreviews"],
                    "verbs": ["create"],
                }
            ],
        }
    )
    apply(
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {"name": "sovereign-maas-ci-self-review"},
            "subjects": [
                {"kind": "ServiceAccount", "name": name, "namespace": NAMESPACE}
                for name in (PREVIEW_SA, DENIED_SA)
            ],
            "roleRef": {
                "kind": "ClusterRole",
                "name": "sovereign-maas-ci-self-review",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        }
    )
    node = json.loads(kubectl("get", "nodes", "-o", "json"))["items"][0]["metadata"]["name"]
    kubectl("label", "node", node, "sovereign-maas/region=eu-gr", "--overwrite")
    apply(
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": DEPLOYMENT,
                "namespace": NAMESPACE,
                "labels": {
                    "sovereign-maas/tenant-id": service.tenant_id,
                    "sovereign-maas/service-id": service.id,
                },
            },
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": DEPLOYMENT}},
                "template": {
                    "metadata": {"labels": {"app": DEPLOYMENT}},
                    "spec": {
                        "nodeSelector": {"sovereign-maas/region": "eu-gr"},
                        "containers": [
                            {
                                "name": "inference",
                                "image": "registry.k8s.io/pause:3.10",
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "32Mi"},
                                    "limits": {"cpu": "200m", "memory": "64Mi"},
                                },
                            }
                        ],
                    },
                },
            },
        }
    )
    kubectl("-n", NAMESPACE, "rollout", "status", f"deployment/{DEPLOYMENT}", "--timeout=120s")


def main() -> None:
    if kubectl("config", "current-context") != CONTEXT:
        raise RuntimeError("refusing to use a non-ephemeral Kubernetes context")
    service = ServiceBundle(
        tenant_id="kind-ci",
        intent=TypedIntent(
            service_name=DEPLOYMENT,
            tier="Gold",
            latency_p95_ms=200,
            minimum_model_quality=0.9,
            max_replicas=4,
            allowed_regions=("eu-gr",),
            allowed_actions=("scale_out",),
        ),
    )
    fixture(service)
    snapshot = make_snapshot(7)
    candidates = propose(service, snapshot)
    decision = decide(service, snapshot, candidates)
    selected = next(item for item in candidates if item.id == decision.selected_candidate_id)
    run = SimulationRun(
        tenant_id=service.tenant_id,
        service_id=service.id,
        seed=7,
        snapshot=snapshot,
        candidates=candidates,
        decision=decision,
        verification=execute(service, snapshot, selected),
    )
    binding = DeploymentBinding(
        tenant_id=service.tenant_id,
        service_id=service.id,
        namespace=NAMESPACE,
        deployment=DEPLOYMENT,
        node_id="edge-a",
        region="eu-gr",
        require_hami_nvidia=False,
    )
    plan = plan_scale(service, run, binding)
    cluster = json.loads(kubectl("config", "view", "--raw", "--minify", "-o", "json"))["clusters"][0][
        "cluster"
    ]
    with tempfile.TemporaryDirectory() as directory:
        ca = Path(directory) / "kind-ca.pem"
        ca.write_bytes(base64.b64decode(cluster["certificate-authority-data"]))
        token = kubectl("-n", NAMESPACE, "create", "token", PREVIEW_SA, "--duration=10m")
        adapter = KubernetesDryRunAdapter(cluster["server"], token, ca)
        try:
            receipt = adapter.preview(plan)
        finally:
            adapter.close()
        assert receipt.evidence == "KUBERNETES_SERVER_DRY_RUN"
        assert receipt.persisted is False and receipt.dry_run_replicas == (2,)
        assert receipt.hami_profile == "NOT_REQUESTED"
        current = json.loads(kubectl("-n", NAMESPACE, "get", "deployment", DEPLOYMENT, "-o", "json"))
        assert current["spec"]["replicas"] == 1

        denied_token = kubectl("-n", NAMESPACE, "create", "token", DENIED_SA, "--duration=10m")
        denied = KubernetesDryRunAdapter(cluster["server"], denied_token, ca)
        try:
            try:
                denied.preview(plan)
            except PlanDenied as error:
                assert str(error) == "KUBERNETES_RBAC_DENIED"
            else:
                raise AssertionError("unprivileged service account unexpectedly passed preview")
        finally:
            denied.close()
    print("kind smoke passed: ready CPU Pod, real API dry-run, unchanged replicas and RBAC denial")


if __name__ == "__main__":
    main()
