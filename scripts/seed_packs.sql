-- Seed core.domain pack into registry
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
    'core.domain@v1',
    'Core Domain',
    '1.0.0',
    'Core domain models for customers and sites',
    'pack_core_domain',
    '{
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "type": "UUID", "primary_key": true},
                    {"name": "name", "type": "VARCHAR(255)", "nullable": false},
                    {"name": "email", "type": "VARCHAR(255)", "nullable": false, "unique": true},
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
        "migrations": [],
        "pack_type": "domain",
        "dependencies": []
    }'::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (pack_ref) DO NOTHING;
