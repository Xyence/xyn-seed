"""Event API endpoints"""
import asyncio
import json
import uuid
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core import models, schemas

router = APIRouter()


def _event_matches_workspace(event: models.Event, workspace_id: Optional[str]) -> bool:
    if not workspace_id:
        return True
    data = event.data if isinstance(event.data, dict) else {}
    return str(data.get("workspace_id") or "").strip() == str(workspace_id).strip()


def _event_matches_runtime_only(event: models.Event, runtime_only: bool) -> bool:
    if not runtime_only:
        return True
    return str(event.event_name or "").startswith("run.")


def _query_events(
    db: Session,
    *,
    limit: int,
    cursor: Optional[str] = None,
    event_name: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[str] = None,
    runtime_only: bool = False,
):
    query = db.query(models.Event)
    if event_name:
        query = query.filter(models.Event.event_name == event_name)
    if run_id:
        query = query.filter(models.Event.run_id == run_id)
    query = query.order_by(models.Event.occurred_at.desc(), models.Event.id.desc())
    if cursor:
        try:
            cursor_id = uuid.UUID(cursor)
            cursor_event = db.query(models.Event).filter(models.Event.id == cursor_id).first()
            if cursor_event:
                query = query.filter(
                    (models.Event.occurred_at < cursor_event.occurred_at) |
                    ((models.Event.occurred_at == cursor_event.occurred_at) & (models.Event.id < cursor_id))
                )
        except ValueError:
            pass
    candidate_events = query.limit(max(limit * 4, limit + 1)).all()
    events = [
        event
        for event in candidate_events
        if _event_matches_workspace(event, workspace_id) and _event_matches_runtime_only(event, runtime_only)
    ]
    next_cursor = None
    if len(events) > limit:
        next_cursor = str(events[limit - 1].id)
        events = events[:limit]
    return events, next_cursor


def _query_stream_events(
    db: Session,
    *,
    after_event_id: Optional[str] = None,
    since: Optional[datetime] = None,
    event_name: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[str] = None,
    runtime_only: bool = False,
    limit: int = 100,
):
    query = db.query(models.Event)
    if event_name:
        query = query.filter(models.Event.event_name == event_name)
    if run_id:
        query = query.filter(models.Event.run_id == run_id)
    if since:
        query = query.filter(models.Event.occurred_at >= since)
    if after_event_id:
        try:
            after_uuid = uuid.UUID(after_event_id)
            anchor = db.query(models.Event).filter(models.Event.id == after_uuid).first()
            if anchor:
                query = query.filter(
                    (models.Event.occurred_at > anchor.occurred_at) |
                    ((models.Event.occurred_at == anchor.occurred_at) & (models.Event.id > after_uuid))
                )
        except ValueError:
            pass
    query = query.order_by(models.Event.occurred_at.asc(), models.Event.id.asc())
    candidate_events = query.limit(max(limit * 4, limit)).all()
    return [
        event
        for event in candidate_events
        if _event_matches_workspace(event, workspace_id) and _event_matches_runtime_only(event, runtime_only)
    ][:limit]


def _serialize_sse_event(*, event_id: str, event_type: str, payload: dict) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.get("/events", response_model=schemas.EventListResponse)
async def list_events(
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    event_name: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[str] = None,
    runtime_only: bool = False,
    db: Session = Depends(get_db)
):
    """List events with optional filtering and pagination.

    Args:
        limit: Maximum number of events to return (1-500)
        cursor: Pagination cursor (event ID to start after)
        event_name: Filter by event name
        run_id: Filter by run ID
        db: Database session

    Returns:
        List of events with optional next cursor
    """
    events, next_cursor = _query_events(
        db,
        limit=limit,
        cursor=cursor,
        event_name=event_name,
        run_id=run_id,
        workspace_id=workspace_id,
        runtime_only=runtime_only,
    )
    items = [schemas.Event.from_orm_model(e) for e in events]

    return schemas.EventListResponse(items=items, next_cursor=next_cursor)


@router.get("/events/stream")
async def stream_events(
    request: Request,
    event_name: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[str] = None,
    runtime_only: bool = False,
    since: Optional[datetime] = None,
    last_event_id: Optional[str] = Query(None, alias="last_event_id"),
    once: bool = False,
    poll_interval_seconds: float = Query(1.0, ge=0.25, le=10.0),
    db: Session = Depends(get_db),
):
    """Stream events from the Event ledger using SSE."""

    async def event_iterator():
        latest_event_id = last_event_id
        while True:
            if await request.is_disconnected():
                break
            db.expire_all()
            events = _query_stream_events(
                db,
                after_event_id=latest_event_id,
                since=since,
                event_name=event_name,
                run_id=run_id,
                workspace_id=workspace_id,
                runtime_only=runtime_only,
            )
            if not events:
                yield ": keepalive\n\n"
                await asyncio.sleep(poll_interval_seconds)
                continue
            for event in events:
                latest_event_id = str(event.id)
                payload = schemas.Event.from_orm_model(event).model_dump(mode="json", by_alias=True)
                yield _serialize_sse_event(event_id=str(event.id), event_type=event.event_name, payload=payload)
            if once:
                break
            await asyncio.sleep(0)

    return StreamingResponse(
        event_iterator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/{event_id}", response_model=schemas.Event)
async def get_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get a specific event by ID.

    Args:
        event_id: Event UUID
        db: Database session

    Returns:
        Event details
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()

    if not event:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")

    return schemas.Event.from_orm_model(event)


@router.post("/events", response_model=schemas.Event, status_code=201)
async def emit_event(
    event_request: schemas.EmitEventRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Emit a new event.

    Args:
        event_request: Event creation request
        request: FastAPI request (for correlation ID)
        db: Database session

    Returns:
        Created event
    """
    env_id = os.getenv("ENV_ID", "local-dev")

    # Get correlation ID from request state (set by middleware)
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))

    # Create event
    event = models.Event(
        event_name=event_request.event_name,
        occurred_at=datetime.utcnow(),
        env_id=env_id,
        actor="system",  # v0: no auth, default to system
        correlation_id=correlation_id,
        run_id=event_request.run_id,
        step_id=event_request.step_id,
        resource_type=event_request.resource.type if event_request.resource else None,
        resource_id=event_request.resource.id if event_request.resource else None,
        data=event_request.data
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return schemas.Event.from_orm_model(event)
