"""One-command offline judgment fixture and unchanged policy demo."""

import json
import secrets
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from .api import create_app
from .judgment import FixtureJudgmentProvider


def main() -> None:
    intent = {
        "service_name": "vision-demo",
        "tier": "Gold",
        "latency_p95_ms": 200,
        "minimum_model_quality": 0.9,
        "max_replicas": 4,
        "allowed_regions": ["eu-gr"],
        "allowed_actions": ["scale_out"],
    }
    with TemporaryDirectory() as directory:
        token = secrets.token_urlsafe(24)
        app = create_app(
            f"{directory}/maas.sqlite3",
            {"demo": token},
            judgment_provider=FixtureJudgmentProvider(),
        )
        with TestClient(app) as client:
            headers = {"X-Tenant-Token": token}
            service_response = client.post("/v1/intents", json=intent, headers=headers)
            service_response.raise_for_status()
            service = service_response.json()
            request = {"service_id": service["id"], "seed": 7}
            advisory_response = client.post("/v1/judgments/evaluate", json=request, headers=headers)
            advisory_response.raise_for_status()
            run_response = client.post(
                "/v1/simulations/run",
                json=request,
                headers={**headers, "Idempotency-Key": "phase4-demo"},
            )
            run_response.raise_for_status()
            advisory = advisory_response.json()
            run = run_response.json()
            print(
                json.dumps(
                    {
                        "judgment_source": advisory["source"],
                        "judgment_status": advisory["status"],
                        "judgment_reason": advisory["reason"],
                        "decision": run["decision"]["selected_candidate_id"],
                        "verification_evidence": run["verification"]["evidence"],
                    },
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    main()
