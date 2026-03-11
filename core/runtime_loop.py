"""Background runtime worker loop for Epic C."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from core import models
from core.database import SessionLocal
from core.runtime_execution import process_runtime_cycle
from core.runtime_workers import register_codex_local_worker


logger = logging.getLogger(__name__)


@dataclass
class RuntimeWorkerLoopHandle:
    thread: threading.Thread
    stop_event: threading.Event
    worker_id: str


def _runtime_loop(
    stop_event: threading.Event,
    *,
    worker_id: str,
    poll_interval_seconds: float,
    executor_factory: Optional[Callable[[], object]] = None,
    validation_runner_factory: Optional[Callable[[], object]] = None,
) -> None:
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            worker = register_codex_local_worker(db, worker_id=worker_id)
            if worker.status == models.RuntimeWorkerStatus.OFFLINE:
                db.commit()
                logger.warning("codex_local worker offline worker_id=%s", worker_id)
                stop_event.wait(poll_interval_seconds)
                continue
            process_runtime_cycle(
                db,
                worker_id=worker_id,
                executor=executor_factory() if executor_factory else None,
                validation_runner=validation_runner_factory() if validation_runner_factory else None,
            )
        except Exception:
            db.rollback()
            logger.exception("runtime worker loop iteration failed")
        finally:
            db.close()
        stop_event.wait(poll_interval_seconds)


def start_runtime_worker_loop(
    *,
    worker_id: Optional[str] = None,
    poll_interval_seconds: Optional[float] = None,
    executor_factory: Optional[Callable[[], object]] = None,
    validation_runner_factory: Optional[Callable[[], object]] = None,
) -> RuntimeWorkerLoopHandle:
    resolved_worker_id = worker_id or os.getenv("XYN_RUNTIME_WORKER_ID") or f"codex-local-runtime-{os.getpid()}"
    interval = poll_interval_seconds
    if interval is None:
        interval = float(os.getenv("XYN_RUNTIME_WORKER_POLL_SECONDS", "1.0"))
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_runtime_loop,
        kwargs={
            "stop_event": stop_event,
            "worker_id": resolved_worker_id,
            "poll_interval_seconds": interval,
            "executor_factory": executor_factory,
            "validation_runner_factory": validation_runner_factory,
        },
        daemon=True,
        name="xyn-runtime-worker",
    )
    thread.start()
    return RuntimeWorkerLoopHandle(thread=thread, stop_event=stop_event, worker_id=resolved_worker_id)


def stop_runtime_worker_loop(handle: Optional[RuntimeWorkerLoopHandle]) -> None:
    if handle is None:
        return
    handle.stop_event.set()
    handle.thread.join(timeout=5)
