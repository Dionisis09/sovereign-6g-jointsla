"""Authenticated local FastAPI surface. Simulation is the only action backend."""

import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from .decision import decide, propose
from .domain import (
    ApprovalRequest,
    ForecastBundle,
    JudgmentRecord,
    NaturalIntentRequest,
    ParsedIntent,
    RunRequest,
    ServiceBundle,
    SimulationRun,
    TypedIntent,
    WorkflowRecord,
    WorkflowRequest,
)
from .forecast import ForecastProvider
from .genai import (
    IntentParseError,
    IntentParser,
    OfflineIntentParser,
    OpenAIIntentParser,
    ProviderUnavailable,
)
from .judgment import (
    DisabledJudgmentProvider,
    FixtureJudgmentProvider,
    JudgmentProvider,
    TypeSafeJevProvider,
)
from .knowledge import KnowledgeBase, KnowledgeHit
from .observability import install_observability
from .simulation import execute, make_snapshot
from .store import Store
from .workflow import WorkflowEngine


def create_app(
    db_path: str | Path,
    tenant_tokens: dict[str, str] | None = None,
    predictor: ForecastProvider | None = None,
    approver_tokens: dict[str, str] | None = None,
    parser: IntentParser | None = None,
    knowledge: KnowledgeBase | None = None,
    live_llm_tenants: set[str] | None = None,
    judgment_provider: JudgmentProvider | None = None,
    metrics_token: str | None = None,
    research_dir: str | Path | None = None,
) -> FastAPI:
    credentials = dict(tenant_tokens or {})
    if any(not tenant or not token for tenant, token in credentials.items()):
        raise ValueError("tenant IDs and tokens must be nonempty")
    if len(set(credentials.values())) != len(credentials):
        raise ValueError("tenant tokens must be unique")
    approvers = dict(approver_tokens or {})
    if any(tenant not in credentials or not token for tenant, token in approvers.items()):
        raise ValueError("approver tokens require a configured tenant and nonempty token")
    if len(set(approvers.values())) != len(approvers) or set(approvers.values()) & set(credentials.values()):
        raise ValueError("approver tokens must be unique and distinct from tenant tokens")
    store = Store(db_path)
    intent_parser = parser or OfflineIntentParser()
    live_allowed = set(live_llm_tenants or set())
    if not live_allowed <= set(credentials):
        raise ValueError("live LLM allowlist must contain configured tenants only")
    kb = knowledge or KnowledgeBase()
    judge = judgment_provider or DisabledJudgmentProvider()
    workflow = WorkflowEngine(db_path, store, intent_parser, kb, predictor, judge)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            workflow.close()

    app = FastAPI(title="Sovereign-MaaS local simulator", version="0.1.0", lifespan=lifespan)
    install_observability(app, metrics_token)
    evidence_dir = Path(research_dir) if research_dir else Path(__file__).resolve().parents[1] / "results"

    def tenant(x_tenant_token: str | None = Header(default=None)) -> str:
        if not x_tenant_token:
            raise HTTPException(401, "tenant token required")
        for tenant_id, token in credentials.items():
            if hmac.compare_digest(x_tenant_token, token):
                return tenant_id
        raise HTTPException(401, "invalid tenant token")

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        if not credentials:
            raise HTTPException(503, "no tenant credentials configured")
        return {
            "status": "ready",
            "backend": "SIMULATOR",
            "intent_parser": type(intent_parser).__name__,
            "llm_external_allowed_tenants": str(len(live_allowed)),
            "judgment_provider": type(judge).__name__,
        }

    @app.post("/v1/intents", response_model=ServiceBundle, status_code=201)
    def submit_intent(intent: TypedIntent, tenant_id: str = Depends(tenant)) -> ServiceBundle:
        service = ServiceBundle(tenant_id=tenant_id, intent=intent)
        store.put_service(service)
        return service

    @app.get("/v1/services", response_model=tuple[ServiceBundle, ...])
    def list_services(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        tenant_id: str = Depends(tenant),
    ) -> tuple[ServiceBundle, ...]:
        return store.list_services(tenant_id, limit, offset)

    @app.get("/v1/simulations", response_model=tuple[SimulationRun, ...])
    def list_runs(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        tenant_id: str = Depends(tenant),
    ) -> tuple[SimulationRun, ...]:
        return store.list_runs(tenant_id, limit, offset)

    @app.get("/v1/workflows", response_model=tuple[WorkflowRecord, ...])
    def list_workflows(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        tenant_id: str = Depends(tenant),
    ) -> tuple[WorkflowRecord, ...]:
        return store.list_workflows(tenant_id, limit, offset)

    @app.get("/v1/monitoring")
    def monitoring(tenant_id: str = Depends(tenant)) -> dict[str, object]:
        recent = store.list_runs(tenant_id, 100)
        return {
            "evidence": "SIMULATION_ONLY",
            "recent_run_count": len(recent),
            "window_limit": 100,
            "latest_run_at": recent[0].created_at if recent else None,
            "forecast_coverage": (
                sum(run.forecast is not None for run in recent) / len(recent) if recent else None
            ),
            "simulated_slo_rate": (
                sum(run.verification.slo_met for run in recent) / len(recent) if recent else None
            ),
            "drift_status": "NOT_EVALUATED",
            "drift_reason": "No live labeled feature/outcome stream or approved drift baseline",
        }

    @app.get("/v1/research/summary")
    def research_summary(tenant_id: str = Depends(tenant)) -> dict[str, object]:
        summaries: dict[str, object] = {}
        for phase in ("phase2-v1", "phase4-v1"):
            path = evidence_dir / phase / "metrics.json"
            if path.is_file():
                summaries[phase] = json.loads(path.read_text(encoding="utf-8"))
        if not summaries:
            raise HTTPException(503, "research artifacts not mounted")
        return {"source": "local checked research artifacts", "summaries": summaries}

    def configured_model() -> dict[str, object] | None:
        if predictor is None or not hasattr(predictor, "manifest"):
            return None
        manifest = predictor.manifest
        digest = manifest["model_sha256"]
        return {
            "model_sha256": digest,
            "model_version": digest[:12],
            "artifact_validated_at_startup": True,
            "runtime": "CONFIGURED_BY_ENVIRONMENT",
            **store.model_stage(digest),
        }

    @app.get("/v1/models")
    def models(tenant_id: str = Depends(tenant)) -> dict[str, object]:
        model = configured_model()
        return {"models": [model] if model else [], "drift_status": "NOT_EVALUATED"}

    @app.post("/v1/models/{model_version}/promote-shadow")
    def promote_shadow(
        model_version: str,
        tenant_id: str = Depends(tenant),
        x_approver_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        expected = approvers.get(tenant_id)
        if (
            expected is None
            or x_approver_token is None
            or not hmac.compare_digest(expected, x_approver_token)
        ):
            raise HTTPException(403, "separate approver credential required")
        model = configured_model()
        if model is None or model_version != model["model_version"]:
            raise HTTPException(404, "configured model not found")
        store.approve_shadow(str(model["model_sha256"]), datetime.now(UTC).isoformat(), "separate-approver")
        return configured_model() or {}

    @app.post("/v1/intents/parse", response_model=ParsedIntent)
    def parse_intent(request: NaturalIntentRequest, tenant_id: str = Depends(tenant)) -> ParsedIntent:
        if isinstance(intent_parser, OpenAIIntentParser) and tenant_id not in live_allowed:
            raise HTTPException(403, "tenant not authorized for external LLM")
        try:
            intent = intent_parser.parse(request.text)
        except ProviderUnavailable as error:
            raise HTTPException(503, str(error)) from error
        except IntentParseError as error:
            raise HTTPException(422, str(error)) from error
        return ParsedIntent(intent=intent, parser=type(intent_parser).__name__)

    @app.get("/v1/knowledge/search", response_model=tuple[KnowledgeHit, ...])
    def search_knowledge(
        q: str = Query(min_length=1, max_length=1000), tenant_id: str = Depends(tenant)
    ) -> tuple[KnowledgeHit, ...]:
        return kb.retrieve(tenant_id, q)

    @app.post("/v1/workflows", response_model=WorkflowRecord, status_code=201)
    def start_workflow(
        request: WorkflowRequest,
        tenant_id: str = Depends(tenant),
        idempotency_key: str | None = Header(default=None),
    ) -> WorkflowRecord:
        if isinstance(intent_parser, OpenAIIntentParser) and tenant_id not in live_allowed:
            raise HTTPException(403, "tenant not authorized for external LLM")
        if not idempotency_key or not idempotency_key.strip() or len(idempotency_key) > 128:
            raise HTTPException(400, "Idempotency-Key header required (1-128 characters)")
        try:
            record = workflow.start(tenant_id, request, idempotency_key)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "idempotency key conflict") from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if record.status == "FAILED":
            status = 503 if record.reason == "LLM provider unavailable" else 422
            raise HTTPException(status, {"workflow_id": record.id, "reason": record.reason})
        return record

    @app.get("/v1/workflows/{workflow_id}", response_model=WorkflowRecord)
    def get_workflow(workflow_id: str, tenant_id: str = Depends(tenant)) -> WorkflowRecord:
        record = store.get_workflow(tenant_id, workflow_id)
        if record is None:
            raise HTTPException(404, "workflow not found")
        return record

    @app.post("/v1/workflows/{workflow_id}/approve", response_model=WorkflowRecord)
    def approve_workflow(
        workflow_id: str,
        request: ApprovalRequest,
        tenant_id: str = Depends(tenant),
        x_approver_token: str | None = Header(default=None),
    ) -> WorkflowRecord:
        expected = approvers.get(tenant_id)
        if (
            expected is None
            or x_approver_token is None
            or not hmac.compare_digest(expected, x_approver_token)
        ):
            raise HTTPException(403, "separate approver credential required")
        record = store.get_workflow(tenant_id, workflow_id)
        if record is None:
            raise HTTPException(404, "workflow not found")
        try:
            return workflow.resume(record, request.approved)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/v1/services/{service_id}", response_model=ServiceBundle)
    def get_service(service_id: str, tenant_id: str = Depends(tenant)) -> ServiceBundle:
        service = store.get_service(tenant_id, service_id)
        if service is None:
            raise HTTPException(404, "service not found")
        return service

    @app.post("/v1/simulations/run", response_model=SimulationRun, status_code=201)
    def run_simulation(
        request: RunRequest,
        tenant_id: str = Depends(tenant),
        idempotency_key: str | None = Header(default=None),
    ) -> SimulationRun:
        if not idempotency_key or not idempotency_key.strip() or len(idempotency_key) > 128:
            raise HTTPException(400, "Idempotency-Key header required (1-128 characters)")
        fingerprint = sha256(request.model_dump_json().encode()).hexdigest()
        previous = store.get_by_key(tenant_id, idempotency_key)
        if previous is not None:
            if previous[0] != fingerprint:
                raise HTTPException(409, "idempotency key reused with different request")
            return previous[1]
        service = store.get_service(tenant_id, request.service_id)
        if service is None:
            raise HTTPException(404, "service not found")
        snapshot = make_snapshot(request.seed)
        candidates = propose(service, snapshot)
        forecast = None
        if predictor is not None:
            try:
                forecast = predictor.predict(service, snapshot, candidates)
            except (ValueError, RuntimeError, OSError):
                forecast = None
        decision = decide(
            service, snapshot, candidates, forecast=forecast, require_forecast=predictor is not None
        )
        advisory = judge.judge(service, snapshot, candidates)
        selected = next(
            candidate for candidate in candidates if candidate.id == decision.selected_candidate_id
        )
        verification = execute(service, snapshot, selected)
        result = SimulationRun(
            tenant_id=tenant_id,
            service_id=service.id,
            seed=request.seed,
            snapshot=snapshot,
            candidates=candidates,
            decision=decision,
            verification=verification,
            forecast=forecast,
            judgment=advisory,
        )
        try:
            store.put_run(result, idempotency_key, fingerprint)
        except sqlite3.IntegrityError:
            previous = store.get_by_key(tenant_id, idempotency_key)
            if previous is None or previous[0] != fingerprint:
                raise HTTPException(409, "idempotency key conflict") from None
            return previous[1]
        return result

    @app.get("/v1/simulations/{run_id}", response_model=SimulationRun)
    def get_run(run_id: str, tenant_id: str = Depends(tenant)) -> SimulationRun:
        result = store.get_run(tenant_id, run_id)
        if result is None:
            raise HTTPException(404, "simulation not found")
        return result

    @app.post("/v1/predictions/evaluate", response_model=ForecastBundle)
    def predict(request: RunRequest, tenant_id: str = Depends(tenant)) -> ForecastBundle:
        if predictor is None:
            raise HTTPException(503, "trained predictor not configured")
        service = store.get_service(tenant_id, request.service_id)
        if service is None:
            raise HTTPException(404, "service not found")
        snapshot = make_snapshot(request.seed)
        candidates = propose(service, snapshot)
        try:
            return predictor.predict(service, snapshot, candidates)
        except (ValueError, RuntimeError, OSError) as error:
            raise HTTPException(503, "trained predictor unavailable") from error

    @app.post("/v1/judgments/evaluate", response_model=JudgmentRecord)
    def evaluate_judgment(request: RunRequest, tenant_id: str = Depends(tenant)) -> JudgmentRecord:
        service = store.get_service(tenant_id, request.service_id)
        if service is None:
            raise HTTPException(404, "service not found")
        snapshot = make_snapshot(request.seed)
        return judge.judge(service, snapshot, propose(service, snapshot))

    return app


