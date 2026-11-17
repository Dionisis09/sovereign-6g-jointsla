"""Exercise production Next server -> authenticated FastAPI -> SQLite locally."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch(url: str, data: dict[str, object] | None = None) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def wait_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"server exited with {process.returncode}")
        try:
            if fetch(url)[0] == 200:
                return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"server did not become ready: {url}")


def main() -> None:
    api_port, web_port = free_port(), free_port()
    with tempfile.TemporaryDirectory() as directory:
        api_env = os.environ.copy()
        api_env.update(
            {
                "SOVEREIGN_TENANT_TOKENS": json.dumps({"smoke": "local-smoke-token"}),
                "SOVEREIGN_APPROVER_TOKENS": json.dumps({"smoke": "local-approver-token"}),
                "SOVEREIGN_DB_PATH": str(Path(directory) / "smoke.sqlite3"),
                "SOVEREIGN_MODEL_DIR": str(ROOT / "results" / "phase2-v1"),
                "SOVEREIGN_RESEARCH_DIR": str(ROOT / "results"),
            }
        )
        web_env = os.environ.copy()
        web_env.update(
            {
                "SOVEREIGN_API_BASE_URL": f"http://127.0.0.1:{api_port}",
                "SOVEREIGN_DASHBOARD_TENANT_TOKEN": "local-smoke-token",
                "SOVEREIGN_DASHBOARD_APPROVER_TOKEN": "local-approver-token",
                "NEXT_TELEMETRY_DISABLED": "1",
            }
        )
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sovereign_maas.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            cwd=ROOT,
            env=api_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        web = None
        try:
            wait_ready(f"http://127.0.0.1:{api_port}/health/ready", api)
            web = subprocess.Popen(
                [
                    "node",
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=ROOT / "apps" / "web",
                env=web_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base = f"http://127.0.0.1:{web_port}"
            wait_ready(base, web)
            status, html = fetch(base)
            assert status == 200 and "Sovereign MaaS" in html
            assert "local-smoke-token" not in html and "local-approver-token" not in html
            status, body = fetch(f"{base}/api/maas/services")
            assert status == 200 and json.loads(body) == []
            status, body = fetch(
                f"{base}/api/maas/intents",
                {
                    "service_name": "phase-five-smoke",
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
            status, body = fetch(f"{base}/api/maas/simulations/run", {"service_id": service_id, "seed": 7})
            assert status == 201 and json.loads(body)["verification"]["evidence"] == "SIMULATED", body
            assert len(json.loads(fetch(f"{base}/api/maas/simulations")[1])) == 1
            assert fetch(f"{base}/api/maas/research/summary")[0] == 200
            assert fetch(f"{base}/api/maas/admin/secret")[0] == 404
            print(
                "Phase 5 HTTP smoke passed: Next -> API -> SQLite -> simulator -> research; secrets absent from HTML"
            )
        finally:
            if web is not None:
                web.terminate()
                web.wait(timeout=10)
            api.terminate()
            api.wait(timeout=10)


if __name__ == "__main__":
    main()
