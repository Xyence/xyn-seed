-- Migration: 012_runtime_execution_layer
-- Purpose: Add Epic C runtime execution contract fields and worker registrations.

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'runtimeworkerstatus') THEN
    CREATE TYPE runtimeworkerstatus AS ENUM ('IDLE', 'BUSY', 'OFFLINE');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_enum e ON t.oid = e.enumtypid
    WHERE t.typname = 'runstatus' AND e.enumlabel = 'BLOCKED'
  ) THEN
    ALTER TYPE runstatus ADD VALUE 'BLOCKED';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_enum e ON t.oid = e.enumtypid
    WHERE t.typname = 'stepstatus' AND e.enumlabel = 'QUEUED'
  ) THEN
    ALTER TYPE stepstatus ADD VALUE 'QUEUED' BEFORE 'CREATED';
  END IF;
END $$;

ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS work_item_id VARCHAR(255),
  ADD COLUMN IF NOT EXISTS worker_type VARCHAR(255),
  ADD COLUMN IF NOT EXISTS prompt_payload JSON NOT NULL DEFAULT '{}'::json,
  ADD COLUMN IF NOT EXISTS execution_policy JSON NOT NULL DEFAULT '{}'::json,
  ADD COLUMN IF NOT EXISTS summary TEXT,
  ADD COLUMN IF NOT EXISTS escalation_reason VARCHAR(255),
  ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_runs_work_item_id ON runs(work_item_id);
CREATE INDEX IF NOT EXISTS ix_runs_worker_type ON runs(worker_type);
CREATE INDEX IF NOT EXISTS ix_runs_heartbeat_at ON runs(heartbeat_at);

ALTER TABLE steps
  ADD COLUMN IF NOT EXISTS step_key VARCHAR(255),
  ADD COLUMN IF NOT EXISTS label VARCHAR(255),
  ADD COLUMN IF NOT EXISTS summary TEXT;

UPDATE steps SET step_key = COALESCE(step_key, name);
UPDATE steps SET label = COALESCE(label, name);

CREATE INDEX IF NOT EXISTS ix_steps_step_key ON steps(step_key);

CREATE TABLE IF NOT EXISTS runtime_workers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id VARCHAR(255) NOT NULL UNIQUE,
  worker_type VARCHAR(255) NOT NULL,
  runtime_environment VARCHAR(255) NOT NULL,
  status runtimeworkerstatus NOT NULL DEFAULT 'IDLE',
  last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  capabilities_json JSON NOT NULL DEFAULT '[]'::json,
  active_run_id UUID REFERENCES runs(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_runtime_workers_worker_type ON runtime_workers(worker_type);
CREATE INDEX IF NOT EXISTS ix_runtime_workers_status ON runtime_workers(status);
CREATE INDEX IF NOT EXISTS ix_runtime_workers_last_heartbeat ON runtime_workers(last_heartbeat);
CREATE INDEX IF NOT EXISTS ix_runtime_workers_worker_type_status ON runtime_workers(worker_type, status);

INSERT INTO schema_migrations (id, applied_at)
VALUES ('012_runtime_execution_layer', NOW())
ON CONFLICT (id) DO NOTHING;

COMMIT;
