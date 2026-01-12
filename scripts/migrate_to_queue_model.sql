-- Migration: Add queue and lease management to runs table
-- Converts from synchronous execution to Postgres-backed queue

-- Add QUEUED status to RunStatus enum
ALTER TYPE runstatus ADD VALUE IF NOT EXISTS 'queued' BEFORE 'created';

-- Add queue and lease management columns
ALTER TABLE runs ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS locked_by VARCHAR(255);
ALTER TABLE runs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMP;

-- Add indexes for queue queries
CREATE INDEX IF NOT EXISTS ix_runs_queued_at ON runs(queued_at);
CREATE INDEX IF NOT EXISTS ix_runs_lease_expires_at ON runs(lease_expires_at);

-- Change default status from CREATED to QUEUED
ALTER TABLE runs ALTER COLUMN status SET DEFAULT 'queued'::runstatus;

-- Backfill existing runs: set queued_at = created_at for old CREATED runs
UPDATE runs
SET queued_at = created_at
WHERE status = 'created' AND queued_at IS NULL;

-- Verify the migration
SELECT
    'Migration complete' as status,
    COUNT(*) FILTER (WHERE status = 'queued') as queued_runs,
    COUNT(*) FILTER (WHERE status = 'running') as running_runs,
    COUNT(*) FILTER (WHERE status = 'completed') as completed_runs,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_runs
FROM runs;
