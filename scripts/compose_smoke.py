"""Exercise the real loopback Compose stack without printing its demo credentials."""

import json
import time
import urllib.error
import urllib.request
from typing import Any

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:3000"


def request(url: str, body: dict[str, Any] | None = None) -> tuple[int, str]:
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=payload, headers=headers), timeout=10
        ) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def ready(url: str) -> None:
    for _ in range(60):
        try:
            if request(url)[0] == 200:
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    raise RuntimeError(f"service did not become ready: {url}")


def main() -> None:
    ready(f"{API}/health/ready")
    ready(WEB)
    status, html = request(WEB)
    assert status == 200 and "Sovereign MaaS" in html
    assert request(f"{WEB}/api/maas/admin/secret")[0] == 404
    status, body = request(
        f"{WEB}/api/maas/intents",
        {
            "service_name": "compose-smoke",
            "tier": "Gold",
            "latency_p95_ms": 200,
            "minimum_model_quality": 0.9,
            "max_replicas": 3,
            "allowed_regions": ["eu-gr"],
            "allowed_actions": ["noop", "scale_out"],
        },
    )
    assert status == 201, body
    service_id = json.loads(body)["id"]
    status, body = request(f"{WEB}/api/maas/simulations/run", {"service_id": service_id, "seed": 7})
    assert status == 201 and json.loads(body)["verification"]["evidence"] == "SIMULATED", body
    status, body = request(f"{WEB}/api/maas/simulations")
    assert status == 200 and any(item["service_id"] == service_id for item in json.loads(body))
    assert request(f"{WEB}/api/maas/research/summary")[0] == 200
    print("Compose smoke passed: healthy containers, Next proxy, API, SQLite, simulator and research")


if __name__ == "__main__":
    main()
