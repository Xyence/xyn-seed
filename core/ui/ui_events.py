"""UI routes for event console"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.database import get_db
from core import models

router = APIRouter()
templates = Jinja2Templates(directory="core/templates")


@router.get("/events", response_class=HTMLResponse)
async def events_page(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    event_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Event console page."""
    query = db.query(models.Event)

    if event_name:
        query = query.filter(models.Event.event_name == event_name)

    query = query.order_by(models.Event.occurred_at.desc())
    events = query.limit(limit).all()

    # Get unique event names for filter
    event_names = db.query(models.Event.event_name).distinct().all()
    event_names = sorted([name[0] for name in event_names])

    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "events": events,
            "event_names": event_names,
            "selected_event_name": event_name
        }
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def event_detail_page(
    request: Request,
    event_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Event detail page."""
    event = db.query(models.Event).filter(models.Event.id == event_id).first()

    if not event:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")

    return templates.TemplateResponse(
        "event_detail.html",
        {
            "request": request,
            "event": event
        }
    )


@router.get("/events/_list", response_class=HTMLResponse)
async def events_list_partial(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    event_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """HTMX partial for event list."""
    query = db.query(models.Event)

    if event_name:
        query = query.filter(models.Event.event_name == event_name)

    query = query.order_by(models.Event.occurred_at.desc())
    events = query.limit(limit).all()

    return templates.TemplateResponse(
        "partials/event_list.html",
        {
            "request": request,
            "events": events
        }
    )
