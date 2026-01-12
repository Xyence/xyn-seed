-- Migration: Add optimized indexes for queue claim query
-- Production hardening for Phase 1
--
-- This migration adds indexes to optimize the worker claim query:
-- - Composite index for general queue access
-- - Partial index for queued runs (most common lookup)
-- - Partial index for expired lease detection (crash recovery)

BEGIN;

-- Composite index for general queue claim access
-- Supports: filter by status + order by priority/run_at/queued_at/created_at
CREATE INDEX IF NOT EXISTS ix_runs_queue_claim
ON runs (status, priority, run_at, queued_at, created_at);

-- Partial index optimized for QUEUED runs (hot path)
-- Smaller, faster for the common case of claiming new work
CREATE INDEX IF NOT EXISTS ix_runs_queued_due
ON runs (priority, run_at, queued_at, created_at)
WHERE status = 'QUEUED';

-- Partial index for reclaiming expired leases (crash recovery)
-- Enables fast detection of zombie runs
CREATE INDEX IF NOT EXISTS ix_runs_running_expired
ON runs (lease_expires_at)
WHERE status = 'RUNNING';

COMMIT;

-- Verify indexes created
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'runs'
  AND indexname LIKE 'ix_runs_%claim%'
     OR indexname LIKE 'ix_runs_queued%'
     OR indexname LIKE 'ix_runs_running%';

-- Record this migration
INSERT INTO schema_migrations (id)
VALUES ('004_add_queue_claim_indexes')
ON CONFLICT (id) DO NOTHING;
