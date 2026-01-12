-- Migration: Add run_edges table for DAG execution (parent/child runs)
-- Phase 2: Sub-run Fan-out
--
-- Adds:
-- - run_edges table: Links parent runs to child runs
-- - child_key: Idempotent spawn key for resumable orchestration

BEGIN;

-- Ensure UUID helper exists
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create run_edges table for parent->child relationships
CREATE TABLE IF NOT EXISTS run_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    child_run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    relation TEXT NOT NULL DEFAULT 'child',
    child_key TEXT NULL,  -- Idempotency key for resumable spawns
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate parent->child edges
    UNIQUE(parent_run_id, child_run_id)
);

-- Indexes for efficient parent/child lookups
CREATE INDEX IF NOT EXISTS ix_run_edges_parent ON run_edges(parent_run_id);
CREATE INDEX IF NOT EXISTS ix_run_edges_child ON run_edges(child_run_id);

-- Idempotency: prevent duplicate spawns with same child_key (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS uq_run_edges_parent_child_key
ON run_edges(parent_run_id, child_key)
WHERE child_key IS NOT NULL;

-- Add parent_run_id to runs table for convenience (denormalized)
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS parent_run_id UUID NULL REFERENCES runs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_runs_parent_run_id
ON runs(parent_run_id)
WHERE parent_run_id IS NOT NULL;

COMMIT;

-- Verify migration
SELECT
    COUNT(*) as total_edges,
    COUNT(DISTINCT parent_run_id) as parents_with_children,
    COUNT(DISTINCT child_run_id) as children_with_parents
FROM run_edges;

-- Record this migration
INSERT INTO schema_migrations (id)
VALUES ('003_add_run_edges_for_dag')
ON CONFLICT (id) DO NOTHING;
