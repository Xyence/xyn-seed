"""Helpers for querying deployed net-inventory app instances."""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from sqlalchemy.orm import Session

from core.models import Job, JobStatus


HTTP_TIMEOUT_SECONDS = 10


def _request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], str]:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw) if raw else {}
            return int(response.status), parsed if isinstance(parsed, dict) else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw) if raw else {}
        return int(exc.code), parsed if isinstance(parsed, dict) else {}, raw
    except Exception as exc:
        return 0, {}, str(exc)


def http_request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], str]:
    return _request_json(url, method=method, payload=payload)


def latest_deployment_for_workspace(db: Session, *, workspace_id: uuid.UUID) -> dict[str, Any]:
    row = (
        db.query(Job)
        .filter(
            Job.workspace_id == workspace_id,
            Job.type == "deploy_app_local",
            Job.status == JobStatus.SUCCEEDED.value,
        )
        .order_by(Job.updated_at.desc())
        .first()
    )
    if not row:
        row = (
            db.query(Job)
            .filter(
                Job.type == "deploy_app_local",
                Job.status == JobStatus.SUCCEEDED.value,
            )
            .order_by(Job.updated_at.desc())
            .first()
        )
    if not row:
        raise RuntimeError("No successful deploy_app_local job found.")
    output = row.output_json if isinstance(row.output_json, dict) else {}
    app_url = str(output.get("app_url") or "").strip().rstrip("/")
    if not app_url:
        raise RuntimeError("Latest deployment is missing output_json.app_url.")
    return output


def _container_request_json(
    container_name: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], str]:
    script = f"""
import json
import urllib.error
import urllib.request
url = "http://localhost:8080{path}"
method = {method!r}
data = None
headers = {{"Content-Type": "application/json"}}
if method in ("POST", "PUT", "PATCH"):
    data = json.dumps({payload or {}!r}).encode("utf-8")
req = urllib.request.Request(url, method=method, headers=headers, data=data)
try:
    with urllib.request.urlopen(req, timeout={HTTP_TIMEOUT_SECONDS}) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        print(json.dumps({{"code": int(resp.status), "body": body}}))
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="ignore")
    print(json.dumps({{"code": int(exc.code), "body": body}}))
except Exception as exc:
    print(json.dumps({{"code": 0, "body": str(exc)}}))
"""
    proc = subprocess.run(
        ["docker", "exec", "-i", container_name, "python", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return 0, {}, proc.stderr.strip() or proc.stdout.strip()
    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        return 0, {}, "empty response"
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return 0, {}, lines[-1]
    code = int(payload.get("code") or 0)
    raw = str(payload.get("body") or "")
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {}
    return code, parsed if isinstance(parsed, dict) else {}, raw


def list_devices(*, deployment: dict[str, Any], workspace_id: uuid.UUID) -> dict[str, Any]:
    response_code, response_payload, response_raw = deployment_request_json(
        deployment=deployment,
        method="GET",
        path="/devices",
        query={"workspace_id": str(workspace_id)},
    )
    if response_code != 200:
        raise RuntimeError(f"GET /devices failed ({response_code}): {response_raw}")
    return response_payload


def deployment_request_json(
    *,
    deployment: dict[str, Any],
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], str]:
    app_url = str(deployment.get("app_url") or "").rstrip("/")
    container_name = str(deployment.get("app_container_name") or "").strip()
    query_string = urllib.parse.urlencode({k: str(v) for k, v in (query or {}).items() if v is not None})
    request_path = str(path or "/").strip() or "/"
    if not request_path.startswith("/"):
        request_path = "/" + request_path
    if query_string:
        request_path = f"{request_path}?{query_string}"
    if container_name:
        code, response_payload, raw = _container_request_json(
            container_name,
            request_path,
            method=method.upper(),
            payload=payload,
        )
    else:
        code, response_payload, raw = _request_json(
            f"{app_url}{request_path}",
            method=method.upper(),
            payload=payload,
        )
    return code, response_payload, raw
