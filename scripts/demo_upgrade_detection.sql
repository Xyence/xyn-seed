-- Demo: Upgrade Detection Scenario
-- This shows how the metadata supports upgrade workflows

-- 1. Show current installation
SELECT
    pack_ref,
    installed_version as current_version,
    schema_name,
    migration_state,
    installed_at
FROM pack_installations
WHERE pack_ref LIKE 'core.domain%';

-- 2. Simulate registering a new version (v2)
-- In reality this would be done via API/seed script
INSERT INTO packs (
    id,
    pack_ref,
    name,
    version,
    description,
    schema_name,
    manifest,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'core.domain@v2',
    'Core Domain',
    '2.0.0',
    'Core domain models - v2 with customer types',
    'pack_core_domain',  -- Same schema, upgrade in place
    '{
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "type": "UUID", "primary_key": true},
                    {"name": "name", "type": "VARCHAR(255)", "nullable": false},
                    {"name": "email", "type": "VARCHAR(255)", "nullable": false, "unique": true},
                    {"name": "customer_type", "type": "VARCHAR(50)", "nullable": false},
                    {"name": "status", "type": "VARCHAR(50)", "nullable": false},
                    {"name": "created_at", "type": "TIMESTAMP", "nullable": false},
                    {"name": "updated_at", "type": "TIMESTAMP", "nullable": false}
                ]
            },
            {
                "name": "sites",
                "columns": [
                    {"name": "id", "type": "UUID", "primary_key": true},
                    {"name": "customer_id", "type": "UUID", "nullable": false, "foreign_key": "customers.id"},
                    {"name": "name", "type": "VARCHAR(255)", "nullable": false},
                    {"name": "url", "type": "VARCHAR(512)", "nullable": true},
                    {"name": "status", "type": "VARCHAR(50)", "nullable": false},
                    {"name": "created_at", "type": "TIMESTAMP", "nullable": false},
                    {"name": "updated_at", "type": "TIMESTAMP", "nullable": false}
                ]
            }
        ],
        "migrations": [
            {
                "id": "20260111_001_add_customer_type",
                "description": "Add customer_type column",
                "sql": "ALTER TABLE pack_core_domain.customers ADD COLUMN customer_type VARCHAR(50) DEFAULT '\''standard'\'' NOT NULL;"
            }
        ],
        "pack_type": "domain",
        "dependencies": []
    }'::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (pack_ref) DO NOTHING;

-- 3. Upgrade detection query
-- Shows which packs have newer versions available
SELECT
    pi.pack_ref as installed_pack,
    pi.installed_version as current_version,
    pi.migration_state as current_migration,
    p.pack_ref as available_pack,
    p.version as available_version,
    (SELECT COUNT(*) FROM jsonb_array_elements(p.manifest->'migrations')) as new_migrations
FROM pack_installations pi
CROSS JOIN packs p
WHERE pi.status::text = 'installed'
  AND pi.pack_ref LIKE 'core.domain%'
  AND p.pack_ref = 'core.domain@v2';

-- 4. Migration delta query
-- Shows which migrations need to be applied
SELECT
    pi.pack_ref,
    pi.migration_state as last_applied,
    jsonb_array_elements(p.manifest->'migrations')->>'id' as migration_id,
    jsonb_array_elements(p.manifest->'migrations')->>'description' as migration_desc
FROM pack_installations pi
JOIN packs p ON p.pack_ref = 'core.domain@v2'
WHERE pi.pack_ref = 'core.domain@v1'
  AND (
    pi.migration_state IS NULL
    OR jsonb_array_elements(p.manifest->'migrations')->>'id' > pi.migration_state
  );

-- 5. Audit trail query
-- Shows installation history with run details
SELECT
    pi.pack_ref,
    pi.installed_version,
    pi.installed_at,
    pi.installed_by_run_id,
    r.status as installation_status,
    r.started_at as install_started,
    r.completed_at as install_completed,
    (r.completed_at - r.started_at) as install_duration
FROM pack_installations pi
LEFT JOIN runs r ON r.id = pi.installed_by_run_id
WHERE pi.pack_ref LIKE 'core.domain%'
ORDER BY pi.installed_at DESC;

-- Cleanup (optional)
-- DELETE FROM packs WHERE pack_ref = 'core.domain@v2';
