"""Runtime worker registration and driver registry."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from core import models
from core.codex_executor import check_codex_availability
from core.runtime_contract import (
    CODEX_LOCAL_CAPABILITIES,
    RunPayloadV1,
    RuntimeWorkerDriver,
    WorkerAcceptedRun,
    WorkerArtifactDescriptor,
    WorkerInfoPayload,
    WorkerRunSnapshot,
)


DEFAULT_HEALTH_WINDOW_SECONDS = 90


class CodexLocalWorkerDriver:
    worker_type = "codex_local"
    capabilities = CODEX_LOCAL_CAPABILITIES

    def can_accept(self, run_payload: RunPayloadV1) -> bool:
        return run_payload.worker_type == self.worker_type and check_codex_availability().available

    def start_run(self, run_payload: RunPayloadV1) -> WorkerAcceptedRun:
        return WorkerAcceptedRun(
            accepted=True,
            worker_id=f"{self.worker_type}-dispatcher",
            run_id=run_payload.run_id,
            message="queued for codex_local execution",
        )

    def cancel_run(self, run_id: str) -> None:
        return None

    def poll_run(self, run_id: str) -> WorkerRunSnapshot:
        from core.database import SessionLocal
        from core.runtime_execution import snapshot_run

        db = SessionLocal()
        try:
            return snapshot_run(db, uuid.UUID(run_id))
        finally:
            db.close()

    def collect_artifacts(self, run_id: str) -> List[WorkerArtifactDescriptor]:
        from core.database import SessionLocal
        from core.runtime_execution import collect_run_artifact_descriptors

        db = SessionLocal()
        try:
            return collect_run_artifact_descriptors(db, uuid.UUID(run_id))
        finally:
            db.close()

    def execute_assigned_run(self, db: Session, run_id, worker_id: str, **kwargs):
        from core.codex_local_worker import execute_codex_local_run

        return execute_codex_local_run(db, run_id=run_id, worker_id=worker_id, **kwargs)


def register_codex_local_worker(db: Session, *, worker_id: Optional[str] = None) -> models.RuntimeWorker:
    from core.codex_local_worker import register_codex_local_worker as _register

    return _register(db, worker_id=worker_id)


_DRIVERS: Dict[str, RuntimeWorkerDriver] = {
    "codex_local": CodexLocalWorkerDriver(),
}


def get_worker_driver(worker_type: str) -> Optional[RuntimeWorkerDriver]:
    return _DRIVERS.get(str(worker_type or "").strip())


def register_worker(db: Session, worker_info: WorkerInfoPayload) -> models.RuntimeWorker:
    row = db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id == worker_info.worker_id).first()
    if row is None:
        row = models.RuntimeWorker(
            id=uuid.uuid4(),
            worker_id=worker_info.worker_id,
            worker_type=worker_info.worker_type,
            runtime_environment=worker_info.runtime_environment,
        )
        db.add(row)
    row.worker_type = worker_info.worker_type
    row.runtime_environment = worker_info.runtime_environment
    row.status = models.RuntimeWorkerStatus(worker_info.status)
    row.last_heartbeat = worker_info.last_heartbeat
    row.capabilities_json = list(worker_info.capabilities or [])
    db.flush()
    return row


def heartbeat(db: Session, worker_id: str) -> Optional[models.RuntimeWorker]:
    row = db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id == worker_id).first()
    if row is None:
        return None
    row.last_heartbeat = datetime.utcnow()
    if row.status == models.RuntimeWorkerStatus.OFFLINE:
        row.status = models.RuntimeWorkerStatus.IDLE
    db.flush()
    return row


def mark_worker_busy(db: Session, worker_id: str, run_id) -> Optional[models.RuntimeWorker]:
    row = db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id == worker_id).first()
    if row is None:
        return None
    row.status = models.RuntimeWorkerStatus.BUSY
    row.active_run_id = run_id
    row.last_heartbeat = datetime.utcnow()
    db.flush()
    return row


def mark_worker_idle(db: Session, worker_id: str) -> Optional[models.RuntimeWorker]:
    row = db.query(models.RuntimeWorker).filter(models.RuntimeWorker.worker_id == worker_id).first()
    if row is None:
        return None
    if row.worker_type == "codex_local" and not check_codex_availability().available:
        row.status = models.RuntimeWorkerStatus.OFFLINE
    else:
        row.status = models.RuntimeWorkerStatus.IDLE
    row.active_run_id = None
    row.last_heartbeat = datetime.utcnow()
    db.flush()
    return row


def list_healthy_workers(
    db: Session,
    worker_type: str,
    *,
    now: Optional[datetime] = None,
    heartbeat_timeout_seconds: int = DEFAULT_HEALTH_WINDOW_SECONDS,
) -> List[models.RuntimeWorker]:
    current = now or datetime.utcnow()
    threshold = current - timedelta(seconds=heartbeat_timeout_seconds)
    return db.query(models.RuntimeWorker).filter(
        models.RuntimeWorker.worker_type == worker_type,
        models.RuntimeWorker.status != models.RuntimeWorkerStatus.OFFLINE,
        models.RuntimeWorker.last_heartbeat >= threshold,
    ).order_by(models.RuntimeWorker.worker_id.asc()).all()


def worker_health_reason(row: models.RuntimeWorker) -> Optional[str]:
    if row.worker_type == "codex_local":
        availability = check_codex_availability()
        if not availability.available:
            return availability.reason
    return None
