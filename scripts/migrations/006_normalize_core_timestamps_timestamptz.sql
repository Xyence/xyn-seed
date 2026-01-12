-- Migration: Normalize core execution timestamps to timestamptz (UTC)
--
-- Why:
-- - Avoid timezone ambiguity in distributed/Kubernetes deployments
-- - Ensure correct comparisons with NOW() and intervals across nodes
-- - Improve future observability, UI display, and analytics
--
-- Assumption:
-- - Existing timestamp values were written as UTC (Python datetime.utcnow()).
--   We convert by interpreting existing "timestamp without time zone" values as UTC.

BEGIN;

-- runs (7 timestamp columns)
ALTER TABLE runs
  ALTER COLUMN created_at       TYPE timestamptz USING (created_at       AT TIME ZONE 'UTC'),
  ALTER COLUMN started_at       TYPE timestamptz USING (started_at       AT TIME ZONE 'UTC'),
  ALTER COLUMN completed_at     TYPE timestamptz USING (completed_at     AT TIME ZONE 'UTC'),
  ALTER COLUMN queued_at        TYPE timestamptz USING (queued_at        AT TIME ZONE 'UTC'),
  ALTER COLUMN locked_at        TYPE timestamptz USING (locked_at        AT TIME ZONE 'UTC'),
  ALTER COLUMN lease_expires_at TYPE timestamptz USING (lease_expires_at AT TIME ZONE 'UTC'),
  ALTER COLUMN run_at           TYPE timestamptz USING (run_at           AT TIME ZONE 'UTC');

-- events (2 timestamp columns)
ALTER TABLE events
  ALTER COLUMN occurred_at TYPE timestamptz USING (occurred_at AT TIME ZONE 'UTC'),
  ALTER COLUMN created_at  TYPE timestamptz USING (created_at  AT TIME ZONE 'UTC');

-- steps (3 timestamp columns)
ALTER TABLE steps
  ALTER COLUMN created_at   TYPE timestamptz USING (created_at   AT TIME ZONE 'UTC'),
  ALTER COLUMN started_at   TYPE timestamptz USING (started_at   AT TIME ZONE 'UTC'),
  ALTER COLUMN completed_at TYPE timestamptz USING (completed_at AT TIME ZONE 'UTC');

-- run_edges (1 timestamp column - for completeness)
ALTER TABLE run_edges
  ALTER COLUMN created_at TYPE timestamptz USING (created_at AT TIME ZONE 'UTC');

COMMIT;

-- Record this migration
INSERT INTO schema_migrations (id)
VALUES ('006_normalize_core_timestamps_timestamptz')
ON CONFLICT (id) DO NOTHING;

-- Verify types (quick sanity check)
SELECT
  'runs'      AS table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name='runs' AND column_name IN (
  'created_at','started_at','completed_at','queued_at','locked_at','lease_expires_at','run_at'
)
UNION ALL
SELECT
  'events'    AS table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name='events' AND column_name IN ('occurred_at','created_at')
UNION ALL
SELECT
  'steps'     AS table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name='steps' AND column_name IN ('created_at','started_at','completed_at')
UNION ALL
SELECT
  'run_edges' AS table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name='run_edges' AND column_name IN ('created_at')
ORDER BY table_name, column_name;
