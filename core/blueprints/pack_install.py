"""Blueprint implementations for pack installation"""
import uuid
from typing import Dict, Any
from datetime import datetime
from sqlalchemy import text

from core import models
from core.blueprints.registry import register_blueprint
from core.blueprints.runner import RunContext
from core.exceptions import (
    PackAlreadyInstalledError,
    PackInstallationInProgressError,
    PackInstallationFailedError,
    PackInstallationInvariantError,
    PackInstallationConflictError
)
from core.advisory_locks import advisory_lock_context, AdvisoryLockUnavailableError


@register_blueprint("core.pack.system.install@v1")
async def system_install_pack(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """System-level pack installation - creates schema and tables.

    Inputs:
        pack_ref: Pack reference (e.g., 'core.domain@v1')
        schema_name: Target schema name

    Outputs:
        schema_name: Created schema name
        tables_created: List of table names created
    """
    pack_ref = inputs["pack_ref"]
    schema_name = inputs["schema_name"]

    # Fetch pack from registry
    with ctx.step("Fetch pack from registry", kind="action_task") as step:
        ctx.emit_progress(f"Looking up pack {pack_ref}")
        pack = ctx.db.query(models.Pack).filter(
            models.Pack.pack_ref == pack_ref
        ).first()

        if not pack:
            raise ValueError(f"Pack not found: {pack_ref}")

        step.outputs = {"pack_id": str(pack.id), "pack_name": pack.name}
        ctx.db.commit()

    # Create schema
    with ctx.step("Create database schema", kind="action_task") as step:
        ctx.emit_progress(f"Creating schema {schema_name}")
        ctx.db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
        ctx.db.commit()
        step.outputs = {"schema_name": schema_name}

    # Create tables from manifest
    tables_created = []
    manifest = pack.manifest

    if "tables" in manifest:
        for table_def in manifest["tables"]:
            table_name = table_def["name"]

            with ctx.step(f"Create table {table_name}", kind="action_task") as step:
                ctx.emit_progress(f"Creating table {schema_name}.{table_name}")

                # Build CREATE TABLE statement
                columns = []
                for col in table_def["columns"]:
                    col_def = f"{col['name']} {col['type']}"

                    if col.get("primary_key"):
                        col_def += " PRIMARY KEY"
                    if col.get("nullable") is False:
                        col_def += " NOT NULL"
                    if col.get("unique"):
                        col_def += " UNIQUE"

                    columns.append(col_def)

                # Add foreign keys
                for col in table_def["columns"]:
                    if col.get("foreign_key"):
                        fk_table = col["foreign_key"].split(".")[0]
                        fk_column = col["foreign_key"].split(".")[1]
                        columns.append(
                            f"FOREIGN KEY ({col['name']}) REFERENCES {schema_name}.{fk_table}({fk_column})"
                        )

                create_sql = f"""
                    CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} (
                        {', '.join(columns)}
                    )
                """

                ctx.db.execute(text(create_sql))
                ctx.db.commit()

                tables_created.append(table_name)
                step.outputs = {"table_name": table_name, "column_count": len(table_def["columns"])}

    return {
        "schema_name": schema_name,
        "tables_created": tables_created,
        "table_count": len(tables_created)
    }


@register_blueprint("core.migrations.apply@v1")
async def apply_migrations(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Apply migrations for a pack.

    Inputs:
        pack_ref: Pack reference
        schema_name: Target schema name
        migrations: List of migration definitions

    Outputs:
        migrations_applied: List of migration IDs applied
    """
    pack_ref = inputs["pack_ref"]
    schema_name = inputs["schema_name"]
    migrations = inputs.get("migrations", [])

    migrations_applied = []

    if not migrations:
        with ctx.step("Check migrations", kind="action_task") as step:
            ctx.emit_progress("No migrations to apply")
            step.outputs = {"message": "No migrations defined"}
        return {"migrations_applied": []}

    for migration in migrations:
        migration_id = migration["id"]

        with ctx.step(f"Apply migration {migration_id}", kind="action_task") as step:
            ctx.emit_progress(f"Applying migration {migration_id} to {schema_name}")

            # Execute migration SQL
            sql = migration.get("sql", "")
            if sql:
                ctx.db.execute(text(sql))
                ctx.db.commit()

            migrations_applied.append(migration_id)
            step.outputs = {"migration_id": migration_id}

    return {
        "migrations_applied": migrations_applied,
        "migration_count": len(migrations_applied)
    }


@register_blueprint("core.pack.install@v1")
async def install_pack(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Install a pack - orchestrates system installation and migration.

    Inputs:
        pack_ref: Pack reference (e.g., 'core.domain@v1')
        env_id: Environment ID (default: 'local-dev')

    Outputs:
        pack_id: Installed pack ID
        installation_id: Installation record ID
        schema_name: Created schema name
    """
    from core.blueprints.runner import run_blueprint

    pack_ref = inputs["pack_ref"]
    env_id = inputs.get("env_id", "local-dev")

    # Advisory lock to prevent concurrent installations of same pack/env
    # This prevents wasted work even if multiple runs are queued
    lock_key = f"pack.install:{env_id}:{pack_ref}"

    try:
        with advisory_lock_context(ctx.db, lock_key, fail_fast=True):
            return await _install_pack_locked(ctx, pack_ref, env_id)
    except AdvisoryLockUnavailableError:
        # Another run is already installing this pack
        raise PackInstallationInProgressError(
            pack_ref=pack_ref,
            env_id=env_id,
            installation_id=None,  # We don't know the ID without querying
            installing_by_run_id=None
        )


async def _install_pack_locked(ctx: RunContext, pack_ref: str, env_id: str) -> Dict[str, Any]:
    """Internal installation logic with advisory lock held."""
    from core.blueprints.runner import run_blueprint

    # Fetch pack
    with ctx.step("Validate pack", kind="action_task") as step:
        ctx.emit_progress(f"Validating pack {pack_ref}")
        pack = ctx.db.query(models.Pack).filter(
            models.Pack.pack_ref == pack_ref
        ).first()

        if not pack:
            raise ValueError(f"Pack not found: {pack_ref}")

        step.outputs = {
            "pack_id": str(pack.id),
            "schema_name": pack.schema_name
        }

    schema_name = pack.schema_name

    # Create installation record
    # Use INSERT ON CONFLICT for atomic duplicate prevention
    with ctx.step("Create installation record", kind="action_task") as step:
        from sqlalchemy.dialects.postgresql import insert

        installation_id = uuid.uuid4()

        # Attempt atomic insert with ON CONFLICT handling
        # Set installed_by_run_id at claim time
        stmt = insert(models.PackInstallation).values(
            id=installation_id,
            pack_id=pack.id,
            pack_ref=pack_ref,
            env_id=env_id,
            status=models.PackStatus.INSTALLING,
            schema_mode="per_pack",
            schema_name=schema_name,
            migration_provider="sql",
            installed_by_run_id=ctx.run.id,  # Claim at insert time
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ).on_conflict_do_nothing(
            constraint="uq_pack_installations_env_pack"
        ).returning(models.PackInstallation)

        result = ctx.db.execute(stmt)
        installation = result.fetchone()
        ctx.db.commit()

        # Check if insert succeeded
        if installation is None:
            # Conflict detected - fetch existing and branch on status
            existing = ctx.db.query(models.PackInstallation).filter(
                models.PackInstallation.pack_ref == pack_ref,
                models.PackInstallation.env_id == env_id
            ).first()

            if existing:
                if existing.status == models.PackStatus.INSTALLED:
                    raise PackAlreadyInstalledError(
                        pack_ref=pack_ref,
                        env_id=env_id,
                        installation_id=existing.id,
                        installed_by_run_id=existing.installed_by_run_id
                    )
                elif existing.status == models.PackStatus.INSTALLING:
                    raise PackInstallationInProgressError(
                        pack_ref=pack_ref,
                        env_id=env_id,
                        installation_id=existing.id,
                        installing_by_run_id=existing.installed_by_run_id
                    )
                elif existing.status == models.PackStatus.FAILED:
                    raise PackInstallationFailedError(
                        pack_ref=pack_ref,
                        env_id=env_id,
                        installation_id=existing.id,
                        error_details=existing.error,
                        last_error_at=existing.last_error_at
                    )
                else:
                    # Other status (UPGRADING, etc.)
                    raise PackInstallationInProgressError(
                        pack_ref=pack_ref,
                        env_id=env_id,
                        installation_id=existing.id,
                        installing_by_run_id=existing.updated_by_run_id or existing.installed_by_run_id
                    )

        # Convert Row to ORM model instance (no lock needed - row is claimed)
        installation = ctx.db.query(models.PackInstallation).filter(
            models.PackInstallation.id == installation_id
        ).first()

        step.outputs = {
            "installation_id": str(installation.id),
            "schema_mode": installation.schema_mode,
            "claimed_by_run_id": str(installation.installed_by_run_id)
        }

    # Run system installation
    with ctx.step("Execute system installation", kind="agent_task") as step:
        ctx.emit_progress("Running core.pack.system.install@v1")

        system_run = await run_blueprint(
            "core.pack.system.install@v1",
            {
                "pack_ref": pack_ref,
                "schema_name": schema_name
            },
            ctx.db,
            actor=ctx.run.actor,
            correlation_id=ctx.correlation_id
        )

        step.outputs = {
            "system_run_id": str(system_run.id),
            "tables_created": system_run.outputs.get("tables_created", [])
        }

    # Apply migrations if any
    migrations = pack.manifest.get("migrations", [])
    latest_migration_id = None

    if migrations:
        with ctx.step("Execute migrations", kind="agent_task") as step:
            ctx.emit_progress(f"Running core.migrations.apply@v1 ({len(migrations)} migrations)")

            migration_run = await run_blueprint(
                "core.migrations.apply@v1",
                {
                    "pack_ref": pack_ref,
                    "schema_name": schema_name,
                    "migrations": migrations
                },
                ctx.db,
                actor=ctx.run.actor,
                correlation_id=ctx.correlation_id
            )

            migrations_applied = migration_run.outputs.get("migrations_applied", [])
            if migrations_applied:
                latest_migration_id = migrations_applied[-1]

            step.outputs = {
                "migration_run_id": str(migration_run.id),
                "migrations_applied": migrations_applied,
                "latest_migration_id": latest_migration_id
            }

    # Mark installation as complete
    # Enforce invariants: when status=INSTALLED, require version, schema_name, installed_at
    # Lock the row during state transition to prevent concurrent finalizers
    with ctx.step("Finalize installation", kind="action_task") as step:
        ctx.emit_progress("Locking installation record for finalization")

        # CRITICAL: Re-load and lock the row for exclusive access during state transition
        # Do NOT trust the old in-memory `installation` object for concurrency control
        locked = (
            ctx.db.query(models.PackInstallation)
            .filter(models.PackInstallation.id == installation.id)
            .with_for_update()  # Blocks concurrent finalizers
            .one()
        )

        # Idempotency: if already installed, return current state
        if locked.status == models.PackStatus.INSTALLED:
            ctx.emit_progress("Installation already finalized, returning current state")
            step.outputs = {
                "status": "installed",
                "version": locked.installed_version,
                "migration_state": locked.migration_state,
                "installed_by_run_id": str(locked.installed_by_run_id),
                "schema_name": locked.schema_name,
                "idempotent": True
            }
        else:
            # Safety: only the claiming run can finalize
            if locked.installed_by_run_id != ctx.run.id:
                raise PackInstallationConflictError(
                    f"Installation is owned by run {locked.installed_by_run_id}, not {ctx.run.id}",
                    expected_run_id=ctx.run.id,
                    actual_run_id=locked.installed_by_run_id
                )

            # Verify status is INSTALLING (the only valid state to finalize from)
            if locked.status != models.PackStatus.INSTALLING:
                raise PackInstallationConflictError(
                    f"Cannot finalize from status={locked.status.value}. Expected INSTALLING."
                )

            # Enforce invariants before finalizing (check fresh locked row)
            if not locked.schema_name:
                raise PackInstallationInvariantError(
                    "schema_name must be set before marking as installed",
                    field="schema_name"
                )

            if not pack.version:
                raise PackInstallationInvariantError(
                    "pack.version must be set before marking as installed",
                    field="version"
                )

            # Transition to INSTALLED (mutate locked row)
            locked.status = models.PackStatus.INSTALLED
            locked.installed_version = pack.version
            locked.migration_state = latest_migration_id or "init"
            locked.installed_at = datetime.utcnow()
            locked.error = None  # Clear any previous errors
            locked.updated_at = datetime.utcnow()

            ctx.db.commit()

            step.outputs = {
                "status": "installed",
                "version": locked.installed_version,
                "migration_state": locked.migration_state,
                "installed_by_run_id": str(locked.installed_by_run_id),
                "schema_name": locked.schema_name,
                "idempotent": False
            }

    return {
        "pack_id": str(pack.id),
        "installation_id": str(installation.id),
        "schema_name": schema_name,
        "version": pack.version
    }
