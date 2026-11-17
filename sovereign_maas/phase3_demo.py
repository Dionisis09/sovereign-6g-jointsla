"""One-command offline Phase 3 workflow demo; no external service or key."""

import json
import secrets
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from .api import create_app


def main() -> None:
    text = (
        "service: vision-demo; tier: Gold; p95: 200; quality: 0.9; "
        "replicas: 4; regions: eu-gr; actions: scale_out"
    )
    with TemporaryDirectory() as directory:
        operator_token = secrets.token_urlsafe(24)
        approver_token = secrets.token_urlsafe(24)
        app = create_app(
            f"{directory}/maas.sqlite3",
            {"demo": operator_token},
            approver_tokens={"demo": approver_token},
        )
        with TestClient(app) as client:
            headers = {"X-Tenant-Token": operator_token, "Idempotency-Key": "phase3-demo"}
            started = client.post("/v1/workflows", json={"text": text, "seed": 7}, headers=headers)
            started.raise_for_status()
            pending = started.json()
            approved = client.post(
                f"/v1/workflows/{pending['id']}/approve",
                json={"approved": True},
                headers={**headers, "X-Approver-Token": approver_token},
            )
            approved.raise_for_status()
            finished = approved.json()
            run = client.get(f"/v1/simulations/{finished['run_id']}", headers=headers)
            run.raise_for_status()
            print(
                json.dumps(
                    {
                        "before_approval": pending["status"],
                        "after_approval": finished["status"],
                        "selected_candidate_id": finished["selected_candidate_id"],
                        "citations": finished["citations"],
                        "verification_evidence": run.json()["verification"]["evidence"],
                    },
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    main()
