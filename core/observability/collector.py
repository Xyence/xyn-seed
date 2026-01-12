"""Metrics collector for Xyn runtime observability.

Periodically updates Prometheus gauges from DB without interfering with workers.

Design:
- Ephemeral SQLAlchemy session per tick (like lease renewal pattern)
- Cheap, indexed queries only
- No high-cardinality labels
"""
import asyncio
import logging
from sqlalchemy import text

from core.database import SessionLocal
from core.observability.metrics import (
    queue_depth,
    queue_ready_depth,
    queue_future_depth,
    queue_oldest_ready_seconds,
    running_with_expired_lease,
    running_with_active_lease,
)

logger = logging.getLogger(__name__)


async def metrics_collector_loop(interval_seconds: int = 5):
    """Periodic DB-backed metrics collection.

    Uses an ephemeral SQLAlchemy session per tick to avoid session conflicts.

    Args:
        interval_seconds: Time between collection ticks (default 5s)
    """
    logger.info(f"Starting metrics collector (interval={interval_seconds}s)")

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            _collect_once()
        except Exception as e:
            logger.exception(f"Metrics collector failed: {e}")


def _collect_once():
    """Execute all metrics queries in a single ephemeral session.

    All queries use indexed columns and avoid high-cardinality labels.
    """
    db = SessionLocal()
    try:
        # 1) Queue depth by status
        # Uses: ix_runs_status
        rows = db.execute(text("""
            SELECT status::text, COUNT(*)::bigint
            FROM runs
            GROUP BY status
        """)).fetchall()

        # Update gauges for each status
        for status, count in rows:
            queue_depth.labels(status=status).set(int(count))

        # 2) Ready vs future queued runs
        # Uses: ix_runs_status, ix_runs_run_at
        row = db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE status='QUEUED'::runstatus AND run_at <= NOW()) AS ready,
              COUNT(*) FILTER (WHERE status='QUEUED'::runstatus AND run_at > NOW()) AS future
            FROM runs
        """)).fetchone()
        queue_ready_depth.set(int(row.ready))
        queue_future_depth.set(int(row.future))

        # 3) Oldest ready run age
        # Uses: ix_runs_status, ix_runs_run_at, ix_runs_queued_at
        row = db.execute(text("""
            SELECT EXTRACT(EPOCH FROM (NOW() - MIN(queued_at)))::double precision AS age_seconds
            FROM runs
            WHERE status='QUEUED'::runstatus AND run_at <= NOW()
        """)).fetchone()
        queue_oldest_ready_seconds.set(float(row.age_seconds) if row.age_seconds is not None else 0.0)

        # 4) Lease health (expired vs active)
        # Uses: ix_runs_status, ix_runs_lease_expires_at
        row = db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE lease_expires_at < NOW()) AS expired,
              COUNT(*) FILTER (WHERE lease_expires_at >= NOW()) AS active
            FROM runs
            WHERE status='RUNNING'::runstatus AND lease_expires_at IS NOT NULL
        """)).fetchone()
        running_with_expired_lease.set(int(row.expired))
        running_with_active_lease.set(int(row.active))

        db.commit()
    finally:
        db.close()
