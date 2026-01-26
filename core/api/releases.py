"""Release plan/apply/status endpoints."""
from __future__ import annotations

import os
import subprocess
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Header
from jsonschema import validate, ValidationError
from pydantic import BaseModel

from core.releases.compiler import compile_release_to_runtime
from core.releases.compose_renderer import render_compose
from core.releases.k8s_backend import validate_runtime_spec, K8sValidationError
from core.releases import store
from core import schemas

router = APIRouter()


def _require_auth(authorization: str | None):
    token = os.environ.get("SHINESEED_API_TOKEN", "").strip()
    if not token:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    expected = f"Bearer {token}"
    if authorization.strip() != expected:
        raise HTTPException(status_code=403, detail="Invalid authorization token")


class PlanRequest(BaseModel):
    release_spec: Dict[str, Any]


class ApplyRequest(BaseModel):
    release_id: str
    plan_id: str


def _load_contract_schema_json(name: str) -> Dict[str, Any]:
    import json
    schema_path = store.contracts_root() / "schemas" / name
    return json.loads(schema_path.read_text())


def _validate_schema(instance: Dict[str, Any], schema_name: str) -> None:
    schema = _load_contract_schema_json(schema_name)
    validate(instance=instance, schema=schema)


def _index_by_name(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item.get("name"): item for item in items if item.get("name")}


def _diff_actions(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any]
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    if previous is None:
        for target_type in ("deployment", "service", "volume", "network", "route"):
            for item in current.get(f"{target_type}s", []):
                name = item.get("name")
                if not name:
                    continue
                actions.append({
                    "op": "create",
                    "targetType": target_type,
                    "targetName": name,
                    "details": {}
                })
        return sorted(actions, key=lambda a: (a["targetType"], a["targetName"]))

    for target_type in ("deployment", "service", "volume", "network", "route"):
        prev_items = _index_by_name(previous.get(f"{target_type}s", []))
        curr_items = _index_by_name(current.get(f"{target_type}s", []))

        for name, curr_item in curr_items.items():
            prev_item = prev_items.get(name)
            if prev_item is None:
                actions.append({
                    "op": "create",
                    "targetType": target_type,
                    "targetName": name,
                    "details": {}
                })
            elif prev_item != curr_item:
                actions.append({
                    "op": "update",
                    "targetType": target_type,
                    "targetName": name,
                    "details": {
                        "previous": prev_item,
                        "current": curr_item
                    }
                })

        for name in prev_items.keys():
            if name not in curr_items:
                actions.append({
                    "op": "delete",
                    "targetType": target_type,
                    "targetName": name,
                    "details": {}
                })

    return sorted(actions, key=lambda a: (a["targetType"], a["targetName"]))


@router.post("/releases/plan", response_model=schemas.ReleasePlan)
async def plan_release(request: PlanRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    release_spec = request.release_spec

    try:
        _validate_schema(release_spec, "ReleaseSpec.schema.json")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"ReleaseSpec validation error: {exc.message}")

    metadata = release_spec["metadata"]
    release_id = f"{metadata['namespace']}.{metadata['name']}"
    revision_from = store.latest_revision(release_id)
    revision_to = (revision_from or 0) + 1

    runtime_spec = compile_release_to_runtime(release_spec, revision=revision_to, release_id=release_id)
    try:
        _validate_schema(runtime_spec, "RuntimeSpec.schema.json")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"RuntimeSpec validation error: {exc.message}")

    compose_yaml = None
    backend_type = runtime_spec["release"]["backend"]["type"]
    if backend_type == "compose":
        compose_yaml = render_compose(runtime_spec)
    elif backend_type == "k8s":
        try:
            validate_runtime_spec(runtime_spec)
        except K8sValidationError as exc:
            raise HTTPException(status_code=400, detail=f"K8s validation error: {exc}")

    artifacts = store.save_revision_artifacts(
        release_id,
        revision_to,
        release_spec,
        runtime_spec,
        compose_yaml
    )

    previous_runtime = None
    if revision_from is not None:
        previous_runtime = store.load_runtime_revision(release_id, revision_from)
    actions = _diff_actions(previous_runtime, runtime_spec)
    plan_id = str(uuid.uuid4())
    plan = {
        "planId": plan_id,
        "releaseId": release_id,
        "revisionFrom": revision_from,
        "revisionTo": revision_to,
        "summary": f"{len(actions)} actions",
        "actions": actions,
        "artifacts": artifacts
    }
    store.save_plan(release_id, plan_id, plan)
    return plan


