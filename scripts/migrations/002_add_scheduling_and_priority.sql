-- Migration: Add scheduling and priority support to runs table
-- Phase 1: Scheduled + Priority Queues
--
-- This migration adds:
-- - run_at: Timestamp for delayed/scheduled runs
-- - priority: Priority queue support (lower number = higher priority)
-- - attempt/max_attempts: Retry support with exponential backoff

BEGIN;

-- Add new columns
ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_at TIMESTAMP NULL;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 100;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS attempt INT NOT NULL DEFAULT 0;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS max_attempts INT NULL;

-- Backfill run_at for existing rows
-- For QUEUED runs: use queued_at
-- For other runs: use created_at (best approximation)
UPDATE runs
SET run_at = COALESCE(queued_at, created_at)
WHERE run_at IS NULL;

-- Make run_at NOT NULL after backfill
ALTER TABLE runs ALTER COLUMN run_at SET NOT NULL;

-- Add indexes for efficient claim queries
CREATE INDEX IF NOT EXISTS ix_runs_run_at ON runs(run_at);
CREATE INDEX IF NOT EXISTS ix_runs_priority ON runs(priority);

-- Composite index for optimized claim query
-- (priority ASC, run_at ASC) supports ORDER BY in claim query
CREATE INDEX IF NOT EXISTS ix_runs_priority_run_at ON runs(priority ASC, run_at ASC);

-- Add index for retry logic queries
CREATE INDEX IF NOT EXISTS ix_runs_attempt ON runs(attempt) WHERE attempt > 0;

COMMIT;

-- Verify migration
SELECT
    COUNT(*) as total_runs,
    COUNT(run_at) as runs_with_run_at,
    MIN(priority) as min_priority,
    MAX(priority) as max_priority,
    AVG(priority) as avg_priority,
    MAX(attempt) as max_attempts
FROM runs;

-- Record this migration
INSERT INTO schema_migrations (id)
VALUES ('002_add_scheduling_and_priority')
ON CONFLICT (id) DO NOTHING;
