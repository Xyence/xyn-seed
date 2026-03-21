"""Access control visibility and helper endpoints."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.access_control import (
    AccessPrincipal,
    assert_access,
    principal_from_request,
    role_capability_catalog,
    CAP_PLATFORM_ACCESS_READ,
)

router = APIRouter()


def _principal(request: Request) -> AccessPrincipal:
    return principal_from_request(request)


@router.get("/access/roles")
async def list_access_roles(
    principal: AccessPrincipal = Depends(_principal),
) -> dict[str, Any]:
    try:
        assert_access(principal, required_capabilities=[CAP_PLATFORM_ACCESS_READ])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "roles": role_capability_catalog(),
    }


@router.get("/access/me")
async def access_me(
    request: Request,
    application_slug: Optional[str] = Query(default=None),
    principal: AccessPrincipal = Depends(_principal),
) -> dict[str, Any]:
    """Return effective principal, role, and capability scope for current request."""
    inferred_workspace_scope = principal.workspace_scope_id or request.headers.get("X-Workspace-Id")
    return {
        "subject_id": principal.subject_id,
        "roles": list(principal.roles),
        "capabilities": list(principal.capabilities),
        "workspace_scope_id": str(inferred_workspace_scope) if inferred_workspace_scope else None,
        "application_scope": principal.application_scope or (str(application_slug or "").strip().lower() or None),
    }
