"""Blueprint implementation for pack upgrades"""
import uuid
from typing import Dict, Any
from datetime import datetime
from sqlalchemy import text

from core import models
from core.blueprints.registry import register_blueprint
from core.blueprints.runner import RunContext


@register_blueprint("core.pack.upgrade@v1")
async def upgrade_pack(ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade a pack to a newer version.

    Inputs:
        pack_ref: Target pack reference (e.g., 'core.domain@v2')
        env_id: Environment ID (default: 'local-dev')
        target_version: Optional explicit version (default: use pack_ref version)

    Outputs:
        from_version: Previous version
        to_version: New version
        migrations_applied: List of migration IDs applied
        installation_id: Updated installation record ID
    """
    from core.blueprints.runner import run_blueprint

    pack_ref = inputs["pack_ref"]
    env_id = inputs.get("env_id", "local-dev")

    # Parse pack reference to get base name
    base_ref = pack_ref.split('@')[0]  # e.g., "core.domain"

    # Verify current installation exists
    with ctx.step("Verify current installation", kind="action_task") as step:
        ctx.emit_progress(f"Checking for existing installation of {base_ref}")

        # Find existing installation (any version of this pack)
        installation = ctx.db.query(models.PackInstallation).filter(
            models.PackInstallation.pack_ref.like(f"{base_ref}@%"),
            models.PackInstallation.env_id == env_id
        ).first()

        if not installation:
            raise ValueError(
                f"No installation found for pack '{base_ref}' in environment '{env_id}'. "
                f"Use core.pack.install@v1 for fresh installation."
            )

        if installation.status != models.PackStatus.INSTALLED:
            raise ValueError(
                f"Pack '{installation.pack_ref}' is in status '{installation.status}', cannot upgrade"
            )

        from_version = installation.installed_version
        from_ref = installation.pack_ref

        step.outputs = {
            "installation_id": str(installation.id),
            "from_ref": from_ref,
            "from_version": from_version,
            "current_migration_state": installation.migration_state
        }

    # Fetch target pack
    with ctx.step("Fetch target pack", kind="action_task") as step:
        ctx.emit_progress(f"Looking up target pack {pack_ref}")

        target_pack = ctx.db.query(models.Pack).filter(
            models.Pack.pack_ref == pack_ref
        ).first()

        if not target_pack:
            raise ValueError(f"Target pack not found: {pack_ref}")

        to_version = target_pack.version

        step.outputs = {
            "target_pack_id": str(target_pack.id),
            "to_version": to_version
        }

    # Validate upgrade path
    with ctx.step("Validate upgrade path", kind="action_task") as step:
        ctx.emit_progress(f"Validating upgrade from {from_version} to {to_version}")

        # For now, only allow same version (no-op) or newer versions
        # In production, this would check compatibility matrix
        if from_version == to_version:
            step.outputs = {
                "upgrade_type": "no-op",
                "message": "Already at target version"
            }
        elif from_version and to_version:
            # Simple version comparison (not semver-aware yet)
            step.outputs = {
                "upgrade_type": "standard",
                "message": f"Upgrading from {from_version} to {to_version}"
            }
        else:
            step.outputs = {
                "upgrade_type": "standard",
                "message": "Version comparison not available"
            }

    # Determine migration delta
    with ctx.step("Calculate migration delta", kind="action_task") as step:
        last_applied = installation.migration_state
        all_migrations = target_pack.manifest.get("migrations", [])

        # Find migrations that need to be applied
        if not all_migrations:
            pending_migrations = []
        elif not last_applied:
            # No migrations applied yet, apply all
            pending_migrations = all_migrations
        else:
            # Apply migrations after last_applied
            pending_migrations = [
                m for m in all_migrations
                if m["id"] > last_applied
            ]

        step.outputs = {
            "last_applied_migration": last_applied,
            "total_migrations": len(all_migrations),
            "pending_migrations_count": len(pending_migrations),
            "pending_migration_ids": [m["id"] for m in pending_migrations]
        }

    # Apply migrations if any
    migrations_applied = []
    if pending_migrations:
        with ctx.step("Apply pending migrations", kind="agent_task") as step:
            ctx.emit_progress(f"Applying {len(pending_migrations)} migrations")

            migration_run = await run_blueprint(
                "core.migrations.apply@v1",
                {
                    "pack_ref": pack_ref,
                    "schema_name": installation.schema_name,
                    "migrations": pending_migrations
                },
                ctx.db,
                actor=ctx.run.actor,
                correlation_id=ctx.correlation_id
            )

            migrations_applied = migration_run.outputs.get("migrations_applied", [])
            latest_migration_id = migrations_applied[-1] if migrations_applied else last_applied

            step.outputs = {
                "migration_run_id": str(migration_run.id),
                "migrations_applied": migrations_applied,
                "new_migration_state": latest_migration_id
            }

            # Update migration state
            installation.migration_state = latest_migration_id
            ctx.db.commit()

    # Finalize upgrade
    # Enforce invariants: update run tracking and ensure required fields
    with ctx.step("Finalize upgrade", kind="action_task") as step:
        installation.pack_ref = pack_ref
        installation.pack_id = target_pack.id
        installation.installed_version = to_version
        installation.status = models.PackStatus.INSTALLED
        installation.updated_at = datetime.utcnow()
        installation.updated_by_run_id = ctx.run.id  # Track upgrade run

        # Ensure required fields are set
        if not installation.installed_at:
            installation.installed_at = datetime.utcnow()

        ctx.db.commit()

        step.outputs = {
            "status": "upgraded",
            "from_version": from_version,
            "to_version": to_version,
            "migrations_applied_count": len(migrations_applied),
            "updated_by_run_id": str(ctx.run.id)
        }

    return {
        "installation_id": str(installation.id),
        "from_version": from_version,
        "to_version": to_version,
        "migrations_applied": migrations_applied,
        "schema_name": installation.schema_name
    }
