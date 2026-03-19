"""Palette API endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from core.access_control import (
    CAP_APP_READ,
    CAP_CAMPAIGNS_MANAGE,
    AccessPrincipal,
    enforce_access_or_403,
    require_capabilities,
)
from core.models import PaletteCommand
from core.palette_commands import normalize_command_key, utc_now
from core.palette_engine import execute_palette_prompt
from core.workspaces import resolve_workspace_by_context, workspace_context

router = APIRouter()


class PaletteExecuteRequest(BaseModel):
    prompt: str = Field(min_length=1)
    workspace_id: Optional[uuid.UUID] = None
    workspace_slug: Optional[str] = None


class PaletteCommandCreateRequest(BaseModel):
    command_key: str = Field(min_length=1)
    handler_type: str = Field(default="http_json", min_length=1)
    handler_config_json: dict[str, Any] = Field(default_factory=dict)
    workspace_id: Optional[uuid.UUID] = None


class PaletteCommandPatchRequest(BaseModel):
    command_key: Optional[str] = None
    handler_type: Optional[str] = None
    handler_config_json: Optional[dict[str, Any]] = None
    workspace_id: Optional[uuid.UUID] = None


class PaletteCommandResponse(BaseModel):
    id: uuid.UUID
    workspace_id: Optional[uuid.UUID] = None
    command_key: str
    handler_type: str
    handler_config_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_model(cls, row: PaletteCommand) -> "PaletteCommandResponse":
        return cls(
            id=row.id,
            workspace_id=row.workspace_id,
            command_key=row.command_key,
            handler_type=row.handler_type,
            handler_config_json=row.handler_config_json or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _validate_handler_type(value: str) -> str:
    handler_type = str(value or "").strip().lower()
    if handler_type != "http_json":
        raise HTTPException(status_code=400, detail="handler_type must be http_json")
    return handler_type


def _validate_workspace_scope(
    *,
    active_workspace_id: uuid.UUID,
    requested_workspace_id: Optional[uuid.UUID],
) -> Optional[uuid.UUID]:
    if requested_workspace_id is None:
        return active_workspace_id
    if requested_workspace_id == active_workspace_id:
        return active_workspace_id
    raise HTTPException(status_code=403, detail="workspace_id does not match active workspace context")


def _command_exists(
    db: Session,
    *,
    command_key: str,
    workspace_id: Optional[uuid.UUID],
    exclude_id: Optional[uuid.UUID] = None,
) -> bool:
    query = db.query(PaletteCommand).filter(
        func.lower(PaletteCommand.command_key) == normalize_command_key(command_key),
    )
    if workspace_id is None:
        query = query.filter(PaletteCommand.workspace_id.is_(None))
    else:
        query = query.filter(PaletteCommand.workspace_id == workspace_id)
    if exclude_id:
        query = query.filter(PaletteCommand.id != exclude_id)
    return query.first() is not None


@router.post("/palette/execute", response_model=dict[str, Any])
async def execute_palette(
    payload: PaletteExecuteRequest,
    ctx: dict = Depends(workspace_context),
    principal: AccessPrincipal = Depends(require_capabilities(CAP_APP_READ)),
    db: Session = Depends(get_db),
):
    try:
        return execute_palette_prompt(
            db,
            prompt=payload.prompt,
            workspace_id=payload.workspace_id or ctx.get("workspace_id"),
            workspace_slug=payload.workspace_slug or ctx.get("workspace_slug"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/palette/commands", response_model=list[PaletteCommandResponse])
async def list_palette_commands(
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
    rows = (
        db.query(PaletteCommand)
        .filter((PaletteCommand.workspace_id == workspace.id) | (PaletteCommand.workspace_id.is_(None)))
        .order_by(PaletteCommand.workspace_id.is_(None), PaletteCommand.command_key.asc())
        .all()
    )
    return [PaletteCommandResponse.from_orm_model(row) for row in rows]


@router.post("/palette/commands", response_model=PaletteCommandResponse, status_code=201)
async def create_palette_command(
    payload: PaletteCommandCreateRequest,
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
    command_key = normalize_command_key(payload.command_key)
    if not command_key:
        raise HTTPException(status_code=400, detail="command_key is required")
    scoped_workspace_id = _validate_workspace_scope(
        active_workspace_id=workspace.id,
        requested_workspace_id=payload.workspace_id,
    )
    if _command_exists(db, command_key=command_key, workspace_id=scoped_workspace_id):
        raise HTTPException(status_code=409, detail="palette command already exists for this workspace")
    row = PaletteCommand(
        workspace_id=scoped_workspace_id,
        command_key=command_key,
        handler_type=_validate_handler_type(payload.handler_type),
        handler_config_json=payload.handler_config_json or {},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return PaletteCommandResponse.from_orm_model(row)


@router.patch("/palette/commands/{command_id}", response_model=PaletteCommandResponse)
async def patch_palette_command(
    command_id: uuid.UUID,
    payload: PaletteCommandPatchRequest,
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
    row = (
        db.query(PaletteCommand)
        .filter(
            PaletteCommand.id == command_id,
            (PaletteCommand.workspace_id == workspace.id) | (PaletteCommand.workspace_id.is_(None)),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Palette command not found")

    fields_set = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))
    if "workspace_id" in fields_set:
        row.workspace_id = _validate_workspace_scope(
            active_workspace_id=workspace.id,
            requested_workspace_id=payload.workspace_id,
        )
    if "command_key" in fields_set:
        command_key = normalize_command_key(payload.command_key or "")
        if not command_key:
            raise HTTPException(status_code=400, detail="command_key cannot be empty")
        if _command_exists(db, command_key=command_key, workspace_id=row.workspace_id, exclude_id=row.id):
            raise HTTPException(status_code=409, detail="palette command already exists for this workspace")
        row.command_key = command_key
    if "handler_type" in fields_set:
        row.handler_type = _validate_handler_type(payload.handler_type or "")
    if "handler_config_json" in fields_set:
        row.handler_config_json = payload.handler_config_json or {}
    row.updated_at = utc_now()
    db.commit()
    db.refresh(row)
    return PaletteCommandResponse.from_orm_model(row)


@router.delete("/palette/commands/{command_id}")
async def delete_palette_command(
    command_id: uuid.UUID,
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
    row = (
        db.query(PaletteCommand)
        .filter(
            PaletteCommand.id == command_id,
            PaletteCommand.workspace_id == workspace.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Palette command not found for workspace")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "id": str(command_id)}
