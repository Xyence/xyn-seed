"""Location primitive CRUD API endpoints."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.database import get_db
from core.access_control import (
    CAP_APP_READ,
    CAP_CAMPAIGNS_MANAGE,
    AccessPrincipal,
    enforce_access_or_403,
    require_capabilities,
)
from core.models import Location
from core.workspaces import resolve_workspace_by_context, workspace_context

logger = logging.getLogger(__name__)
router = APIRouter()

KNOWN_LOCATION_KINDS = {
    "site",
    "building",
    "room",
    "closet",
    "rack",
    "cabinet",
    "address",
    "billing",
    "service",
    "shipping",
    "other",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_kind(kind: str) -> str:
    value = str(kind or "").strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail="kind is required")
    if value not in KNOWN_LOCATION_KINDS:
        logger.warning("Unknown location kind requested: %s", value)
    return value


class LocationBase(BaseModel):
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    parent_location_id: Optional[uuid.UUID] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    tags_json: Optional[dict[str, Any]] = None


class LocationCreateRequest(LocationBase):
    workspace_id: Optional[uuid.UUID] = None


class LocationPatchRequest(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    parent_location_id: Optional[uuid.UUID] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    tags_json: Optional[dict[str, Any]] = None


class LocationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    kind: str
    parent_location_id: Optional[uuid.UUID] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    tags_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_model(cls, row: Location) -> "LocationResponse":
        return cls(
            id=row.id,
            workspace_id=row.workspace_id,
            name=row.name,
            kind=row.kind,
            parent_location_id=row.parent_location_id,
            address_line1=row.address_line1,
            address_line2=row.address_line2,
            city=row.city,
            region=row.region,
            postal_code=row.postal_code,
            country=row.country,
            notes=row.notes,
            tags_json=row.tags_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _validate_parent_workspace(db: Session, *, workspace_id: uuid.UUID, parent_location_id: Optional[uuid.UUID]) -> None:
    if not parent_location_id:
        return
    parent = db.query(Location).filter(Location.id == parent_location_id).first()
    if not parent:
        raise HTTPException(status_code=400, detail="parent_location_id does not exist")
    if parent.workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="parent_location_id must belong to the same workspace")


@router.get("/locations", response_model=list[LocationResponse])
async def list_locations(
    ctx: dict = Depends(workspace_context),
    kind: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    principal: AccessPrincipal = Depends(require_capabilities(CAP_APP_READ)),
    db: Session = Depends(get_db),
):
    workspace = resolve_workspace_by_context(
        db,
        workspace_id=ctx.get("workspace_id"),
        workspace_slug=ctx.get("workspace_slug"),
    )
    enforce_access_or_403(principal, required_capabilities=[CAP_APP_READ], workspace_id=workspace.id)
    query = db.query(Location).filter(Location.workspace_id == workspace.id)
    if kind:
        query = query.filter(Location.kind == _normalize_kind(kind))
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Location.name.ilike(term),
                Location.address_line1.ilike(term),
                Location.address_line2.ilike(term),
                Location.city.ilike(term),
                Location.region.ilike(term),
                Location.postal_code.ilike(term),
                Location.country.ilike(term),
                Location.notes.ilike(term),
            )
        )
    rows = query.order_by(Location.updated_at.desc()).limit(limit).all()
    return [LocationResponse.from_orm_model(row) for row in rows]


@router.post("/locations", response_model=LocationResponse, status_code=201)
async def create_location(
    payload: LocationCreateRequest,
    ctx: dict = Depends(workspace_context),
    principal: AccessPrincipal = Depends(require_capabilities(CAP_CAMPAIGNS_MANAGE)),
    db: Session = Depends(get_db),
):
    workspace = resolve_workspace_by_context(
        db,
        workspace_id=ctx.get("workspace_id"),
        workspace_slug=ctx.get("workspace_slug"),
    )
    enforce_access_or_403(principal, required_capabilities=[CAP_CAMPAIGNS_MANAGE], workspace_id=workspace.id)
    if payload.workspace_id and payload.workspace_id != workspace.id:
        raise HTTPException(status_code=403, detail="workspace_id does not match active workspace context")

    kind = _normalize_kind(payload.kind)
    _validate_parent_workspace(db, workspace_id=workspace.id, parent_location_id=payload.parent_location_id)

    row = Location(
        workspace_id=workspace.id,
        name=str(payload.name).strip(),
        kind=kind,
        parent_location_id=payload.parent_location_id,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        city=payload.city,
        region=payload.region,
        postal_code=payload.postal_code,
        country=payload.country,
        notes=payload.notes,
        tags_json=payload.tags_json,
    )
    if not row.name:
        raise HTTPException(status_code=400, detail="name is required")
    db.add(row)
    db.commit()
    db.refresh(row)
    return LocationResponse.from_orm_model(row)


@router.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: uuid.UUID,
    ctx: dict = Depends(workspace_context),
    principal: AccessPrincipal = Depends(require_capabilities(CAP_APP_READ)),
    db: Session = Depends(get_db),
):
    workspace = resolve_workspace_by_context(
        db,
        workspace_id=ctx.get("workspace_id"),
        workspace_slug=ctx.get("workspace_slug"),
    )
    enforce_access_or_403(principal, required_capabilities=[CAP_APP_READ], workspace_id=workspace.id)
    row = db.query(Location).filter(Location.id == location_id, Location.workspace_id == workspace.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationResponse.from_orm_model(row)


@router.patch("/locations/{location_id}", response_model=LocationResponse)
async def patch_location(
    location_id: uuid.UUID,
    payload: LocationPatchRequest,
    ctx: dict = Depends(workspace_context),
    principal: AccessPrincipal = Depends(require_capabilities(CAP_CAMPAIGNS_MANAGE)),
    db: Session = Depends(get_db),
):
    workspace = resolve_workspace_by_context(
        db,
        workspace_id=ctx.get("workspace_id"),
        workspace_slug=ctx.get("workspace_slug"),
    )
    enforce_access_or_403(principal, required_capabilities=[CAP_CAMPAIGNS_MANAGE], workspace_id=workspace.id)
    row = db.query(Location).filter(Location.id == location_id, Location.workspace_id == workspace.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")

    fields_set = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))

    if "name" in fields_set:
        if payload.name is None:
            raise HTTPException(status_code=400, detail="name cannot be null")
        name = str(payload.name).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        row.name = name
    if "kind" in fields_set:
        if payload.kind is None:
            raise HTTPException(status_code=400, detail="kind cannot be null")
        row.kind = _normalize_kind(payload.kind)
    if "parent_location_id" in fields_set:
        if payload.parent_location_id == row.id:
            raise HTTPException(status_code=400, detail="parent_location_id cannot reference itself")
        _validate_parent_workspace(db, workspace_id=workspace.id, parent_location_id=payload.parent_location_id)
        row.parent_location_id = payload.parent_location_id
    if "address_line1" in fields_set:
        row.address_line1 = payload.address_line1
    if "address_line2" in fields_set:
        row.address_line2 = payload.address_line2
    if "city" in fields_set:
        row.city = payload.city
    if "region" in fields_set:
        row.region = payload.region
    if "postal_code" in fields_set:
        row.postal_code = payload.postal_code
    if "country" in fields_set:
        row.country = payload.country
    if "notes" in fields_set:
        row.notes = payload.notes
    if "tags_json" in fields_set:
        row.tags_json = payload.tags_json

    row.updated_at = _utc_now()
    db.commit()
    db.refresh(row)
    return LocationResponse.from_orm_model(row)


@router.delete("/locations/{location_id}")
async def delete_location(
    location_id: uuid.UUID,
    ctx: dict = Depends(workspace_context),
    principal: AccessPrincipal = Depends(require_capabilities(CAP_CAMPAIGNS_MANAGE)),
    db: Session = Depends(get_db),
):
    workspace = resolve_workspace_by_context(
        db,
        workspace_id=ctx.get("workspace_id"),
        workspace_slug=ctx.get("workspace_slug"),
    )
    enforce_access_or_403(principal, required_capabilities=[CAP_CAMPAIGNS_MANAGE], workspace_id=workspace.id)
    row = db.query(Location).filter(Location.id == location_id, Location.workspace_id == workspace.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")
    child = db.query(Location).filter(Location.parent_location_id == row.id, Location.workspace_id == workspace.id).first()
    if child:
        raise HTTPException(status_code=409, detail="Cannot delete location with child locations")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "id": str(location_id)}
