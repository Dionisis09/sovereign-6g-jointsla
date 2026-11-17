"""Small tenant-scoped SQLite repository with a versioned schema."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .domain import ServiceBundle, SimulationRun, WorkflowRecord


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise RuntimeError(f"unsupported Sovereign-MaaS schema version {version}")
            connection.execute("""CREATE TABLE IF NOT EXISTS services (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payload TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
                payload TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key))""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_services_tenant ON services(tenant_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_tenant ON runs(tenant_id)")
            connection.execute("""CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                UNIQUE(tenant_id, idempotency_key))""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_workflows_tenant ON workflows(tenant_id)")
            connection.execute("""CREATE TABLE IF NOT EXISTS model_registry (
                model_sha256 TEXT PRIMARY KEY, stage TEXT NOT NULL,
                approved_at TEXT, approved_by TEXT)""")
            connection.execute("PRAGMA user_version=3")

    def model_stage(self, digest: str) -> dict[str, str | None]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT stage, approved_at, approved_by FROM model_registry WHERE model_sha256=?",
                (digest,),
            ).fetchone()
        return dict(row) if row else {"stage": "CANDIDATE", "approved_at": None, "approved_by": None}

    def approve_shadow(self, digest: str, approved_at: str, approved_by: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO model_registry VALUES (?, 'APPROVED_SHADOW', ?, ?) "
                "ON CONFLICT(model_sha256) DO NOTHING",
                (digest, approved_at, approved_by),
            )

    def put_service(self, service: ServiceBundle) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO services VALUES (?, ?, ?)",
                (service.id, service.tenant_id, service.model_dump_json()),
            )

    def get_service(self, tenant_id: str, service_id: str) -> ServiceBundle | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id)
            ).fetchone()
        return ServiceBundle.model_validate_json(row[0]) if row else None

    def list_services(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[ServiceBundle, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM services WHERE tenant_id=? "
                "ORDER BY json_extract(payload, '$.created_at') DESC, id DESC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset),
            ).fetchall()
        return tuple(ServiceBundle.model_validate_json(row[0]) for row in rows)

    def get_run(self, tenant_id: str, run_id: str) -> SimulationRun | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE tenant_id=? AND id=?", (tenant_id, run_id)
            ).fetchone()
        return SimulationRun.model_validate_json(row[0]) if row else None

    def list_runs(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[SimulationRun, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs WHERE tenant_id=? "
                "ORDER BY json_extract(payload, '$.created_at') DESC, id DESC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset),
            ).fetchall()
        return tuple(SimulationRun.model_validate_json(row[0]) for row in rows)

    def get_by_key(self, tenant_id: str, key: str) -> tuple[str, SimulationRun] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT request_fingerprint, payload FROM runs WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, key),
            ).fetchone()
        return (row[0], SimulationRun.model_validate_json(row[1])) if row else None

    def put_run(self, run: SimulationRun, key: str, fingerprint: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (run.id, run.tenant_id, run.service_id, key, fingerprint, run.model_dump_json()),
            )

    def put_workflow(self, record: WorkflowRecord, key: str, fingerprint: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO workflows VALUES (?, ?, ?, ?, ?)",
                (record.id, record.tenant_id, key, fingerprint, record.model_dump_json()),
            )

    def get_workflow(self, tenant_id: str, workflow_id: str) -> WorkflowRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM workflows WHERE tenant_id=? AND id=?", (tenant_id, workflow_id)
            ).fetchone()
        return WorkflowRecord.model_validate_json(row[0]) if row else None

    def list_workflows(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[WorkflowRecord, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM workflows WHERE tenant_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset),
            ).fetchall()
        return tuple(WorkflowRecord.model_validate_json(row[0]) for row in rows)

    def get_workflow_by_key(self, tenant_id: str, key: str) -> tuple[str, WorkflowRecord] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT request_fingerprint, payload FROM workflows WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, key),
            ).fetchone()
        return (row[0], WorkflowRecord.model_validate_json(row[1])) if row else None

    def update_workflow(self, record: WorkflowRecord, from_status: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE workflows SET payload=? WHERE tenant_id=? AND id=? "
                "AND json_extract(payload, '$.status')=?",
                (record.model_dump_json(), record.tenant_id, record.id, from_status),
            )
            return cursor.rowcount == 1
