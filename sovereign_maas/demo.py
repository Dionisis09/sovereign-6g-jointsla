"""One-command local API demonstration with an ephemeral token and SQLite file."""

import json
import secrets
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from .api import create_app


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sovereign-maas-") as temp:
        token = secrets.token_urlsafe(32)
        app = create_app(Path(temp) / "demo.sqlite3", {"demo-tenant": token})
        with TestClient(app) as client:
            headers = {"X-Tenant-Token": token}
            intent = {
                "service_name": "vision-demo",
                "tier": "Gold",
                "latency_p95_ms": 200,
                "minimum_model_quality": 0.9,
                "max_replicas": 4,
                "allowed_regions": ["eu-gr"],
                "allowed_actions": ["scale_out"],
            }
            response = client.post("/v1/intents", json=intent, headers=headers)
            response.raise_for_status()
            service = response.json()
            response = client.post(
                "/v1/simulations/run",
                json={"service_id": service["id"], "seed": 7},
                headers={**headers, "Idempotency-Key": "demo-seed-7"},
            )
            response.raise_for_status()
            result = response.json()
            print(
                json.dumps(
                    {
                        "service_id": service["id"],
                        "run_id": result["id"],
                        "seed": result["seed"],
                        "candidate_sources": [c["source"] for c in result["candidates"]],
                        "selected": result["decision"]["selected_candidate_id"],
                        "rejected": result["decision"]["rejected"],
                        "simulated_p95_ms": result["verification"]["measured_p95_ms"],
                        "simulated_slo_met": result["verification"]["slo_met"],
                        "evidence": result["verification"]["evidence"],
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
