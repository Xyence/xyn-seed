"""Advisory locks for preventing concurrent work on the same resource.

Uses Postgres advisory locks to gate operations like pack installation
at the (env_id, pack_ref) level. Prevents expensive duplicate work even
when multiple runs are queued or retried.
"""
import hashlib
from contextlib import contextmanager
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


def hash_lock_key(key: str) -> int:
    """Convert string key to int64 for Postgres advisory lock.

    Args:
        key: String key (e.g., "pack.install:local-dev:core.domain@v1")

    Returns:
        Signed 64-bit integer suitable for pg_advisory_lock
    """
    # Use first 8 bytes of SHA256 hash
    hash_bytes = hashlib.sha256(key.encode()).digest()[:8]
    # Convert to signed int64
    lock_id = int.from_bytes(hash_bytes, byteorder='big', signed=False)
    # Convert to signed by subtracting 2^63 if > 2^63-1
    if lock_id >= 2**63:
        lock_id -= 2**64
    return lock_id


def try_advisory_lock(db: Session, key: str) -> bool:
    """Attempt to acquire an advisory lock (non-blocking).

    Args:
        db: Database session
        key: String lock key

    Returns:
        True if lock acquired, False if already held by another session
    """
    lock_id = hash_lock_key(key)
    result = db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id})
    return result.scalar()


def advisory_lock(db: Session, key: str):
    """Acquire an advisory lock (blocking).

    Waits until lock is available.

    Args:
        db: Database session
        key: String lock key
    """
    lock_id = hash_lock_key(key)
    db.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id})


def advisory_unlock(db: Session, key: str) -> bool:
    """Release an advisory lock.

    Args:
        db: Database session
        key: String lock key

    Returns:
        True if lock was held and released, False if not held
    """
    lock_id = hash_lock_key(key)
    result = db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    return result.scalar()


@contextmanager
def advisory_lock_context(db: Session, key: str, fail_fast: bool = True):
    """Context manager for advisory locks.

    Args:
        db: Database session
        key: String lock key
        fail_fast: If True, use try_lock and raise if unavailable.
                   If False, use blocking lock.

    Raises:
        AdvisoryLockUnavailableError: If fail_fast=True and lock unavailable

    Example:
        with advisory_lock_context(db, "pack.install:local-dev:core.domain@v1"):
            # ... do installation work
            pass
    """
    if fail_fast:
        acquired = try_advisory_lock(db, key)
        if not acquired:
            raise AdvisoryLockUnavailableError(f"Advisory lock unavailable: {key}")
    else:
        advisory_lock(db, key)
        acquired = True

    try:
        yield
    finally:
        if acquired:
            advisory_unlock(db, key)


class AdvisoryLockUnavailableError(Exception):
    """Raised when advisory lock cannot be acquired in fail-fast mode."""

    def __init__(self, message: str, lock_key: Optional[str] = None):
        super().__init__(message)
        self.lock_key = lock_key