@router.post("/releases/apply", response_model=schemas.Operation)
async def apply_release(request: ApplyRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    plan = store.load_plan(request.release_id, request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    runtime_path = plan["artifacts"].get("runtimeSpecPath")
    if not runtime_path:
        raise HTTPException(status_code=400, detail="Plan missing runtimeSpecPath")

    runtime_spec = store.load_runtime_by_path(runtime_path)
    if not runtime_spec:
        raise HTTPException(status_code=404, detail="RuntimeSpec not found")

    operation_id = str(uuid.uuid4())
    status = "running"
    message = ""

    backend_type = runtime_spec["release"]["backend"]["type"]
    started_at = store._now_iso()

    if backend_type == "compose":
        compose_path_rel = plan["artifacts"].get("composeYamlPath")
        if not compose_path_rel:
            status = "failed"
            message = "composeYamlPath missing from plan"
        else:
            compose_path = store.load_compose_path(compose_path_rel)
            project_name = f"{runtime_spec['metadata']['namespace']}_{runtime_spec['metadata']['name']}"
            env = {"COMPOSE_PROJECT_NAME": project_name, **dict(os.environ)}
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_path), "up", "-d"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(compose_path.parent),
                env=env
            )
            if result.returncode != 0:
                status = "failed"
                message = result.stderr.strip() or "docker compose apply failed"
            else:
                status = "succeeded"
                message = result.stdout.strip() or "apply succeeded"
    else:
        status = "failed"
        message = f"backend '{backend_type}' apply not implemented"

    finished_at = store._now_iso()
    artifacts = {}
    if backend_type == "k8s":
        artifacts = {"notImplemented": "k8s"}

    operation = {
        "operationId": operation_id,
        "releaseId": request.release_id,
        "type": "apply",
        "status": status,
        "createdAt": started_at,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "planId": request.plan_id,
        "message": message,
        "artifacts": artifacts
    }

    store.save_operation(request.release_id, operation_id, operation)
    return operation


@router.get("/releases/{release_id}/status", response_model=schemas.ReleaseStatus)
async def get_release_status(release_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    runtime_spec = store.load_latest_runtime(release_id)
    if not runtime_spec:
        raise HTTPException(status_code=404, detail="Release not found")

    services = []
    backend_type = runtime_spec["release"]["backend"]["type"]
    message = ""

    if backend_type == "compose":
        revisions_dir = store.release_revisions_dir(release_id)
        latest = store.latest_revision(release_id)
        compose_path = None
        if latest is not None:
            candidate = revisions_dir / str(latest) / "compose.yaml"
            if candidate.exists():
                compose_path = candidate

        if compose_path:
            project_name = f"{runtime_spec['metadata']['namespace']}_{runtime_spec['metadata']['name']}"
            env = {"COMPOSE_PROJECT_NAME": project_name, **dict(os.environ)}
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_path), "ps", "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(compose_path.parent),
                env=env
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    payload = json.loads(result.stdout)
                    if isinstance(payload, dict):
                        entries = [payload]
                    elif isinstance(payload, list):
                        entries = payload
                    else:
                        entries = []
                    if not entries:
                        entries = [
                            json.loads(line)
                            for line in result.stdout.splitlines()
                            if line.strip()
                        ]
                    for entry in entries:
                        state = entry.get("State") or "unknown"
                        health = entry.get("Health") or "unknown"
                        services.append({
                            "name": entry.get("Service", "unknown"),
                            "state": "running" if state == "running" else "stopped",
                            "health": health,
                            "details": entry
                        })
                except json.JSONDecodeError:
                    message = "unable to parse docker compose status output"
            else:
                message = result.stderr.strip() or "docker compose status failed"
        else:
            message = "compose.yaml not found for latest revision"
    else:
        message = f"backend '{backend_type}' status not implemented"
        services = [
            {
                "name": service.get("name", "unknown"),
                "state": "unknown",
                "health": "unknown",
                "details": {}
            }
            for service in runtime_spec.get("services", [])
        ]

    return {
        "releaseId": release_id,
        "desiredRevision": runtime_spec["release"]["revision"],
        "observed": {
            "timestamp": store._now_iso(),
            "backend": backend_type,
            "message": message
        },
        "services": services
    }


@router.get("/operations/{operation_id}", response_model=schemas.Operation)
async def get_operation(operation_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    operation = store.find_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    return operation
