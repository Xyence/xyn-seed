"""UI routes for runs"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.database import get_db
from core import models
from core.executor import SimpleExecutor

router = APIRouter()
templates = Jinja2Templates(directory="core/templates")


@router.get("/runs", response_class=HTMLResponse)
async def runs_page(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Runs list page."""
    query = db.query(models.Run)

    if status:
        try:
            status_enum = models.RunStatus(status)
            query = query.filter(models.Run.status == status_enum)
        except ValueError:
            pass

    query = query.order_by(models.Run.created_at.desc())
    runs = query.limit(limit).all()

    return templates.TemplateResponse(
        "runs.html",
        {
            "request": request,
            "runs": runs,
            "selected_status": status
        }
    )


@router.get("/runs/new", response_class=HTMLResponse)
async def new_run_page(request: Request):
    """New run launcher page."""
    return templates.TemplateResponse(
        "run_new.html",
        {
            "request": request
        }
    )


@router.post("/runs")
async def create_run_ui(
    request: Request,
    name: str = Form(...),
    blueprint_ref: Optional[str] = Form(""),
    inputs: Optional[str] = Form("{}"),
    simulate_failure: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Create a new run from UI form."""
    import json

    # Parse inputs JSON
    try:
        inputs_dict = json.loads(inputs) if inputs else {}
    except json.JSONDecodeError:
        inputs_dict = {"raw_input": inputs}

    # Get correlation ID from request state
    correlation_id = getattr(request.state, "correlation_id", None)

    executor = SimpleExecutor(db)

    # Execute a simple demo run
    # Note: blueprint_ref is accepted but not used in v0 (just stored for future)
    run = await executor.execute_simple_run(
        name=name,
        inputs=inputs_dict,
        simulate_failure=simulate_failure,
        correlation_id=correlation_id
    )

    # Redirect to run detail page
    return RedirectResponse(url=f"/ui/runs/{run.id}", status_code=303)


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail_page(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Run detail page."""
    run = db.query(models.Run).filter(models.Run.id == run_id).first()

    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Run not found")

    # Get steps for this run
    steps = db.query(models.Step).filter(
        models.Step.run_id == run_id
    ).order_by(models.Step.idx).all()

    # Get artifacts for this run
    artifacts = db.query(models.Artifact).filter(
        models.Artifact.run_id == run_id
    ).all()

    # Get events for this run
    events = db.query(models.Event).filter(
        models.Event.run_id == run_id
    ).order_by(models.Event.occurred_at.desc()).all()

    return templates.TemplateResponse(
        "run_detail.html",
        {
            "request": request,
            "run": run,
            "steps": steps,
            "artifacts": artifacts,
            "events": events
        }
    )


@router.get("/runs/_list", response_class=HTMLResponse)
async def runs_list_partial(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """HTMX partial for runs list."""
    query = db.query(models.Run)

    if status:
        try:
            status_enum = models.RunStatus(status)
            query = query.filter(models.Run.status == status_enum)
        except ValueError:
            pass

    query = query.order_by(models.Run.created_at.desc())
    runs = query.limit(limit).all()

    return templates.TemplateResponse(
        "partials/run_list.html",
        {
            "request": request,
            "runs": runs
        }
    )


@router.get("/runs/{run_id}/_status", response_class=HTMLResponse)
async def run_status_partial(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """HTMX partial for run status."""
    run = db.query(models.Run).filter(models.Run.id == run_id).first()

    if not run:
        return ""

    return templates.TemplateResponse(
        "partials/run_status.html",
        {
            "request": request,
            "run": run
        }
    )
