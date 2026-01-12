"""
Blueprint: core.migrations.apply@v1
Apply pending SQL migrations from scripts/migrations/ directory.

Uses:
- schema_migrations ledger for tracking
- PostgreSQL advisory locks for concurrency safety
- Idempotent SQL (IF NOT EXISTS, ON CONFLICT DO NOTHING)
- psycopg2 DBAPI cursor for multi-statement execution
"""
import os
import glob
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.blueprints.registry import register_blueprint
from core.blueprints.runner import RunContext

# Advisory lock key for core migrations (stable int32 pair as single int64)
LOCK_KEY = 701001


def _list_migration_files(directory: str) -> List[str]:
    """List all .sql migration files in sorted order."""
    paths = glob.glob(os.path.join(directory, "*.sql"))
    return sorted(paths)


def _migration_id(path: str) -> str:
    """Extract migration ID from file path (e.g., '001_initial_schema')."""
    base = os.path.basename(path)
    if not base.endswith(".sql"):
        raise ValueError(f"Not a .sql file: {path}")
    return base[:-4]


def _read_file(path: str) -> str:
    """Read SQL file contents."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _exec_sql_file_psycopg2(db: Session, sql: str) -> None:
    """Execute a migration SQL file that may contain multiple statements.

    Uses psycopg2 DBAPI cursor to allow: BEGIN; ...; COMMIT; in one call.

    IMPORTANT: Commits/rollbacks at DBAPI level (raw_conn), not SQLAlchemy level,
    because we're bypassing SQLAlchemy's unit-of-work.
    """
    # SQLAlchemy Connection (wraps the DBAPI connection)
    sa_conn = db.connection()

    # Get psycopg2 connection + cursor
    raw_conn = sa_conn.connection
    cur = raw_conn.cursor()
    try:
        cur.execute(sql)
        # If the SQL file contains BEGIN/COMMIT, it controls the transaction.
        # If it does not, it runs in the connection's current transaction.
        # In either case, we commit at the DBAPI level to persist.
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        cur.close()


def _ledger_exists(db: Session) -> bool:
    """Check if schema_migrations table exists."""
    row = db.execute(text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name='schema_migrations'
    """)).fetchone()
    return bool(row)


@register_blueprint("core.migrations.apply@v1")
async def core_migrations_apply_v1(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Apply pending migrations from scripts/migrations/ directory.

    Inputs:
        directory: Migration directory (default: "scripts/migrations")
        dry_run: If true, show what would be applied without applying (default: false)
        force: If true, re-apply even if already in ledger (default: false)
        require: List of migration IDs that must exist after run (default: [])

    Outputs:
        applied: List of migration IDs that were applied
        skipped: List of migration IDs that were already applied
        missing_required: List of required migration IDs that are missing
        latest: Most recent migration ID
        dry_run: Whether this was a dry run
    """
    directory = inputs.get("directory", "scripts/migrations")
    dry_run = bool(inputs.get("dry_run", False))
    force = bool(inputs.get("force", False))
    require: List[str] = inputs.get("require", [])

    applied: List[str] = []
    skipped: List[str] = []

    # 1) Acquire advisory lock (single migrator)
    with ctx.step("Acquire migrations lock", kind="gate") as step:
        ctx.assert_ownership()
        ctx.db.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
        ctx.db.commit()
        step.outputs = {"lock_key": LOCK_KEY}
        ctx.emit_progress(f"Acquired advisory lock {LOCK_KEY}")

    try:
        # 2) Ensure ledger exists (apply 000 if missing)
        with ctx.step("Ensure migration ledger exists", kind="action_task") as step:
            if not _ledger_exists(ctx.db):
                path = os.path.join(directory, "000_migrations_ledger.sql")
                sql = _read_file(path)
                if dry_run:
                    step.outputs = {"created": False, "note": "dry_run"}
                else:
                    _exec_sql_file_psycopg2(ctx.db, sql)
                    step.outputs = {"created": True, "path": path}
            else:
                step.outputs = {"created": False}
            ctx.emit_progress("Migration ledger verified")

        # 3) Load applied IDs
        with ctx.step("Load applied migrations", kind="action_task") as step:
            rows = ctx.db.execute(text("SELECT id FROM schema_migrations")).fetchall()
            applied_ids = {r[0] for r in rows}
            step.outputs = {"applied_count": len(applied_ids)}
            ctx.emit_progress(f"Current ledger has {len(applied_ids)} applied migrations")

        # 4) Apply missing migrations
        files = _list_migration_files(directory)

        for idx, path in enumerate(files, start=1):
            mig_id = _migration_id(path)

            # Skip 000 if ledger just created and already recorded itself
            if not force and mig_id in applied_ids:
                skipped.append(mig_id)
                continue

            if dry_run:
                applied.append(mig_id)
                continue

            with ctx.step(f"Apply {mig_id}", kind="action_task") as step:
                ctx.assert_ownership()

                sql = _read_file(path)

                # Execute the file (multi-statement safe, commits at DBAPI level)
                _exec_sql_file_psycopg2(ctx.db, sql)

                # Verify it recorded itself in ledger
                ok = ctx.db.execute(
                    text("SELECT 1 FROM schema_migrations WHERE id = :id"),
                    {"id": mig_id},
                ).fetchone()
                if not ok:
                    raise RuntimeError(
                        f"Migration {mig_id} did not insert itself into schema_migrations. "
                        "All migrations must record themselves in the ledger."
                    )

                applied_ids.add(mig_id)
                applied.append(mig_id)
                step.outputs = {"id": mig_id, "path": path, "seq": idx}
                ctx.emit_progress(f"✓ Applied {mig_id}")

        # 5) Required check
        missing_required = [m for m in require if m not in applied_ids]
        if missing_required:
            raise RuntimeError(
                f"Missing required migrations: {', '.join(missing_required)}. "
                "These migrations must be applied before continuing."
            )

        # Determine latest migration
        latest = None
        if applied:
            latest = applied[-1]
        elif applied_ids:
            latest = sorted(applied_ids)[-1]

        return {
            "applied": applied,
            "skipped": skipped,
            "missing_required": [],
            "latest": latest,
            "dry_run": dry_run,
            "summary": f"Applied {len(applied)}, skipped {len(skipped)}"
        }

    finally:
        # Always release lock (best effort)
        try:
            ctx.db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            ctx.db.commit()
        except Exception:
            ctx.db.rollback()
