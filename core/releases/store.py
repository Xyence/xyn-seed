"""Filesystem store for release artifacts (plans, revisions, operations)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _workspace_root() -> Path:
    env_path = os.getenv("SHINESEED_WORKSPACE")
    if env_path:
        return Path(env_path)
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "workspace"


def contracts_root() -> Path:
    env_path = os.getenv("SHINESEED_CONTRACTS_ROOT")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[3] / "xyn-contracts"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _release_root(release_id: str) -> Path:
    return _ensure_dir(_workspace_root() / "releases" / release_id)


def release_revisions_dir(release_id: str) -> Path:
    return _ensure_dir(_release_root(release_id) / "revisions")


def release_plans_dir(release_id: str) -> Path:
    return _ensure_dir(_release_root(release_id) / "plans")


def release_operations_dir(release_id: str) -> Path:
    return _ensure_dir(_release_root(release_id) / "operations")


def list_release_ids() -> list[str]:
    releases_root = _workspace_root() / "releases"
    if not releases_root.exists():
        return []
    return sorted([path.name for path in releases_root.iterdir() if path.is_dir()])


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def latest_revision(release_id: str) -> Optional[int]:
    revisions_dir = release_revisions_dir(release_id)
    candidates = []
    for child in revisions_dir.iterdir():
        if child.is_dir() and child.name.isdigit():
            candidates.append(int(child.name))
    return max(candidates) if candidates else None


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def write_text(path: Path, payload: str) -> None:
    path.write_text(payload)


def save_revision_artifacts(
    release_id: str,
    revision: int,
    release_spec: Dict[str, Any],
    runtime_spec: Dict[str, Any],
    compose_yaml: Optional[str]
) -> Dict[str, str]:
    revision_dir = _ensure_dir(release_revisions_dir(release_id) / str(revision))
    release_path = revision_dir / "release.json"
    runtime_path = revision_dir / "runtime.json"
    compose_path = revision_dir / "compose.yaml"

    write_json(release_path, release_spec)
    write_json(runtime_path, runtime_spec)
    if compose_yaml is not None:
        write_text(compose_path, compose_yaml)

    workspace_root = _workspace_root()
    artifacts = {
        "releaseSpecPath": str(release_path.relative_to(workspace_root)),
        "runtimeSpecPath": str(runtime_path.relative_to(workspace_root)),
    }
    if compose_yaml is not None:
        artifacts["composeYamlPath"] = str(compose_path.relative_to(workspace_root))
    return artifacts


def save_plan(
    release_id: str,
    plan_id: str,
    plan: Dict[str, Any]
) -> Path:
    plan_path = release_plans_dir(release_id) / f"{plan_id}.json"
    write_json(plan_path, plan)
    return plan_path


def save_operation(
    release_id: str,
    operation_id: str,
    operation: Dict[str, Any]
) -> Path:
    operation_path = release_operations_dir(release_id) / f"{operation_id}.json"
    write_json(operation_path, operation)
    return operation_path


def load_latest_runtime(release_id: str) -> Optional[Dict[str, Any]]:
    revision = latest_revision(release_id)
    if revision is None:
        return None
    runtime_path = release_revisions_dir(release_id) / str(revision) / "runtime.json"
    if not runtime_path.exists():
        return None
    return read_json(runtime_path)


def load_runtime_revision(release_id: str, revision: int) -> Optional[Dict[str, Any]]:
    runtime_path = release_revisions_dir(release_id) / str(revision) / "runtime.json"
    if not runtime_path.exists():
        return None
    return read_json(runtime_path)


def latest_compose_path(release_id: str) -> Optional[Path]:
    revision = latest_revision(release_id)
    if revision is None:
        return None
    candidate = release_revisions_dir(release_id) / str(revision) / "compose.yaml"
    if candidate.exists():
        return candidate
    return None


def load_plan(release_id: str, plan_id: str) -> Optional[Dict[str, Any]]:
    plan_path = release_plans_dir(release_id) / f"{plan_id}.json"
    if not plan_path.exists():
        return None
    return read_json(plan_path)


def load_operation(release_id: str, operation_id: str) -> Optional[Dict[str, Any]]:
    operation_path = release_operations_dir(release_id) / f"{operation_id}.json"
    if not operation_path.exists():
        return None
    return read_json(operation_path)


def find_operation(operation_id: str) -> Optional[Dict[str, Any]]:
    releases_root = _workspace_root() / "releases"
    if not releases_root.exists():
        return None
    for release_dir in releases_root.iterdir():
        if not release_dir.is_dir():
            continue
        operation_path = release_dir / "operations" / f"{operation_id}.json"
        if operation_path.exists():
            return read_json(operation_path)
    return None


def load_runtime_by_path(relative_path: str) -> Optional[Dict[str, Any]]:
    path = _workspace_root() / relative_path
    if not path.exists():
        return None
    return read_json(path)


def load_compose_path(relative_path: str) -> Path:
    return _workspace_root() / relative_path


__all__ = [
    "contracts_root",
    "latest_revision",
    "load_latest_runtime",
    "load_runtime_revision",
    "load_plan",
    "load_runtime_by_path",
    "load_compose_path",
    "load_operation",
    "find_operation",
    "list_release_ids",
    "latest_compose_path",
    "save_plan",
    "save_revision_artifacts",
    "save_operation",
    "_now_iso",
]
