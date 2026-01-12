"""Blueprint runner - executes blueprints with step observability"""
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from contextlib import contextmanager

from core import models
from core.blueprints.registry import get_blueprint

logger = logging.getLogger(__name__)

def enqueue_run(
    blueprint_ref: str,
    inputs: Dict[str, Any],
    db: Session,
    actor: str = "system",
    correlation_id: Optional[str] = None,
    run_at: Optional[datetime] = None,
    priority: int = 100,
    max_attempts: Optional[int] = None,
    commit: bool = True
) -> models.Run:
    """Enqueue a blueprint run for async execution by a worker.

    Args:
        blueprint_ref: Blueprint reference to execute
        inputs: Input parameters for the blueprint
        db: Database session
        actor: Actor enqueuing the run
        correlation_id: Correlation ID for tracking
        run_at: When to run (default: now). For delayed/scheduled runs.
        priority: Priority (lower = higher priority, default: 100)
                  0-9: critical, 10-49: high, 50-100: normal, 200+: background
        max_attempts: Maximum retry attempts (default: None = no retries)
        commit: Whether to commit immediately (default: True)

    Returns:
        Run object with status=QUEUED
    """
    # Generate correlation ID if not provided
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    now = datetime.utcnow()

    # Create run in QUEUED state
    run = models.Run(
        id=uuid.uuid4(),
        name=blueprint_ref,
        status=models.RunStatus.QUEUED,
        actor=actor,
        correlation_id=correlation_id,
        inputs=inputs,
        created_at=now,
        queued_at=now,
        run_at=run_at or now,
        priority=priority,
        attempt=0,
        max_attempts=max_attempts
    )
    db.add(run)
    if commit:
        db.commit()
        db.refresh(run)

    if run_at and run_at > now:
        logger.info(f"Scheduled run {run.id} for blueprint {blueprint_ref} at {run_at} (priority={priority})",
                    extra={'correlation_id': correlation_id})
    else:
        logger.info(f"Enqueued run {run.id} for blueprint {blueprint_ref} (priority={priority})",
                    extra={'correlation_id': correlation_id})

    return run


