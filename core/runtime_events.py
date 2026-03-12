"""Runtime event helpers backed by the existing Event ledger."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core import models


def _run_context(db: Session, run_id) -> Dict[str, Any]:
    if not run_id:
        return {}
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if run is None:
        return {}
    prompt_payload = run.prompt_payload if isinstance(run.prompt_payload, dict) else {}
    target = prompt_payload.get("target") if isinstance(prompt_payload.get("target"), dict) else {}
    context = prompt_payload.get("context") if isinstance(prompt_payload.get("context"), dict) else {}
    return {
        "run_id": str(run.id),
        "work_item_id": run.work_item_id,
        "worker_type": run.worker_type,
        "status": run.status.value if getattr(run, "status", None) is not None else None,
        "workspace_id": target.get("workspace_id"),
        "thread_id": context.get("metadata", {}).get("thread_id") if isinstance(context.get("metadata"), dict) else context.get("thread_id"),
        "artifact_id": target.get("artifact_id"),
        "repo": target.get("repo"),
        "branch": target.get("branch"),
        "epic_id": context.get("epic_id"),
    }


def publish_runtime_event(
    db: Session,
    *,
    event_name: str,
    run_id,
    step_id=None,
    actor: str = "runtime",
    correlation_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> models.Event:
    event_data = _run_context(db, run_id)
    if data:
        event_data.update(data)
    event = models.Event(
        id=uuid.uuid4(),
        event_name=event_name,
        occurred_at=datetime.utcnow(),
        env_id="local-dev",
        actor=actor,
        correlation_id=correlation_id,
        run_id=run_id,
        step_id=step_id,
        data=event_data,
    )
    db.add(event)
    db.flush()
    return event
