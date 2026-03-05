from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Header, HTTPException, Query
from sqlalchemy.orm import Session

from core.models import Workspace

DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_WORKSPACE_TITLE = "Default Workspace"


def ensure_default_workspace(db: Session) -> Workspace:
    row = db.query(Workspace).filter(Workspace.slug == DEFAULT_WORKSPACE_SLUG).first()
    if row:
        return row
    row = Workspace(slug=DEFAULT_WORKSPACE_SLUG, title=DEFAULT_WORKSPACE_TITLE)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_workspace_by_context(
    db: Session,
    *,
    workspace_id: Optional[uuid.UUID],
    workspace_slug: Optional[str],
) -> Workspace:
    row: Optional[Workspace] = None

    if workspace_id:
        row = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    elif workspace_slug:
        slug = str(workspace_slug).strip().lower()
        if slug:
            row = db.query(Workspace).filter(Workspace.slug == slug).first()

    if not row and (workspace_slug or "").strip().lower() == DEFAULT_WORKSPACE_SLUG:
        row = ensure_default_workspace(db)

    if not row:
        raise HTTPException(
            status_code=400,
            detail="Workspace context is required. Set workspace_id/workspace_slug query param or X-Workspace-Id/X-Workspace-Slug header.",
        )
    return row


def workspace_context(
    workspace_id: Optional[uuid.UUID] = Query(default=None),
    workspace_slug: Optional[str] = Query(default=None),
    x_workspace_id: Optional[uuid.UUID] = Header(default=None, alias="X-Workspace-Id"),
    x_workspace_slug: Optional[str] = Header(default=None, alias="X-Workspace-Slug"),
) -> dict[str, Optional[str | uuid.UUID]]:
    return {
        "workspace_id": workspace_id or x_workspace_id,
        "workspace_slug": workspace_slug or x_workspace_slug,
    }