class RunContext:
    """Context passed to blueprint implementations."""

    def __init__(self, run: models.Run, db: Session, correlation_id: str, worker_id: Optional[str] = None):
        self.run = run
        self.db = db
        self.correlation_id = correlation_id
        self.worker_id = worker_id
        self._current_step: Optional[models.Step] = None

    def assert_ownership(self):
        """Assert that this worker still owns the run.

        Raises:
            LostLeaseError: If worker has lost ownership/lease of the run
        """
        if not self.worker_id:
            # Not running in worker context - skip ownership check
            return

        from sqlalchemy import text
        from core.exceptions import LostLeaseError

        row = self.db.execute(text("""
            SELECT 1
            FROM runs
            WHERE id = :run_id
              AND status = 'RUNNING'::runstatus
              AND locked_by = :worker_id
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at > NOW()
        """), {"run_id": self.run.id, "worker_id": self.worker_id}).fetchone()

        if not row:
            raise LostLeaseError(f"Worker {self.worker_id} lost lease/ownership of run {self.run.id}")

    def emit_event(self, event_name: str, data: Dict[str, Any] = None):
        """Emit an event during execution.

        Uses flush() instead of commit() to avoid performance issues with chatty blueprints.
        Events will be committed at step boundaries or run completion.

        Args:
            event_name: Name of the event
            data: Event data
        """
        # Guard: assert ownership before writing events
        self.assert_ownership()

        # Get env_id from run inputs or fall back to default
        # TODO: Add env_id column to runs table for proper env tracking
        env_id = self.run.inputs.get("env_id", "local-dev") if self.run.inputs else "local-dev"

        event = models.Event(
            id=uuid.uuid4(),
            event_name=event_name,
            occurred_at=datetime.utcnow(),
            env_id=env_id,
            actor=self.run.actor,
            correlation_id=self.correlation_id,
            run_id=self.run.id,
            step_id=self._current_step.id if self._current_step else None,
            data=data or {}
        )
        self.db.add(event)
        # Flush to get event ID and make it visible within transaction
        # Commit happens at step boundaries or run completion
        self.db.flush()
        logger.info(f"Event emitted: {event_name}", extra={'correlation_id': self.correlation_id})

    @contextmanager
    def step(self, name: str, kind: str = "action_task"):
        """Context manager for executing a step.

        Optimized commit cadence: flush at creation, commit at boundaries (start/end).
        Automatically emits step.started, step.completed/failed events.

        Args:
            name: Step name
            kind: Step kind (action_task, agent_task, gate, transform)

        Yields:
            Step object
        """
        from sqlalchemy.exc import IntegrityError

        # Create step with robust idx assignment (handles rare race conditions)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Count existing steps for this run
                step_count = self.db.query(models.Step).filter(
                    models.Step.run_id == self.run.id
                ).count()

                step = models.Step(
                    id=uuid.uuid4(),
                    run_id=self.run.id,
                    name=name,
                    idx=step_count,
                    kind=kind,
                    status=models.StepStatus.CREATED,
                    created_at=datetime.utcnow()
                )
                self.db.add(step)
                self.db.flush()  # Flush to ensure INSERT, but don't commit yet
                break  # Success
            except IntegrityError:
                # Rare: concurrent step creation violated UNIQUE(run_id, idx)
                self.db.rollback()
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Step idx conflict for run {self.run.id}, retrying (attempt {attempt + 1})")
                continue

        # Set as current step
        self._current_step = step

        try:
            # Guard: assert ownership before starting step
            self.assert_ownership()

            # Step start boundary: set RUNNING + emit event + single commit
            step.status = models.StepStatus.RUNNING
            step.started_at = datetime.utcnow()
            self.emit_event("step.started", {
                "step_id": str(step.id),
                "step_name": name,
                "step_kind": kind
            })
            # Single commit: step RUNNING + step.started event
            self.db.commit()

            yield step

            # Guard: assert ownership before completing step
            self.assert_ownership()

            # Step completion boundary: set COMPLETED + emit event + single commit
            step.status = models.StepStatus.COMPLETED
            step.completed_at = datetime.utcnow()
            self.emit_event("step.completed", {
                "step_id": str(step.id),
                "step_name": name
            })
            # Single commit: step COMPLETED + step.completed event
            self.db.commit()

        except Exception as e:
            try:
                # Guard: assert ownership before marking step failed
                self.assert_ownership()

                # Step failure boundary: set FAILED + emit event + single commit
                step.status = models.StepStatus.FAILED
                step.completed_at = datetime.utcnow()
                step.error = {
                    "message": str(e),
                    "type": type(e).__name__
                }
                self.emit_event("step.failed", {
                    "step_id": str(step.id),
                    "step_name": name,
                    "error": str(e)
                })
                # Single commit: step FAILED + step.failed event
                self.db.commit()
            except Exception as fail_error:
                # If we lose ownership while marking failed, log and continue
                from core.exceptions import LostLeaseError
                if isinstance(fail_error, LostLeaseError):
                    logger.warning(f"Lost ownership while marking step {step.id} as failed")
                else:
                    logger.error(f"Error while marking step {step.id} as failed: {fail_error}")
                # Rollback failed commit attempt
                try:
                    self.db.rollback()
                except:
                    pass
            raise
        finally:
            self._current_step = None

    def emit_progress(self, message: str, progress: Optional[float] = None):
        """Emit step progress event.

        Progress events use flush() only - they are committed at the next
        step boundary (completion/failure). For real-time progress visibility,
        consider adding throttled commits (e.g., once per 2s).

        Args:
            message: Progress message
            progress: Optional progress percentage (0.0 to 1.0)
        """
        if not self._current_step:
            logger.warning("No active step for progress emission")
            return

        data = {
            "step_id": str(self._current_step.id),
            "message": message
        }
        if progress is not None:
            data["progress"] = progress

        self.emit_event("step.progress", data)

        # Note: Progress events are flushed but not committed here.
        # They will be committed at the next step boundary.
        # For real-time progress streaming, add throttled commit logic:
        #   if (utcnow() - self._last_progress_commit).total_seconds() > 2:
        #       self.db.commit()
        #       self._last_progress_commit = utcnow()

    def spawn_run(
        self,
        blueprint_ref: str,
        inputs: Dict[str, Any],
        child_key: Optional[str] = None,
        priority: Optional[int] = None,
        run_at: Optional[datetime] = None
    ) -> uuid.UUID:
        """Spawn a child run for DAG execution.

        Race-safe and atomic: creates child run + edge in single transaction.
        Idempotent when child_key is provided - if edge insert conflicts,
        returns existing child_run_id (no orphaned runs).

        Args:
            blueprint_ref: Blueprint to execute
            inputs: Blueprint inputs
            child_key: Idempotency key (e.g., "migrations", "install-domain")
            priority: Optional priority override (inherits parent if None)
            run_at: Optional scheduling (default: now)

        Returns:
            UUID of spawned child run

        Raises:
            Exception: If spawn fails (non-idempotency conflict)
        """
        # Fast path: if already spawned, return existing
        if child_key:
            existing = self.db.query(models.RunEdge).filter(
                models.RunEdge.parent_run_id == self.run.id,
                models.RunEdge.child_key == child_key
            ).first()
            if existing:
                logger.info(f"Child run already spawned with key '{child_key}': {existing.child_run_id}")
                return existing.child_run_id

        # Inherit priority from parent if not specified
        if priority is None:
            priority = self.run.priority

        from sqlalchemy.exc import IntegrityError
        try:
            # Create child run WITHOUT committing (part of parent txn)
            child_run = enqueue_run(
                blueprint_ref=blueprint_ref,
                inputs=inputs,
                db=self.db,
                actor=self.run.actor,
                correlation_id=self.correlation_id,
                run_at=run_at,
                priority=priority,
                commit=False  # Critical: don't commit yet
            )

            # Set parent pointer on child run before commit
            child_run.parent_run_id = self.run.id

            # Create edge
            edge = models.RunEdge(
                id=uuid.uuid4(),
                parent_run_id=self.run.id,
                child_run_id=child_run.id,
                relation="child",
                child_key=child_key,
                created_at=datetime.utcnow()
            )
            self.db.add(edge)

            # Atomic commit: child run + parent_run_id + edge
            # If this fails, entire transaction rolls back (no orphan child run)
            self.db.commit()

        except IntegrityError:
            self.db.rollback()

            # Race: another worker spawned with same child_key first
            if child_key:
                existing = self.db.query(models.RunEdge).filter(
                    models.RunEdge.parent_run_id == self.run.id,
                    models.RunEdge.child_key == child_key
                ).one()
                logger.info(f"Race condition detected - returning existing child run {existing.child_run_id} for key '{child_key}'")
                return existing.child_run_id

            # If no child_key, this shouldn't happen; re-raise
            raise

        # Emit event AFTER successful commit
        self.emit_event("run.spawned", {
            "parent_run_id": str(self.run.id),
            "child_run_id": str(child_run.id),
            "child_key": child_key,
            "blueprint_ref": blueprint_ref,
            "priority": priority
        })

        logger.info(f"Spawned child run {child_run.id} (key='{child_key}') for blueprint {blueprint_ref}")
        return child_run.id

    async def wait_runs(
        self,
        run_ids: List[uuid.UUID],
        policy: str = "all",
        timeout: Optional[float] = None,
        poll_interval: float = 0.5
    ) -> Dict[str, Any]:
        """Wait for child runs to complete.

        Uses fresh session per poll to avoid stale reads. Fail-fast for policy='all'.
        Adaptive backoff with jitter to reduce DB load.

        Args:
            run_ids: List of run IDs to wait for
            policy: 'all' (wait for all to succeed) or 'any' (wait for at least one success)
            timeout: Optional timeout in seconds
            poll_interval: Initial polling interval in seconds (default: 0.5s)

        Returns:
            Dict with status and results:
            {
                "completed": [run_id, ...],
                "failed": [run_id, ...],
                "policy_met": bool
            }

        Raises:
            TimeoutError: If timeout exceeded
            Exception: If policy='all' and any run failed, or policy='any' and all failed
        """
        import asyncio
        import time
        import random
        from core.database import SessionLocal

        start_time = time.time()
        poll = poll_interval

        logger.info(f"Waiting for {len(run_ids)} child runs (policy={policy}, timeout={timeout}s)")

        while True:
            # Assert parent still owns this run (critical for crash recovery safety)
            self.assert_ownership()

            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Timeout waiting for child runs (policy={policy}, timeout={timeout}s)")

            # Query run statuses with fresh session to avoid stale reads
            # Select only (id, status) for efficiency
            with SessionLocal() as db2:
                rows = db2.query(models.Run.id, models.Run.status).filter(
                    models.Run.id.in_(run_ids)
                ).all()

            completed = [rid for rid, st in rows if st == models.RunStatus.COMPLETED]
            failed = [rid for rid, st in rows if st in (models.RunStatus.FAILED, models.RunStatus.CANCELLED)]
            done = len(completed) + len(failed)

            # Policy evaluation
            if policy == "all":
                # Fail fast: abort immediately if any child failed
                if failed:
                    raise Exception(f"{len(failed)} child run(s) failed (fail-fast): {failed}")
                # Success: all completed
                if done == len(run_ids):
                    logger.info(f"All {len(completed)} child runs completed successfully")
                    return {
                        "completed": [str(x) for x in completed],
                        "failed": [],
                        "policy_met": True
                    }

            elif policy == "any":
                # Success: at least one completed
                if completed:
                    logger.info(f"Child run completed (policy=any): {len(completed)} completed, {len(failed)} failed")
                    return {
                        "completed": [str(x) for x in completed],
                        "failed": [str(x) for x in failed],
                        "policy_met": True
                    }
                # Failure: all failed, no successful completions possible
                if len(failed) == len(run_ids):
                    raise Exception(f"All {len(failed)} child runs failed (policy=any): {failed}")

            # Emit progress
            if self._current_step:
                self.emit_progress(
                    f"Waiting for child runs: {done}/{len(run_ids)} done",
                    progress=(done / len(run_ids)) if run_ids else 0.0
                )

            # Adaptive backoff with jitter to reduce DB load
            jitter = random.uniform(0, 0.1)
            await asyncio.sleep(poll + jitter)

            # Increase poll interval after 10s (mild backoff, cap at 2s)
            if (time.time() - start_time) > 10 and poll < 2.0:
                poll = min(2.0, poll * 1.25)


