"""Event API endpoints"""
import uuid
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core import models, schemas

router = APIRouter()


@router.get("/events", response_model=schemas.EventListResponse)
async def list_events(
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    event_name: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
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
    query = db.query(models.Event)

    # Apply filters
    if event_name:
        query = query.filter(models.Event.event_name == event_name)
    if run_id:
        query = query.filter(models.Event.run_id == run_id)

    # Order by occurred_at descending, then id descending for stable ordering
    query = query.order_by(models.Event.occurred_at.desc(), models.Event.id.desc())

    # Apply cursor pagination
    if cursor:
        try:
            cursor_id = uuid.UUID(cursor)
            # Find the cursor event to get its occurred_at
            cursor_event = db.query(models.Event).filter(models.Event.id == cursor_id).first()
            if cursor_event:
                # Filter to events that occurred before the cursor, or same timestamp with lower ID
                query = query.filter(
                    (models.Event.occurred_at < cursor_event.occurred_at) |
                    ((models.Event.occurred_at == cursor_event.occurred_at) & (models.Event.id < cursor_id))
                )
        except ValueError:
            pass  # Invalid cursor, ignore

    # Fetch limit + 1 to determine if there are more results
    events = query.limit(limit + 1).all()

    # Determine next cursor
    next_cursor = None
    if len(events) > limit:
        next_cursor = str(events[limit - 1].id)
        events = events[:limit]

    # Convert to schema
    items = [schemas.Event.from_orm_model(e) for e in events]

    return schemas.EventListResponse(items=items, next_cursor=next_cursor)


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
