"""UI routes for artifacts"""
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


@router.get("/artifacts", response_class=HTMLResponse)
async def artifacts_page(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    run_id: Optional[uuid.UUID] = None,
    kind: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Artifacts browser page."""
    query = db.query(models.Artifact)

    if run_id:
        query = query.filter(models.Artifact.run_id == run_id)
    if kind:
        query = query.filter(models.Artifact.kind == kind)

    query = query.order_by(models.Artifact.created_at.desc())
    artifacts = query.limit(limit).all()

    # Get unique kinds for filter
    kinds = db.query(models.Artifact.kind).distinct().all()
    kinds = sorted([k[0] for k in kinds])

    return templates.TemplateResponse(
        "artifacts.html",
        {
            "request": request,
            "artifacts": artifacts,
            "kinds": kinds,
            "selected_kind": kind,
            "selected_run_id": run_id
        }
    )


@router.get("/artifacts/{artifact_id}", response_class=HTMLResponse)
async def artifact_detail_page(
    request: Request,
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Artifact detail page."""
    artifact = db.query(models.Artifact).filter(
        models.Artifact.id == artifact_id
    ).first()

    if not artifact:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Get associated run if available
    run = None
    if artifact.run_id:
        run = db.query(models.Run).filter(
            models.Run.id == artifact.run_id
        ).first()

    return templates.TemplateResponse(
        "artifact_detail.html",
        {
            "request": request,
            "artifact": artifact,
            "run": run
        }
    )


@router.get("/runs/{run_id}/artifacts", response_class=HTMLResponse)
async def run_artifacts_partial(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """HTMX partial for run artifacts."""
    artifacts = db.query(models.Artifact).filter(
        models.Artifact.run_id == run_id
    ).order_by(models.Artifact.created_at.desc()).all()

    return templates.TemplateResponse(
        "partials/artifact_list.html",
        {
            "request": request,
            "artifacts": artifacts
        }
    )
