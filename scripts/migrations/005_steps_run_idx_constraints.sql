-- Migration: Enforce stable step ordering per run and speed up ordered retrieval
-- Adds:
--   1) UNIQUE(run_id, idx) to prevent duplicate step indices within a run
--   2) Index for WHERE run_id=? ORDER BY idx (covered by unique index, but explicit is OK)
-- Notes:
--   - If duplicate (run_id, idx) already exist, the UNIQUE index creation will fail.
--   - See verification query at bottom before/after applying.

BEGIN;

-- 1) Optional preflight: detect duplicates that would break the unique index
-- (This SELECT does not block; it just reports.)
-- If this returns rows, you must resolve duplicates before creating the UNIQUE index.
SELECT run_id, idx, COUNT(*) AS cnt
FROM steps
GROUP BY run_id, idx
HAVING COUNT(*) > 1;

-- 2) Enforce uniqueness of step ordering per run
CREATE UNIQUE INDEX IF NOT EXISTS uq_steps_run_idx ON steps(run_id, idx);

-- 3) Optional: If you want a non-unique index for planner flexibility.
-- In Postgres, the UNIQUE index already supports the same access path, so you can skip this.
-- CREATE INDEX IF NOT EXISTS ix_steps_run_idx ON steps(run_id, idx);

COMMIT;

-- Verify: show indexes on steps
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'steps'
ORDER BY indexname;

-- Record this migration
INSERT INTO schema_migrations (id)
VALUES ('005_steps_run_idx_constraints')
ON CONFLICT (id) DO NOTHING;
