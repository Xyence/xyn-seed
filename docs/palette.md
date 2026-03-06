# Palette Commands

Palette execution is registry-driven via `palette_commands`.

## Model

- `workspace_id` nullable (`null` means global default)
- `command_key`
- `handler_type` (`http_json` for Phase 2)
- `handler_config_json`

Workspace-specific commands override global commands with the same normalized key.

## API

- `GET /api/v1/palette/commands`
- `POST /api/v1/palette/commands`
- `PATCH /api/v1/palette/commands/{id}`
- `DELETE /api/v1/palette/commands/{id}`
- `POST /api/v1/palette/execute`

## Default Command

Seed creates a global command:

- `show devices` -> deployed net-inventory `/devices` with `workspace_id` query mapping.

This keeps palette behavior configurable without hardcoded prompt routing.
