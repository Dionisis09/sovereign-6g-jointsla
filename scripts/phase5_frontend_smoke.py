"""Production Next server smoke that does not need the Python API."""

import os
import subprocess
from pathlib import Path

from phase5_http_smoke import fetch, free_port, wait_ready

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    port = free_port()
    env = os.environ.copy()
    env.pop("SOVEREIGN_API_BASE_URL", None)
    env.pop("SOVEREIGN_DASHBOARD_TENANT_TOKEN", None)
    env.pop("SOVEREIGN_DASHBOARD_APPROVER_TOKEN", None)
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    web = subprocess.Popen(
        ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(port)],
        cwd=ROOT / "apps" / "web",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        wait_ready(base, web)
        status, html = fetch(base)
        assert status == 200 and "Sovereign MaaS" in html
        assert fetch(f"{base}/api/maas/services")[0] == 503
        assert fetch(f"{base}/api/maas/admin/secret")[0] == 404
        print("Phase 5 frontend smoke passed: production page, missing config state, proxy allowlist")
    finally:
        web.terminate()
        web.wait(timeout=10)


if __name__ == "__main__":
    main()
