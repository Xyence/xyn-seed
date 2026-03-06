"""Palette command registry helpers."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models import PaletteCommand


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_command_key(value: str) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def ensure_default_palette_commands(db: Session) -> None:
    """Seed global default commands used by Phase 2 validation."""
    key = "show devices"
    existing = (
        db.query(PaletteCommand)
        .filter(PaletteCommand.workspace_id.is_(None), func.lower(PaletteCommand.command_key) == key)
        .first()
    )
    if existing:
        return
    row = PaletteCommand(
        workspace_id=None,
        command_key=key,
        handler_type="http_json",
        handler_config_json={
            "base_url": "$deployment.app_url",
            "method": "GET",
            "path": "/devices",
            "query_map": {"workspace_id": "$workspace_id"},
            "response_adapter": {
                "kind": "table",
                "columns": ["id", "name", "kind", "status", "workspace_id", "location_id"],
                "text_template": "{{count}} devices found",
            },
        },
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(row)
    db.commit()


def resolve_palette_command(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    prompt: str,
) -> PaletteCommand | None:
    key = normalize_command_key(prompt)
    if not key:
        return None

    workspace_match = (
        db.query(PaletteCommand)
        .filter(
            PaletteCommand.workspace_id == workspace_id,
            func.lower(PaletteCommand.command_key) == key,
        )
        .order_by(PaletteCommand.updated_at.desc())
        .first()
    )
    if workspace_match:
        return workspace_match

    global_match = (
        db.query(PaletteCommand)
        .filter(
            PaletteCommand.workspace_id.is_(None),
            func.lower(PaletteCommand.command_key) == key,
        )
        .order_by(PaletteCommand.updated_at.desc())
        .first()
    )
    return global_match


def list_palette_commands(
    db: Session,
    *,
    workspace_id: uuid.UUID,
) -> list[PaletteCommand]:
    return (
        db.query(PaletteCommand)
        .filter((PaletteCommand.workspace_id == workspace_id) | (PaletteCommand.workspace_id.is_(None)))
        .order_by(PaletteCommand.workspace_id.is_(None), PaletteCommand.command_key.asc())
        .all()
    )


def build_palette_result_from_items(
    *,
    items: list[dict[str, Any]],
    columns: list[str],
    text_template: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        for column in columns:
            value = item.get(column)
            row[column] = "" if value is None else value
        rows.append(row)
    text = str(text_template or "{{count}} rows").replace("{{count}}", str(len(rows)))
    return {
        "kind": "table",
        "columns": columns,
        "rows": rows,
        "text": text,
    }
