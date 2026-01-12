#!/usr/bin/env python3
"""
Test script for core.migrations.apply@v1 blueprint.
Tests dry-run and actual migration application.
"""
import sys
from core.database import SessionLocal
from core.blueprints.runner import enqueue_run

def test_migrations_blueprint(dry_run=False, require=None):
    """Enqueue a run to test the migrations blueprint."""
    db = SessionLocal()
    try:
        inputs = {
            "directory": "scripts/migrations",
            "dry_run": dry_run,
            "force": False,
            "require": require or []
        }

        run = enqueue_run(
            blueprint_ref="core.migrations.apply@v1",
            inputs=inputs,
            db=db,
            actor="test-script",
            priority=0  # High priority for testing
        )

        print(f"✓ Enqueued run {run.id}")
        print(f"  Blueprint: {run.name}")
        print(f"  Inputs: {run.inputs}")
        print(f"  Status: {run.status}")
        print()
        print("Worker should pick this up within 2s...")
        print(f"Monitor: docker logs xyn-core -f | grep '{run.id}'")
        print(f"Or query: SELECT * FROM runs WHERE id = '{run.id}'")
        return run.id

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        print("Running DRY-RUN test...\n")
        run_id = test_migrations_blueprint(dry_run=True)
    elif len(sys.argv) > 1 and sys.argv[1] == "--with-require":
        print("Running with REQUIRED MIGRATIONS test...\n")
        run_id = test_migrations_blueprint(
            dry_run=False,
            require=["001_initial_schema", "005_steps_run_idx_constraints"]
        )
    else:
        print("Running NORMAL test...\n")
        run_id = test_migrations_blueprint(dry_run=False)

    print(f"\nRun ID: {run_id}")
