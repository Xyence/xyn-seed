-- Add CHECK constraint to enforce invariants for INSTALLED status
-- This prevents database-level corruption where status=INSTALLED but required fields are NULL

ALTER TABLE pack_installations
ADD CONSTRAINT ck_pack_installations_installed_invariants
CHECK (
    status != 'INSTALLED' OR (
        schema_name IS NOT NULL AND
        installed_version IS NOT NULL AND
        installed_at IS NOT NULL AND
        installed_by_run_id IS NOT NULL
    )
);

-- Verify the constraint was added
SELECT
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'pack_installations'::regclass
    AND conname = 'ck_pack_installations_installed_invariants';
