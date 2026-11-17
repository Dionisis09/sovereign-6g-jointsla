"""Bounded checkpointed simulator workflow with a separate approval interrupt."""

import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .decision import decide, propose
from .domain import ActionKind, ServiceBundle, SimulationRun, WorkflowRecord, WorkflowRequest
from .forecast import ForecastProvider
from .genai import IntentParseError, IntentParser
from .judgment import DisabledJudgmentProvider, JudgmentProvider
from .knowledge import KnowledgeBase
from .simulation import execute, make_snapshot
from .store import Store


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    tenant_id: str
    text: str
    seed: int
    parser: str
    intent: dict[str, Any]
    service: dict[str, Any]
    snapshot: dict[str, Any]
    candidates: list[dict[str, Any]]
    decision: dict[str, Any]
    forecast: dict[str, Any]
    judgment: dict[str, Any]
    citations: list[str]
    approved: bool
    status: str
    reason: str
    run_id: str


class WorkflowEngine:
    def __init__(
        self,
        db_path: str | Path,
        store: Store,
        parser: IntentParser,
        knowledge: KnowledgeBase,
        predictor: ForecastProvider | None = None,
        judgment_provider: JudgmentProvider | None = None,
    ):
        self.store = store
        self.parser = parser
        self.knowledge = knowledge
        self.predictor = predictor
        self.judgment_provider = judgment_provider or DisabledJudgmentProvider()
        path = str(db_path) + ".checkpoints.sqlite3"
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.checkpointer = SqliteSaver(self.connection)
        builder = StateGraph(WorkflowState)
        builder.add_node("parse", self._parse)
        builder.add_node("plan", self._plan)
        builder.add_node("approval", self._approval)
        builder.add_node("execute", self._execute)
        builder.add_edge(START, "parse")
        builder.add_edge("parse", "plan")
        builder.add_conditional_edges(
            "plan", self._route_plan, {"approval": "approval", "execute": "execute"}
        )
        builder.add_conditional_edges("approval", self._route_approval, {"execute": "execute", "end": END})
        builder.add_edge("execute", END)
        self.graph = builder.compile(checkpointer=self.checkpointer)

    def close(self) -> None:
        self.connection.close()

    def _parse(self, state: WorkflowState) -> dict[str, Any]:
        intent = self.parser.parse(state["text"])
        return {"intent": intent.model_dump(mode="json")}

    def _plan(self, state: WorkflowState) -> dict[str, Any]:
        from .domain import TypedIntent

        intent = TypedIntent.model_validate(state["intent"])
        service = ServiceBundle(id=state["workflow_id"], tenant_id=state["tenant_id"], intent=intent)
        snapshot = make_snapshot(state["seed"])
        candidates = propose(service, snapshot)
        forecast = None
        if self.predictor is not None:
            try:
                forecast = self.predictor.predict(service, snapshot, candidates)
            except (ValueError, RuntimeError, OSError):
                forecast = None
        decision = decide(
            service, snapshot, candidates, forecast=forecast, require_forecast=self.predictor is not None
        )
        judgment = self.judgment_provider.judge(service, snapshot, candidates)
        hits = self.knowledge.retrieve(state["tenant_id"], "simulated vision scale approval policy")
        return {
            "service": service.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "decision": decision.model_dump(mode="json"),
            "forecast": forecast.model_dump(mode="json") if forecast is not None else {},
            "judgment": judgment.model_dump(mode="json"),
            "citations": [f"{hit.source_id}@{hit.source_version}" for hit in hits],
        }

    @staticmethod
    def _route_plan(state: WorkflowState) -> str:
        return "execute" if state["decision"]["selected_candidate_id"] == "baseline-noop" else "approval"

    @staticmethod
    def _approval(state: WorkflowState) -> dict[str, Any]:
        answer = interrupt(
            {
                "workflow_id": state["workflow_id"],
                "selected_candidate_id": state["decision"]["selected_candidate_id"],
                "message": "Separate human approval required for simulator action",
            }
        )
        if not isinstance(answer, dict) or type(answer.get("approved")) is not bool:
            return {"approved": False, "status": "REJECTED", "reason": "INVALID_APPROVAL"}
        return {
            "approved": answer["approved"],
            "status": "PENDING" if answer["approved"] else "REJECTED",
            "reason": "HUMAN_DENIED" if not answer["approved"] else "",
        }

    @staticmethod
    def _route_approval(state: WorkflowState) -> str:
        return "execute" if state.get("approved") else "end"

    def _execute(self, state: WorkflowState) -> dict[str, Any]:
        from .domain import CandidateAction, DecisionRecord, ForecastBundle, JudgmentRecord, TelemetrySnapshot

        service = ServiceBundle.model_validate(state["service"])
        snapshot = TelemetrySnapshot.model_validate(state["snapshot"])
        candidates = tuple(CandidateAction.model_validate(item) for item in state["candidates"])
        original = DecisionRecord.model_validate(state["decision"])
        forecast = ForecastBundle.model_validate(state["forecast"]) if state.get("forecast") else None
        judgment = JudgmentRecord.model_validate(state["judgment"]) if state.get("judgment") else None
        fresh = decide(
            service, snapshot, candidates, forecast=forecast, require_forecast=self.predictor is not None
        )
        if fresh.selected_candidate_id != original.selected_candidate_id:
            return {"status": "REJECTED", "reason": "POLICY_CHANGED_OR_STALE_TELEMETRY"}
        selected = next(item for item in candidates if item.id == original.selected_candidate_id)
        if selected.kind != ActionKind.NOOP and not state.get("approved"):
            return {"status": "REJECTED", "reason": "APPROVAL_REQUIRED"}
        previous = self.store.get_run(state["tenant_id"], state["workflow_id"])
        if previous is not None:
            return {"status": "VERIFIED", "run_id": previous.id}
        if self.store.get_service(state["tenant_id"], service.id) is None:
            self.store.put_service(service)
        run = SimulationRun(
            id=state["workflow_id"],
            tenant_id=state["tenant_id"],
            service_id=service.id,
            seed=state["seed"],
            snapshot=snapshot,
            candidates=candidates,
            decision=original,
            verification=execute(service, snapshot, selected),
            forecast=forecast,
            judgment=judgment,
        )
        try:
            self.store.put_run(
                run, f"workflow:{state['workflow_id']}", sha256(state["text"].encode()).hexdigest()
            )
        except sqlite3.IntegrityError:
            prior = self.store.get_run(state["tenant_id"], state["workflow_id"])
            if prior is None:
                raise
        return {"status": "VERIFIED", "run_id": run.id}

    @staticmethod
    def _record(state: WorkflowState, status: str) -> WorkflowRecord:
        from .domain import DecisionRecord, JudgmentRecord, TypedIntent

        return WorkflowRecord(
            id=state["workflow_id"],
            tenant_id=state["tenant_id"],
            status=status,
            parser=state["parser"],
            intent=TypedIntent.model_validate(state["intent"]) if "intent" in state else None,
            service_id=state["workflow_id"] if "service" in state else None,
            selected_candidate_id=state.get("decision", {}).get("selected_candidate_id"),
            decision=DecisionRecord.model_validate(state["decision"]) if "decision" in state else None,
            run_id=state.get("run_id"),
            citations=tuple(state.get("citations", [])),
            reason=state.get("reason"),
            judgment=JudgmentRecord.model_validate(state["judgment"]) if "judgment" in state else None,
        )

    def start(self, tenant_id: str, request: WorkflowRequest, key: str) -> WorkflowRecord:
        fingerprint = sha256(request.model_dump_json().encode()).hexdigest()
        previous = self.store.get_workflow_by_key(tenant_id, key)
        if previous is not None:
            if previous[0] != fingerprint:
                raise ValueError("idempotency key reused with different request")
            return previous[1]
        workflow_id = str(uuid4())
        initial: WorkflowState = {
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
            "text": request.text,
            "seed": request.seed,
            "parser": type(self.parser).__name__,
        }
        pending = self._record(initial, "PENDING")
        self.store.put_workflow(pending, key, fingerprint)
        try:
            result = self.graph.invoke(initial, {"configurable": {"thread_id": workflow_id}})
            state = cast(
                WorkflowState, self.graph.get_state({"configurable": {"thread_id": workflow_id}}).values
            )
            status = "NEEDS_APPROVAL" if "__interrupt__" in result else state["status"]
            record = self._record(state, status)
        except (IntentParseError, ValueError) as error:
            record = pending.model_copy(update={"status": "FAILED", "reason": str(error)})
        self.store.update_workflow(record, "PENDING")
        return record

    def resume(self, record: WorkflowRecord, approved: bool) -> WorkflowRecord:
        if record.status != "NEEDS_APPROVAL":
            raise ValueError("workflow is not awaiting approval")
        locked = record.model_copy(update={"status": "PENDING"})
        if not self.store.update_workflow(locked, "NEEDS_APPROVAL"):
            raise ValueError("approval already processed")
        try:
            result = self.graph.invoke(
                Command(resume={"approved": approved}), {"configurable": {"thread_id": record.id}}
            )
            if "__interrupt__" in result:
                raise RuntimeError("unexpected repeated approval interrupt")
            state = cast(
                WorkflowState, self.graph.get_state({"configurable": {"thread_id": record.id}}).values
            )
            updated = self._record(state, state["status"])
        except Exception:
            failed = locked.model_copy(update={"status": "FAILED", "reason": "WORKFLOW_EXECUTION_FAILED"})
            self.store.update_workflow(failed, "PENDING")
            raise
        self.store.update_workflow(updated, "PENDING")
        return updated