async def execute_run(run_id: uuid.UUID, db: Session, worker_id: Optional[str] = None) -> models.Run:
    """Execute an existing run (worker-only function).

    This is the internal execution primitive used by workers.
    Does NOT create a new run - executes an existing one.

    Args:
        run_id: ID of existing run to execute
        db: Database session
        worker_id: Worker ID for ownership checking (if running in worker)

    Returns:
        Completed run object

    Raises:
        ValueError: If run not found or blueprint not found
        Exception: If blueprint execution fails
        LostLeaseError: If worker loses ownership during execution
    """
    from sqlalchemy import text
    from core.exceptions import LostLeaseError

    # Load existing run
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    # Resolve blueprint
    implementation = get_blueprint(run.name)
    if not implementation:
        raise ValueError(f"Blueprint not found: {run.name}")

    logger.info(f"Executing run {run.id} for blueprint {run.name}",
                extra={'correlation_id': run.correlation_id})

    # Create context with worker_id for ownership checks
    ctx = RunContext(run, db, run.correlation_id, worker_id)

    try:
        # Emit run.started event (guarded if worker_id set)
        ctx.emit_event("run.started", {
            "run_id": str(run.id),
            "blueprint_ref": run.name,
            "inputs": run.inputs
        })

        # Execute blueprint
        outputs = await implementation(ctx, run.inputs)

        # Mark run as completed using CAS update (prevents double-finalization)
        result = db.execute(text("""
            UPDATE runs
            SET status = 'COMPLETED'::runstatus,
                completed_at = NOW(),
                outputs = :outputs
            WHERE id = :run_id
              AND status = 'RUNNING'::runstatus
              AND (:worker_id IS NULL OR locked_by = :worker_id)
              AND (:worker_id IS NULL OR lease_expires_at > NOW())
            RETURNING id
        """), {
            "run_id": run.id,
            "outputs": outputs or {},
            "worker_id": worker_id
        })

        row = result.fetchone()
        db.commit()

        if not row:
            # Lost ownership - another worker may have reclaimed
            raise LostLeaseError(f"Lost ownership when marking run {run.id} as completed")

        # Reload run to get updated state
        db.refresh(run)

        ctx.emit_event("run.completed", {
            "run_id": str(run.id),
            "outputs": outputs
        })

        logger.info(f"Completed run {run.id}", extra={'correlation_id': run.correlation_id})
        return run

    except Exception as e:
        # Rollback any pending changes before marking failed
        db.rollback()

        # Mark run as failed using CAS update (prevents double-finalization)
        import json
        result = db.execute(text("""
            UPDATE runs
            SET status = 'FAILED'::runstatus,
                completed_at = NOW(),
                error = :error::jsonb
            WHERE id = :run_id
              AND status = 'RUNNING'::runstatus
              AND (:worker_id IS NULL OR locked_by = :worker_id)
              AND (:worker_id IS NULL OR lease_expires_at > NOW())
            RETURNING id
        """), {
            "run_id": run.id,
            "error": json.dumps({"message": str(e), "type": type(e).__name__}),
            "worker_id": worker_id
        })

        row = result.fetchone()
        db.commit()

        if row:
            # Successfully marked as failed - reload and emit event
            db.refresh(run)
            ctx.emit_event("run.failed", {
                "run_id": str(run.id),
                "error": str(e)
            })
        else:
            # Lost ownership - don't emit event
            logger.warning(f"Lost ownership when marking run {run.id} as failed")

        logger.error(f"Failed run {run.id}: {e}", extra={'correlation_id': run.correlation_id})
        raise


