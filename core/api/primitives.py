"""Primitive catalog API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from core.access_control import CAP_APP_READ, AccessPrincipal, require_capabilities
from core.primitives import get_primitive_catalog

router = APIRouter()


@router.get("/primitives", response_model=list[dict[str, Any]])
async def list_primitives(
    principal: AccessPrincipal = Depends(require_capabilities(CAP_APP_READ)),
):
    return get_primitive_catalog()
