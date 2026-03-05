"""Reusable primitive catalog for app-building flows."""
from __future__ import annotations

from typing import Any


def get_primitive_catalog() -> list[dict[str, Any]]:
    return [
        {
            "slug": "location",
            "title": "Location",
            "workspace_scoped": True,
            "api_base": "/api/v1/locations",
            "description": "Named place/address with optional hierarchy; reusable across apps.",
            "fields": {
                "id": "uuid",
                "workspace_id": "uuid",
                "name": "string",
                "kind": "string",
                "parent_location_id": "uuid|null",
                "address_line1": "string|null",
                "address_line2": "string|null",
                "city": "string|null",
                "region": "string|null",
                "postal_code": "string|null",
                "country": "string|null",
                "notes": "text|null",
                "tags_json": "json|null",
                "created_at": "datetime",
                "updated_at": "datetime",
            },
        }
    ]