async def run_blueprint(
    blueprint_ref: str,
    inputs: Dict[str, Any],
    db: Session,
    actor: str = "system",
    correlation_id: Optional[str] = None,
    parent_run_id: Optional[uuid.UUID] = None
) -> models.Run:
    """Execute a blueprint (for nested/child runs).

    Creates a child run with status=RUNNING and executes inline.
    Used for nested blueprint calls within a parent blueprint.

    Args:
        blueprint_ref: Blueprint reference to execute
        inputs: Input parameters for the blueprint
        db: Database session
        actor: Actor executing the run
        correlation_id: Correlation ID for tracking (inherited from parent)
        parent_run_id: Parent run ID (for nested calls)

    Returns:
        Completed run object

    Raises:
        ValueError: If blueprint not found
        Exception: If blueprint execution fails
    """
    # Generate correlation ID if not provided
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    # Create child run with status=RUNNING (no queue bypass for nested calls)
    run = models.Run(
        id=uuid.uuid4(),
        name=blueprint_ref,
        status=models.RunStatus.RUNNING,  # Start as RUNNING (inline execution)
        actor=actor,
        correlation_id=correlation_id,
        inputs=inputs,
        created_at=datetime.utcnow(),
        started_at=datetime.utcnow()  # Set immediately for inline execution
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    logger.info(f"Executing nested run {run.id} for blueprint {blueprint_ref}",
                extra={'correlation_id': correlation_id})

    # Execute using the shared execution logic
    return await execute_run(run.id, db)