def from_environment() -> FastAPI:
    raw = os.getenv("SOVEREIGN_TENANT_TOKENS", "{}")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        raise ValueError("SOVEREIGN_TENANT_TOKENS must be a JSON object of tenant IDs to tokens")
    model_dir = os.getenv("SOVEREIGN_MODEL_DIR")
    predictor = None
    if model_dir:
        from .research_models import TrainedForecastProvider

        predictor = TrainedForecastProvider(Path(model_dir))
    raw_approvers = json.loads(os.getenv("SOVEREIGN_APPROVER_TOKENS", "{}"))
    if not isinstance(raw_approvers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in raw_approvers.items()
    ):
        raise ValueError("SOVEREIGN_APPROVER_TOKENS must be a JSON object")
    mode = os.getenv("SOVEREIGN_LLM_MODE", "offline")
    if mode not in ("offline", "openai"):
        raise ValueError("SOVEREIGN_LLM_MODE must be offline or openai")
    key = os.getenv("OPENAI_API_KEY", "")
    llm_model = os.getenv("SOVEREIGN_LLM_MODEL", "")
    live_allowed = {
        item.strip() for item in os.getenv("SOVEREIGN_LLM_ALLOWED_TENANTS", "").split(",") if item.strip()
    }
    parser: IntentParser = (
        OpenAIIntentParser(key, llm_model)
        if mode == "openai" and key and llm_model
        else OfflineIntentParser()
    )
    jev_mode = os.getenv("SOVEREIGN_JEV_MODE", "disabled")
    if jev_mode not in ("disabled", "fixture", "live"):
        raise ValueError("SOVEREIGN_JEV_MODE must be disabled, fixture or live")
    jev_key = os.getenv("TYPESAFE_API_KEY", "")
    jev_model = os.getenv("SOVEREIGN_JEV_MODEL", "")
    jev_allowed = {
        item.strip() for item in os.getenv("SOVEREIGN_JEV_ALLOWED_TENANTS", "").split(",") if item.strip()
    }
    if not jev_allowed <= set(parsed):
        raise ValueError("Jev allowlist must contain configured tenants only")
    judge: JudgmentProvider = (
        TypeSafeJevProvider(jev_key, jev_model, jev_allowed)
        if jev_mode == "live" and jev_key and jev_model and jev_allowed
        else FixtureJudgmentProvider()
        if jev_mode == "fixture"
        else DisabledJudgmentProvider()
    )
    return create_app(
        os.getenv("SOVEREIGN_DB_PATH", "sovereign_maas.sqlite3"),
        parsed,
        predictor,
        raw_approvers,
        parser,
        live_llm_tenants=live_allowed,
        judgment_provider=judge,
        metrics_token=os.getenv("SOVEREIGN_METRICS_TOKEN") or None,
        research_dir=os.getenv("SOVEREIGN_RESEARCH_DIR") or None,
    )


app = from_environment()
