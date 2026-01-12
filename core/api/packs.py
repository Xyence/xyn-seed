"""Pack API endpoints"""
import uuid
import os
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from core import models, schemas
from core.exceptions import (
    PackAlreadyInstalledError,
    PackInstallationInProgressError,
    PackInstallationFailedError,
    PackNotFoundError
)

router = APIRouter()


@router.get("/packs", response_model=schemas.PackListResponse)
async def list_packs(
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List available packs with installation status.

    Args:
        limit: Maximum number of packs to return (1-500)
        cursor: Pagination cursor (pack ID to start after)
        db: Database session

    Returns:
        List of packs with installation status
    """
    env_id = os.getenv("ENV_ID", "local-dev")

    # Order by created_at descending, then id descending for stable ordering
    query = db.query(models.Pack).order_by(
        models.Pack.created_at.desc(),
        models.Pack.id.desc()
    )

    # Apply cursor pagination
    if cursor:
        try:
            cursor_id = uuid.UUID(cursor)
            cursor_pack = db.query(models.Pack).filter(models.Pack.id == cursor_id).first()
            if cursor_pack:
                query = query.filter(
                    (models.Pack.created_at < cursor_pack.created_at) |
                    ((models.Pack.created_at == cursor_pack.created_at) & (models.Pack.id < cursor_id))
                )
        except ValueError:
            pass  # Invalid cursor, ignore

    # Fetch limit + 1 to determine if there are more results
    packs = query.limit(limit + 1).all()

    # Determine next cursor
    next_cursor = None
    if len(packs) > limit:
        next_cursor = str(packs[limit - 1].id)
        packs = packs[:limit]

    # Build response with installation status
    items = []
    for pack in packs:
        # Get installation for this pack in current env
        installation = db.query(models.PackInstallation).filter(
            models.PackInstallation.pack_id == pack.id,
            models.PackInstallation.env_id == env_id
        ).first()

        items.append(schemas.PackWithInstallation(
            pack=schemas.Pack.from_orm_model(pack),
            installation=schemas.PackInstallation.from_orm_model(installation) if installation else None
        ))

    return schemas.PackListResponse(items=items, next_cursor=next_cursor)


@router.get("/packs/{pack_ref}", response_model=schemas.Pack)
async def get_pack(
    pack_ref: str,
    db: Session = Depends(get_db)
):
    """Get pack details by reference.

    Args:
        pack_ref: Pack reference (e.g., core.domain@v1)
        db: Database session

    Returns:
        Pack details
    """
    pack = db.query(models.Pack).filter(models.Pack.pack_ref == pack_ref).first()

    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_ref}' not found")

    return schemas.Pack.from_orm_model(pack)


@router.get("/packs/{pack_ref}/status", response_model=schemas.PackStatusResponse)
async def get_pack_status(
    pack_ref: str,
    db: Session = Depends(get_db)
):
    """Get pack installation status.

    Args:
        pack_ref: Pack reference (e.g., core.domain@v1)
        db: Database session

    Returns:
        Pack installation status
    """
    env_id = os.getenv("ENV_ID", "local-dev")

    # Get pack
    pack = db.query(models.Pack).filter(models.Pack.pack_ref == pack_ref).first()
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_ref}' not found")

    # Get installation for current environment
    installation = db.query(models.PackInstallation).filter(
        models.PackInstallation.pack_id == pack.id,
        models.PackInstallation.env_id == env_id
    ).first()

    if not installation:
        # Pack available but not installed
        return schemas.PackStatusResponse(
            pack_ref=pack_ref,
            status="available",
            schema_mode=None,
            schema_name=pack.schema_name,
            installed_version=None,
            migration_provider=None,
            migration_state=None,
            installed_at=None,
            installed_by_run_id=None,
            updated_by_run_id=None,
            error=None,
            last_error_at=None
        )

    return schemas.PackStatusResponse(
        pack_ref=pack_ref,
        status=installation.status.value if hasattr(installation.status, 'value') else installation.status,
        schema_mode=installation.schema_mode,
        schema_name=installation.schema_name,
        installed_version=installation.installed_version,
        migration_provider=installation.migration_provider,
        migration_state=installation.migration_state,
        installed_at=installation.installed_at,
        installed_by_run_id=installation.installed_by_run_id,
        updated_by_run_id=installation.updated_by_run_id,
        error=installation.error,
        last_error_at=installation.last_error_at
    )


@router.post("/packs/{pack_ref}/install", status_code=202)
async def install_pack(
    pack_ref: str,
    request: schemas.PackInstallRequest = schemas.PackInstallRequest(),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Enqueue a pack installation for async execution by worker.

    Args:
        pack_ref: Pack reference (e.g., 'core.domain@v1')
        request: Installation options (run_at, priority, max_attempts)
        background_tasks: FastAPI background tasks (unused, kept for compatibility)
        db: Database session

    Returns:
        202 Accepted with run_id for tracking progress via GET /runs/{run_id}

    Raises:
        404: Pack not found
    """
    from core.blueprints.runner import enqueue_run

    env_id = os.getenv("ENV_ID", "local-dev")

    # Verify pack exists
    pack = db.query(models.Pack).filter(models.Pack.pack_ref == pack_ref).first()
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_ref}' not found")

    # Enqueue installation run with scheduling/priority support
    run = enqueue_run(
        "core.pack.install@v1",
        {
            "pack_ref": pack_ref,
            "env_id": env_id
        },
        db,
        actor="api",
        run_at=request.run_at,
        priority=request.priority,
        max_attempts=request.max_attempts
    )

    message = "Pack installation queued. Poll GET /api/v1/runs/{run_id} for progress."
    if request.run_at:
        message = f"Pack installation scheduled for {request.run_at}. Poll GET /api/v1/runs/{{run_id}} for progress."

    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "pack_ref": pack_ref,
        "priority": run.priority,
        "run_at": run.run_at.isoformat(),
        "correlation_id": run.correlation_id,
        "message": message
    }


@router.post("/packs/{pack_ref}/upgrade", status_code=202)
async def upgrade_pack(
    pack_ref: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Enqueue a pack upgrade for async execution by worker.

    Args:
        pack_ref: Target pack reference (e.g., 'core.domain@v2')
        background_tasks: FastAPI background tasks (unused, kept for compatibility)
        db: Database session

    Returns:
        202 Accepted with run_id for tracking progress via GET /runs/{run_id}
    """
    from core.blueprints.runner import enqueue_run

    env_id = os.getenv("ENV_ID", "local-dev")

    # Verify target pack exists
    pack = db.query(models.Pack).filter(models.Pack.pack_ref == pack_ref).first()
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_ref}' not found")

    # Enqueue upgrade run (returns immediately)
    run = enqueue_run(
        "core.pack.upgrade@v1",
        {
            "pack_ref": pack_ref,
            "env_id": env_id
        },
        db,
        actor="api"
    )

    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "pack_ref": pack_ref,
        "correlation_id": run.correlation_id,
        "message": "Pack upgrade queued. Poll GET /api/v1/runs/{run_id} for progress."
    }
