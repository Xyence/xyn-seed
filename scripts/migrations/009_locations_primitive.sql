-- Migration: 009_locations_primitive
-- Purpose: Add reusable workspace-scoped Location primitive table.

BEGIN;

CREATE TABLE IF NOT EXISTS locations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
  name VARCHAR(255) NOT NULL,
  kind VARCHAR(64) NOT NULL,
  parent_location_id UUID NULL REFERENCES locations(id) ON DELETE SET NULL,
  address_line1 VARCHAR(255),
  address_line2 VARCHAR(255),
  city VARCHAR(255),
  region VARCHAR(255),
  postal_code VARCHAR(64),
  country VARCHAR(128),
  notes TEXT,
  tags_json JSON,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_locations_workspace_id ON locations(workspace_id);
CREATE INDEX IF NOT EXISTS ix_locations_workspace_kind ON locations(workspace_id, kind);
CREATE INDEX IF NOT EXISTS ix_locations_workspace_parent ON locations(workspace_id, parent_location_id);

COMMIT;

-- Record migration
INSERT INTO schema_migrations (id)
VALUES ('009_locations_primitive')
ON CONFLICT (id) DO NOTHING;
