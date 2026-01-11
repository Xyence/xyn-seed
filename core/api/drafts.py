"""Draft API endpoints (stub for v0)"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core import models, schemas

router = APIRouter()


@router.post("/drafts", response_model=schemas.Draft, status_code=201)
async def create_draft(
    name: str,
    kind: str,
    definition: dict,
    db: Session = Depends(get_db)
):
    """Create a new draft (stub for v0).

    Args:
        name: Draft name
        kind: Draft kind (blueprint, pack)
        definition: Draft definition (YAML/JSON as dict)
        db: Database session

    Returns:
        Created draft
    """
    draft = models.Draft(
        name=name,
        kind=kind,
        definition=definition,
        status=models.DraftStatus.DRAFT
    )

    db.add(draft)
    db.commit()
    db.refresh(draft)

    return schemas.Draft.from_orm_model(draft)


@router.get("/drafts", response_model=list[schemas.Draft])
async def list_drafts(
    limit: int = Query(50, ge=1, le=500),
    kind: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List drafts with optional filtering.

    Args:
        limit: Maximum number of drafts to return
        kind: Filter by kind
        status: Filter by status
        db: Database session

    Returns:
        List of drafts
    """
    query = db.query(models.Draft)

    if kind:
        query = query.filter(models.Draft.kind == kind)
    if status:
        try:
            status_enum = models.DraftStatus(status)
            query = query.filter(models.Draft.status == status_enum)
        except ValueError:
            pass

    query = query.order_by(models.Draft.updated_at.desc())
    drafts = query.limit(limit).all()

    return [schemas.Draft.from_orm_model(d) for d in drafts]


@router.get("/drafts/{draft_id}", response_model=schemas.Draft)
async def get_draft(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get a specific draft.

    Args:
        draft_id: Draft UUID
        db: Database session

    Returns:
        Draft details
    """
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    return schemas.Draft.from_orm_model(draft)
