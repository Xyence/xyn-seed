# Deployment Guide: Database Migrations

## Environment Configuration

### Local Development

```bash
# Allow auto-creation for rapid development
export XYN_AUTO_CREATE_SCHEMA=true
```

SQLAlchemy will create tables automatically on first startup. Migrations optional but recommended for testing.

### CI/Testing

```bash
# Require baseline schema only
export XYN_AUTO_CREATE_SCHEMA=false
export XYN_REQUIRED_MIGRATIONS=001_initial_schema
```

Apply migrations before tests:
```bash
./scripts/apply_migrations.sh
pytest
```

### Staging/Production (Strict Mode)

```bash
# Require all migrations
export XYN_AUTO_CREATE_SCHEMA=false
export XYN_REQUIRED_MIGRATIONS=001_initial_schema,002_add_scheduling_and_priority,003_add_run_edges_for_dag,004_add_queue_claim_indexes,005_steps_run_idx_constraints
```

Apply migrations as part of deployment:
```bash
# Pre-deploy step
./scripts/apply_migrations.sh

# Deploy application
# App will fail fast if migrations missing
```

## Kubernetes Example

### ConfigMap for Environment

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: xyn-config
data:
  XYN_AUTO_CREATE_SCHEMA: "false"
  XYN_REQUIRED_MIGRATIONS: "001_initial_schema,002_add_scheduling_and_priority,003_add_run_edges_for_dag,004_add_queue_claim_indexes,005_steps_run_idx_constraints"
```

### Init Container for Migrations

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: xyn-worker
spec:
  template:
    spec:
      initContainers:
      - name: migrate
        image: xyn-app:latest
        command: ["/app/scripts/apply_migrations.sh"]
        envFrom:
        - configMapRef:
            name: xyn-config
        - secretRef:
            name: xyn-db-credentials
      containers:
      - name: worker
        image: xyn-app:latest
        command: ["python", "-m", "core.worker"]
        envFrom:
        - configMapRef:
            name: xyn-config
        - secretRef:
            name: xyn-db-credentials
```

## Docker Compose Example

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: xyn
      POSTGRES_PASSWORD: xyn_password
      POSTGRES_DB: xyn
    volumes:
      - postgres_data:/var/lib/postgresql/data

  migrate:
    image: xyn-app:latest
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql://xyn:xyn_password@postgres:5432/xyn
      XYN_AUTO_CREATE_SCHEMA: "false"
    command: ./scripts/apply_migrations.sh

  worker:
    image: xyn-app:latest
    depends_on:
      migrate:
        condition: service_completed_successfully
    environment:
      DATABASE_URL: postgresql://xyn:xyn_password@postgres:5432/xyn
      XYN_AUTO_CREATE_SCHEMA: "false"
      XYN_REQUIRED_MIGRATIONS: "001_initial_schema,002_add_scheduling_and_priority,003_add_run_edges_for_dag,004_add_queue_claim_indexes,005_steps_run_idx_constraints"
    command: python -m core.worker

volumes:
  postgres_data:
```

## Migration Workflow

### Adding a New Migration

1. Create migration file:
```bash
scripts/migrations/006_your_feature.sql
```

2. Test locally:
```bash
./scripts/apply_migrations.sh
```

3. Update `XYN_REQUIRED_MIGRATIONS` in deployment configs (if required for app to function)

4. Deploy:
   - Migrations run via init container/pre-deploy step
   - App validates required migrations on startup
   - Fails fast if missing

### Rollback Strategy

Migrations are **forward-only**. To rollback:

1. Deploy previous app version
2. Optionally: write compensating migration to undo changes
3. Never delete applied migrations from `schema_migrations` table

### Zero-Downtime Deployments

For breaking schema changes:

1. **Phase 1**: Additive migration
   - Add new columns/tables (nullable)
   - Deploy app version that works with both schemas

2. **Phase 2**: Data migration
   - Backfill data
   - Verify correctness

3. **Phase 3**: Cleanup migration
   - Drop old columns/tables
   - Deploy app version using only new schema

## Troubleshooting

### App won't start: "Database migrations missing"

**Error**: `Database migrations missing: 002_add_scheduling_and_priority. Run scripts/apply_migrations.sh`

**Solution**: Run migrations before starting app:
```bash
./scripts/apply_migrations.sh
```

### App won't start: "Database schema not initialized"

**Error**: `Database schema not initialized. Run migrations...`

**Solution**: The `schema_migrations` table doesn't exist. Run all migrations:
```bash
./scripts/apply_migrations.sh
```

### Migration fails: Already applied

This is expected! All migrations are idempotent. The script will show:
```
Checking 001_initial_schema... ✓ already applied
```

### Need to force re-apply a migration

Don't delete from `schema_migrations` unless you know what you're doing. Instead:

1. Create a new migration (e.g., `006_fix_previous_migration.sql`)
2. Apply the fix as a new migration
