"""Bounded local request metrics and redacted request logs."""

import json
import logging
import threading
import time
from collections import Counter, defaultdict
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import Response


class RequestMetrics:
    buckets = (0.01, 0.05, 0.1, 0.5, 1.0, 5.0)

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts: Counter[tuple[str, str, int]] = Counter()
        self.duration_counts: Counter[tuple[str, str, float]] = Counter()
        self.duration_sum: dict[tuple[str, str], float] = defaultdict(float)

    def record(self, method: str, route: str, status: int, seconds: float) -> None:
        with self.lock:
            self.counts[(method, route, status)] += 1
            self.duration_sum[(method, route)] += seconds
            for bound in self.buckets:
                if seconds <= bound:
                    self.duration_counts[(method, route, bound)] += 1

    def render(self) -> str:
        lines = [
            "# HELP sovereign_http_requests_total HTTP requests by template route and status",
            "# TYPE sovereign_http_requests_total counter",
        ]
        with self.lock:
            for (method, route, status), value in sorted(self.counts.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.append(f"sovereign_http_requests_total{{{labels}}} {value}")
            lines += [
                "# HELP sovereign_http_request_duration_seconds Request duration",
                "# TYPE sovereign_http_request_duration_seconds histogram",
            ]
            for method, route in sorted(self.duration_sum):
                base = f'method="{method}",route="{route}"'
                for bound in self.buckets:
                    value = self.duration_counts[(method, route, bound)]
                    lines.append(
                        f'sovereign_http_request_duration_seconds_bucket{{{base},le="{bound}"}} {value}'
                    )
                total = sum(
                    value
                    for (candidate_method, candidate_route, _), value in self.counts.items()
                    if candidate_method == method and candidate_route == route
                )
                lines.append(f'sovereign_http_request_duration_seconds_bucket{{{base},le="+Inf"}} {total}')
                lines.append(
                    f"sovereign_http_request_duration_seconds_sum{{{base}}} {self.duration_sum[(method, route)]}"
                )
                lines.append(f"sovereign_http_request_duration_seconds_count{{{base}}} {total}")
        return "\n".join(lines) + "\n"


def install_observability(app: FastAPI, metrics_token: str | None) -> None:
    metrics = RequestMetrics()
    logger = logging.getLogger("sovereign_maas.requests")

    @app.middleware("http")
    async def observe(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        correlation_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(json.dumps({"correlation_id": correlation_id, "event": "request_failed"}))
            raise
        duration = time.perf_counter() - started
        route_obj = request.scope.get("route")
        route = getattr(route_obj, "path", "unmatched")
        if route != "/metrics":
            metrics.record(request.method, route, response.status_code, duration)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            json.dumps(
                {
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                }
            )
        )
        return response

    @app.get("/metrics", include_in_schema=False)
    def get_metrics(request: Request) -> Response:
        if not metrics_token:
            return Response(status_code=503)
        from hmac import compare_digest

        supplied = request.headers.get("X-Metrics-Token", "")
        if not compare_digest(supplied, metrics_token):
            return Response(status_code=403)
        return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
