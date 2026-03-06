-- Phase 2 hardening: palette command registry

CREATE TABLE IF NOT EXISTS palette_commands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  command_key VARCHAR(255) NOT NULL,
  handler_type VARCHAR(64) NOT NULL DEFAULT 'http_json',
  handler_config_json JSON NOT NULL DEFAULT '{}'::json,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_palette_commands_workspace_id
  ON palette_commands(workspace_id);

CREATE INDEX IF NOT EXISTS ix_palette_commands_workspace_command
  ON palette_commands(workspace_id, command_key);

CREATE UNIQUE INDEX IF NOT EXISTS ux_palette_commands_global_command
  ON palette_commands(command_key)
  WHERE workspace_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_palette_commands_workspace_command
  ON palette_commands(workspace_id, command_key)
  WHERE workspace_id IS NOT NULL;

INSERT INTO schema_migrations (id, applied_at)
VALUES ('010_palette_commands_registry', NOW())
ON CONFLICT (id) DO NOTHING;
