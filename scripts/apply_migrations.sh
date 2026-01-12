#!/bin/bash
# Apply SQL migrations from scripts/migrations/ in order
# Uses schema_migrations ledger for tracking

set -euo pipefail

cd "$(dirname "$0")/.."

# Determine how to run psql
USE_DOCKER=0
if command -v psql >/dev/null 2>&1; then
  # Local psql
  DATABASE_URL="${DATABASE_URL:-postgresql://xyn:xyn_dev_password@localhost:5432/xyn}"
  PSQL=(psql "$DATABASE_URL" -v ON_ERROR_STOP=1)
  TARGET_DESC="$DATABASE_URL"
else
  # Docker fallback
  USE_DOCKER=1
  PSQL=(docker exec -i xyn-postgres psql -U xyn -d xyn -v ON_ERROR_STOP=1)
  TARGET_DESC="(via Docker: xyn-postgres)"
fi

echo "Applying migrations to: ${TARGET_DESC}"
echo

# Helper function to execute SQL file
execute_sql_file() {
  local file="$1"
  if [[ $USE_DOCKER -eq 1 ]]; then
    # Docker: pipe file content to stdin
    cat "$file" | "${PSQL[@]}"
  else
    # Local: use -f flag
    "${PSQL[@]}" -f "$file"
  fi
}

# Ensure ledger exists before proceeding (helps first-run clarity)
if ! "${PSQL[@]}" -tAc "SELECT 1 FROM information_schema.tables WHERE table_name='schema_migrations';" | grep -q 1; then
  echo "schema_migrations table not found. Applying 000_migrations_ledger.sql first..."
  execute_sql_file "scripts/migrations/000_migrations_ledger.sql"
fi

# Iterate migrations in sorted order (critical for numeric sorting)
mapfile -t MIGRATIONS < <(ls -1 scripts/migrations/*.sql | sort)

for migration in "${MIGRATIONS[@]}"; do
  filename="$(basename "$migration")"
  migration_id="${filename%.sql}"

  echo -n "Checking ${migration_id}... "

  already_applied="$("${PSQL[@]}" -tAc "SELECT COUNT(*) FROM schema_migrations WHERE id = '$migration_id';" | tr -d '[:space:]' || echo "0")"

  if [[ "${already_applied}" != "0" ]]; then
    echo "✓ already applied"
    continue
  fi

  echo "applying..."
  execute_sql_file "$migration"

  # Verify migration recorded itself in ledger
  applied_now="$("${PSQL[@]}" -tAc "SELECT COUNT(*) FROM schema_migrations WHERE id = '$migration_id';" | tr -d '[:space:]')"
  if [[ "$applied_now" == "0" ]]; then
    echo "ERROR: Migration ${migration_id} did not record itself in schema_migrations."
    exit 1
  fi

  echo "  ✓ applied successfully"
done

echo
echo "Migration ledger:"
"${PSQL[@]}" -c "SELECT id, applied_at FROM schema_migrations ORDER BY id;"
