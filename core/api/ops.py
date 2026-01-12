"""Operational/monitoring endpoints for queue and worker health"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from core.database import get_db
from core import models

router = APIRouter()


@router.get("/ops/queue")
async def get_queue_status(db: Session = Depends(get_db)):
    """Get queue health metrics.

    Returns:
        Queue status including counts by status, oldest queued age, expired leases
    """
    # Count by status
    status_counts = db.query(
        models.Run.status,
        func.count(models.Run.id).label('count')
    ).group_by(models.Run.status).all()

    status_map = {status.value: count for status, count in status_counts}

    # Oldest queued run
    oldest_queued = db.query(models.Run).filter(
        models.Run.status == models.RunStatus.QUEUED
    ).order_by(models.Run.queued_at.asc()).first()

    oldest_queued_age_seconds = None
    if oldest_queued and oldest_queued.queued_at:
        oldest_queued_age_seconds = (datetime.utcnow() - oldest_queued.queued_at).total_seconds()

    # Expired leases (runs with status=RUNNING but lease_expires_at in past)
    expired_lease_count = db.query(func.count(models.Run.id)).filter(
        and_(
            models.Run.status == models.RunStatus.RUNNING,
            models.Run.lease_expires_at < datetime.utcnow()
        )
    ).scalar()

    # Long-running (>5 min)
    long_running_threshold = datetime.utcnow() - timedelta(minutes=5)
    long_running_count = db.query(func.count(models.Run.id)).filter(
        and_(
            models.Run.status == models.RunStatus.RUNNING,
            models.Run.started_at < long_running_threshold
        )
    ).scalar()

    return {
        "queued_count": status_map.get("queued", 0),
        "running_count": status_map.get("running", 0),
        "completed_count": status_map.get("completed", 0),
        "failed_count": status_map.get("failed", 0),
        "cancelled_count": status_map.get("cancelled", 0),
        "oldest_queued_age_seconds": oldest_queued_age_seconds,
        "expired_lease_count": expired_lease_count,
        "long_running_count": long_running_count,
        "status_counts": status_map
    }


@router.get("/ops/workers")
async def get_worker_status(
    lookback_minutes: int = Query(5, ge=1, le=60),
    db: Session = Depends(get_db)
):
    """Get worker health metrics.

    Args:
        lookback_minutes: How far back to look for active workers (default 5 min)

    Returns:
        Worker status including active workers and their last seen times
    """
    lookback_threshold = datetime.utcnow() - timedelta(minutes=lookback_minutes)

    # Active workers (distinct locked_by values from recent runs)
    active_workers = db.query(
        models.Run.locked_by,
        func.max(models.Run.locked_at).label('last_seen_at'),
        func.count(models.Run.id).label('runs_claimed')
    ).filter(
        and_(
            models.Run.locked_by.isnot(None),
            models.Run.locked_at >= lookback_threshold
        )
    ).group_by(models.Run.locked_by).all()

    workers = []
    for worker_id, last_seen, runs_claimed in active_workers:
        age_seconds = (datetime.utcnow() - last_seen).total_seconds() if last_seen else None
        workers.append({
            "worker_id": worker_id,
            "last_seen_at": last_seen.isoformat() if last_seen else None,
            "last_seen_age_seconds": age_seconds,
            "runs_claimed": runs_claimed,
            "status": "active" if age_seconds and age_seconds < 120 else "stale"
        })

    # Currently running runs per worker
    running_by_worker = db.query(
        models.Run.locked_by,
        func.count(models.Run.id).label('running_count')
    ).filter(
        models.Run.status == models.RunStatus.RUNNING
    ).group_by(models.Run.locked_by).all()

    running_map = {worker_id: count for worker_id, count in running_by_worker if worker_id}

    # Add current running count to each worker
    for worker in workers:
        worker["current_running"] = running_map.get(worker["worker_id"], 0)

    return {
        "active_worker_count": len([w for w in workers if w["status"] == "active"]),
        "stale_worker_count": len([w for w in workers if w["status"] == "stale"]),
        "workers": workers,
        "lookback_minutes": lookback_minutes
    }


@router.get("/ops/stuck-runs")
async def get_stuck_runs(
    older_than_minutes: int = Query(10, ge=1, le=1440),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get runs that may be stuck (running too long).

    Args:
        older_than_minutes: Consider runs stuck if running longer than this
        limit: Maximum number of results

    Returns:
        List of potentially stuck runs
    """
    threshold = datetime.utcnow() - timedelta(minutes=older_than_minutes)

    stuck_runs = db.query(models.Run).filter(
        and_(
            models.Run.status == models.RunStatus.RUNNING,
            models.Run.started_at < threshold
        )
    ).order_by(models.Run.started_at.asc()).limit(limit).all()

    results = []
    for run in stuck_runs:
        age_seconds = (datetime.utcnow() - run.started_at).total_seconds() if run.started_at else None
        lease_expired = run.lease_expires_at and run.lease_expires_at < datetime.utcnow()

        results.append({
            "run_id": str(run.id),
            "name": run.name,
            "status": run.status.value,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "running_seconds": age_seconds,
            "locked_by": run.locked_by,
            "lease_expires_at": run.lease_expires_at.isoformat() if run.lease_expires_at else None,
            "lease_expired": lease_expired,
            "correlation_id": run.correlation_id
        })

    return {
        "stuck_run_count": len(results),
        "older_than_minutes": older_than_minutes,
        "runs": results
    }
