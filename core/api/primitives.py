"""Primitive catalog API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from core.primitives import get_primitive_catalog

router = APIRouter()


@router.get("/primitives", response_model=list[dict[str, Any]])
async def list_primitives():
    return get_primitive_catalog()
