# Location Primitive

The `location` primitive is a reusable, workspace-scoped entity for physical places and addresses.

## Purpose

Use `location_id` references from app data models (devices, accounts, orders, contracts) instead of duplicating address/location fields everywhere.

## Supported Kinds

- `site`
- `building`
- `room`
- `closet`
- `rack`
- `cabinet`
- `address`
- `billing`
- `service`
- `shipping`
- `other`

Unknown kinds are allowed and logged as warnings for forward compatibility.

## Hierarchy

`parent_location_id` allows location trees such as:

- site -> building -> room -> closet -> rack

Validation enforces parent and child are in the same workspace.

## API

- `GET /api/v1/locations`
- `POST /api/v1/locations`
- `GET /api/v1/locations/{id}`
- `PATCH /api/v1/locations/{id}`
- `DELETE /api/v1/locations/{id}`

All endpoints are workspace-scoped via workspace context (`workspace_id`/`workspace_slug` query or `X-Workspace-*` headers).
