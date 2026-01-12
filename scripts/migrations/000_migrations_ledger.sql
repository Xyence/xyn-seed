-- Migration: Create schema_migrations ledger
-- Purpose: track applied SQL migrations explicitly (framework-free)

CREATE TABLE IF NOT EXISTS schema_migrations (
  id TEXT PRIMARY KEY,                -- e.g. '005_steps_run_idx_constraints'
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Verify
SELECT COUNT(*) FROM schema_migrations;

-- Record this migration
INSERT INTO schema_migrations (id)
VALUES ('000_migrations_ledger')
ON CONFLICT (id) DO NOTHING;
