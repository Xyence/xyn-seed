"""Workspace API endpoints for Phase 2 validation flows."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Workspace
from core.workspaces import DEFAULT_WORKSPACE_SLUG, ensure_default_workspace

router = APIRouter()


def _normalize_slug(value: str) -> str:
    raw = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", raw).strip("-")
    return slug


class WorkspaceCreateRequest(BaseModel):
    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_model(cls, row: Workspace) -> "WorkspaceResponse":
        return cls(
            id=row.id,
            slug=row.slug,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    include_default: bool = True,
    db: Session = Depends(get_db),
):
    if include_default:
        ensure_default_workspace(db)
    rows = db.query(Workspace).order_by(Workspace.slug.asc()).all()
    return [WorkspaceResponse.from_orm_model(row) for row in rows]


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    db: Session = Depends(get_db),
):
    ensure_default_workspace(db)
    slug = _normalize_slug(payload.slug)
    title = str(payload.title or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if slug == DEFAULT_WORKSPACE_SLUG:
        existing_default = db.query(Workspace).filter(Workspace.slug == DEFAULT_WORKSPACE_SLUG).first()
        if existing_default:
            return WorkspaceResponse.from_orm_model(existing_default)
    existing = db.query(Workspace).filter(func.lower(Workspace.slug) == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="workspace slug already exists")
    row = Workspace(slug=slug, title=title)
    db.add(row)
    db.commit()
    db.refresh(row)
    return WorkspaceResponse.from_orm_model(row)
