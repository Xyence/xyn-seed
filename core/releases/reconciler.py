"""Reconciler loop for long-running releases."""
from __future__ import annotations

import asyncio
import os
import subprocess
import shutil
import time
import uuid
from typing import Dict, Optional

from core.releases import store

_last_action: Dict[str, float] = {}


def _interval_seconds() -> int:
    raw = os.getenv("SHINESEED_RECONCILE_INTERVAL", "30")
    try:
        return int(raw)
    except ValueError:
        return 30


def _should_reconcile(release_id: str, now: float, interval: int) -> bool:
    last = _last_action.get(release_id)
    if last is None:
        return True
    return (now - last) >= interval


def _compose_project_name(runtime_spec: dict) -> str:
    return f"{runtime_spec['metadata']['namespace']}_{runtime_spec['metadata']['name']}"


def _compose_ps(compose_path, runtime_spec) -> Optional[list[dict]]:
    env = {"COMPOSE_PROJECT_NAME": _compose_project_name(runtime_spec), **dict(os.environ)}
    compose_cmd = ["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"]
    result = subprocess.run(
        [*compose_cmd, "-f", str(compose_path), "ps", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(compose_path.parent),
        env=env
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        import json
        return json.loads(result.stdout)
    except Exception:
        return None


def _compose_up(compose_path, runtime_spec) -> tuple[bool, str]:
    env = {"COMPOSE_PROJECT_NAME": _compose_project_name(runtime_spec), **dict(os.environ)}
    compose_cmd = ["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"]
    result = subprocess.run(
        [*compose_cmd, "-f", str(compose_path), "up", "-d"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(compose_path.parent),
        env=env
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "docker compose up failed"
    return True, result.stdout.strip() or "reconcile apply succeeded"


async def reconcile_once() -> None:
    release_ids = store.list_release_ids()
    now = time.monotonic()
    interval = _interval_seconds()
    for release_id in release_ids:
        if interval <= 0:
            return
        if not _should_reconcile(release_id, now, interval):
            continue
        runtime_spec = store.load_latest_runtime(release_id)
        if not runtime_spec:
            continue
        backend_type = runtime_spec["release"]["backend"]["type"]
        if backend_type != "compose":
            continue
        compose_path = store.latest_compose_path(release_id)
        if not compose_path:
            continue
        payload = _compose_ps(compose_path, runtime_spec)
        if not payload:
            continue
        drifted = any(entry.get("State") != "running" for entry in payload)
        if not drifted:
            continue
        ok, message = _compose_up(compose_path, runtime_spec)
        operation_id = str(uuid.uuid4())
        operation = {
            "operationId": operation_id,
            "releaseId": release_id,
            "type": "reconcile",
            "status": "succeeded" if ok else "failed",
            "createdAt": store._now_iso(),
            "startedAt": store._now_iso(),
            "finishedAt": store._now_iso(),
            "planId": None,
            "message": message,
            "artifacts": {}
        }
        store.save_operation(release_id, operation_id, operation)
        _last_action[release_id] = time.monotonic()


async def reconcile_loop() -> None:
    interval = _interval_seconds()
    if interval <= 0:
        return
    while True:
        await reconcile_once()
        await asyncio.sleep(interval)


__all__ = ["reconcile_loop", "reconcile_once"]
