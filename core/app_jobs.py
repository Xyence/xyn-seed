"""Phase-1 app-intent job worker pipeline.

Executes queued jobs:
- generate_app_spec
- deploy_app_local
- smoke_test
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from fastapi import HTTPException
from jsonschema import ValidationError, validate
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.models import Artifact, Job, JobStatus, Workspace
from core.primitives import get_primitive_catalog
from core.provisioning_local import ProvisionLocalRequest, provision_local_instance


POLL_SECONDS = float(os.getenv("XYN_APP_JOB_POLL_SECONDS", "2.0"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("XYN_APP_JOB_HTTP_TIMEOUT", "10"))
APP_DEPLOY_HEALTH_TIMEOUT_SECONDS = int(os.getenv("XYN_APP_DEPLOY_HEALTH_TIMEOUT_SECONDS", "240"))
COMMAND_TIMEOUT_SECONDS = int(os.getenv("XYN_APP_JOB_COMMAND_TIMEOUT_SECONDS", "240"))
SMOKE_SIBLING_TIMEOUT_SECONDS = int(os.getenv("XYN_SMOKE_SIBLING_TIMEOUT_SECONDS", "300"))
APPSPEC_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "appspec_v0.schema.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _safe_slug(value: str, *, default: str = "app") -> str:
    raw = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in str(value or "").lower())
    collapsed = "-".join(part for part in raw.split("-") if part)
    return collapsed or default


def _deployments_root() -> Path:
    workspace_root = Path(os.getenv("XYNSEED_WORKSPACE", "/app/workspace"))
    root = Path(os.getenv("XYN_LOCAL_APP_DEPLOYMENTS_ROOT", str(workspace_root / "app_deployments"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _workspace_root() -> Path:
    root = Path(os.getenv("XYN_LOCAL_WORKSPACE_ROOT", os.getenv("XYNSEED_WORKSPACE", "/app/workspace"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run(cmd: list[str], *, cwd: Optional[Path] = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        return 124, stdout, stderr or f"command timed out after {COMMAND_TIMEOUT_SECONDS}s"
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _container_http_json(container_name: str, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> tuple[int, dict[str, Any], str]:
    script = f"""
import json
import urllib.error
import urllib.request

method = {method!r}
path = {path!r}
payload = {json.dumps(payload or {})!r}
url = "http://localhost:8080" + path
data = None
headers = {{"Content-Type": "application/json"}}
if method in ("POST", "PUT", "PATCH"):
    data = payload.encode("utf-8")
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
        timeout=HTTP_TIMEOUT_SECONDS + 5,
    )
    if proc.returncode != 0:
        return 0, {}, proc.stderr.strip() or proc.stdout.strip()
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return 0, {}, "empty container response"
    line = out[-1].strip()
    try:
        payload_json = json.loads(line)
    except json.JSONDecodeError:
        return 0, {}, line
    code = int(payload_json.get("code") or 0)
    raw_body = str(payload_json.get("body") or "")
    try:
        body_json = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        body_json = {}
    return code, body_json, raw_body


def _wait_for_container_http_ok(container_name: str, path: str, *, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        code, _, _ = _container_http_json(container_name, "GET", path)
        if code == 200:
            return True
        time.sleep(2)
    return False


def _append_job_log(log_lines: list[str], message: str) -> None:
    log_lines.append(f"[{_iso_now()}] {message}")


def _load_appspec_schema() -> dict[str, Any]:
    return json.loads(APPSPEC_SCHEMA_PATH.read_text(encoding="utf-8"))


def _persist_json_artifact(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    name: str,
    kind: str,
    payload: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    specs_root = _workspace_root() / "app_specs"
    specs_root.mkdir(parents=True, exist_ok=True)
    artifact_id = uuid.uuid4()
    path = specs_root / f"{artifact_id}.json"
    text = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    row = Artifact(
        id=artifact_id,
        name=name,
        kind=kind,
        content_type="application/json",
        byte_length=len(text.encode("utf-8")),
        created_by="app-job-worker",
        storage_path=str(path),
        extra_metadata={"workspace_id": str(workspace_id), **(metadata or {})},
        created_at=_utc_now(),
    )
    db.add(row)
    db.flush()
    return str(row.id)


def _build_app_spec(*, workspace_id: uuid.UUID, title: str, raw_prompt: str) -> dict[str, Any]:
    prompt = raw_prompt.lower()
    requires_primitives: list[str] = []
    if any(token in prompt for token in ("location", "address", "site", "rack", "closet")):
        requires_primitives.append("location")
    app_slug = "net-inventory" if "network" in raw_prompt.lower() and "inventory" in raw_prompt.lower() else _safe_slug(title, default="net-inventory")
    spec = {
        "schema_version": "xyn.appspec.v0",
        "app_slug": app_slug,
        "title": title or "Network Inventory",
        "workspace_id": str(workspace_id),
        "services": [
            {
                "name": "net-inventory-api",
                "image": "python:3.11-alpine",
                "env": {
                    "APP_ENV": "local",
                    "PORT": "8080",
                    "DATABASE_URL": "postgresql://xyn:xyn_dev_password@net-inventory-db:5432/net_inventory",
                },
                "ports": [
                    {"container": 8080, "host": 18080, "protocol": "tcp"},
                ],
                "depends_on": ["net-inventory-db"],
            },
            {
                "name": "net-inventory-db",
                "image": "postgres:16-alpine",
                "env": {
                    "POSTGRES_DB": "net_inventory",
                    "POSTGRES_USER": "xyn",
                    "POSTGRES_PASSWORD": "xyn_dev_password",
                },
                "ports": [
                    {"container": 5432, "host": 15432, "protocol": "tcp"},
                ],
                "depends_on": [],
            },
        ],
        "ingress": {"enabled": False},
        "data": {"postgres": {"required": True, "service": "net-inventory-db"}},
        "reports": [
            "device_count_by_workspace",
            "devices_by_vendor",
            "stale_device_last_seen",
        ],
        "source_prompt": raw_prompt,
    }
    if requires_primitives:
        spec["requires_primitives"] = requires_primitives
    return spec


def _ports_yaml(ports: list[dict[str, Any]], *, host_port_override: Optional[int] = None) -> list[str]:
    lines: list[str] = []
    for idx, port in enumerate(ports):
        host_port = int(port.get("host") or 0)
        if idx == 0 and host_port_override is not None:
            host_port = host_port_override
        container_port = int(port.get("container") or 0)
        protocol = str(port.get("protocol") or "tcp").strip().lower()
        if protocol not in {"tcp", "udp"}:
            protocol = "tcp"
        lines.append(f'      - "{host_port}:{container_port}/{protocol}"')
    return lines


def _resolve_published_port(container_name: str, target: str) -> int:
    code, stdout, stderr = _run(["docker", "port", container_name, target])
    if code != 0:
        raise RuntimeError(f"Failed to resolve published port for {container_name} {target}: {stderr or stdout}")
    first = (stdout.splitlines() or [""])[0].strip()
    if ":" not in first:
        raise RuntimeError(f"Unexpected docker port output: {first}")
    return int(first.rsplit(":", 1)[1])


def _materialize_net_inventory_compose(
    *,
    app_spec: dict[str, Any],
    deployment_dir: Path,
    app_port: int,
    compose_project: str,
) -> Path:
    app_service = next((row for row in app_spec.get("services", []) if row.get("name") == "net-inventory-api"), {})
    app_ports = _ports_yaml(
        list(app_service.get("ports") or [{"host": 0, "container": 8080, "protocol": "tcp"}]),
        host_port_override=0,
    )

    server_script = """import json
from http.server import BaseHTTPRequestHandler, HTTPServer

devices = []


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        if self.path == "/devices":
            self._write_json(200, {"items": devices})
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/devices":
            self._write_json(404, {"error": "not_found"})
            return
        content_len = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_len) if content_len else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._write_json(400, {"error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._write_json(400, {"error": "invalid_payload"})
            return
        devices.append(payload)
        self._write_json(200, payload)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()
"""
    inline_command = (
        "cat >/tmp/server.py <<'PY'\n"
        f"{server_script}"
        "PY\n"
        "python /tmp/server.py"
    )

    compose = deployment_dir / "docker-compose.yml"
    compose.write_text(
        "\n".join(
            [
                "services:",
                "  net-inventory-db:",
                "    image: postgres:16-alpine",
                f"    container_name: {compose_project}-db",
                "    restart: unless-stopped",
                "    environment:",
                "      POSTGRES_DB: net_inventory",
                "      POSTGRES_USER: xyn",
                "      POSTGRES_PASSWORD: xyn_dev_password",
                "    healthcheck:",
                "      test: [\"CMD-SHELL\", \"pg_isready -U xyn -d net_inventory\"]",
                "      interval: 5s",
                "      timeout: 5s",
                "      retries: 20",
                "",
                "  net-inventory-api:",
                "    image: python:3.11-alpine",
                f"    container_name: {compose_project}-api",
                "    restart: unless-stopped",
                "    working_dir: /app",
                "    command:",
                "      - /bin/sh",
                "      - -lc",
                f"      - |-\n        {inline_command.replace(chr(10), chr(10) + '        ')}",
                "    environment:",
                "      APP_ENV: local",
                "      PORT: \"8080\"",
                "      DATABASE_URL: postgresql://xyn:xyn_dev_password@net-inventory-db:5432/net_inventory",
                "    ports:",
                *app_ports,
                "    depends_on:",
                "      net-inventory-db:",
                "        condition: service_healthy",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return compose


def _handle_generate_app_spec(db: Session, job: Job, logs: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = job.input_json or {}
    title = str(payload.get("title") or "Network Inventory").strip() or "Network Inventory"
    content = payload.get("content_json") if isinstance(payload.get("content_json"), dict) else {}
    raw_prompt = str(content.get("raw_prompt") or payload.get("raw_prompt") or title).strip()
    _append_job_log(logs, f"Generating AppSpec from prompt: {raw_prompt}")
    primitive_catalog = get_primitive_catalog()
    _append_job_log(logs, f"Loaded primitive catalog ({len(primitive_catalog)} entries)")
    app_spec = _build_app_spec(workspace_id=job.workspace_id, title=title, raw_prompt=raw_prompt)
    schema = _load_appspec_schema()
    try:
        validate(instance=app_spec, schema=schema)
    except ValidationError as exc:
        raise RuntimeError(f"AppSpec validation failed: {exc.message}") from exc
    _append_job_log(logs, f"AppSpec validated against schema: {APPSPEC_SCHEMA_PATH.name}")
    artifact_id = _persist_json_artifact(
        db,
        workspace_id=job.workspace_id,
        name=f"appspec.{app_spec['app_slug']}",
        kind="app_spec",
        payload=app_spec,
        metadata={"job_id": str(job.id)},
    )
    _append_job_log(logs, f"Persisted AppSpec artifact: {artifact_id}")
    follow_up = [
        {
            "type": "deploy_app_local",
            "input_json": {
                "app_spec": app_spec,
                "app_spec_artifact_id": artifact_id,
                "source_job_id": str(job.id),
            },
        }
    ]
    return {
        "app_spec": app_spec,
        "app_spec_artifact_id": artifact_id,
        "app_spec_schema": "xyn.appspec.v0",
        "primitive_catalog": primitive_catalog,
    }, follow_up


def _handle_deploy_app_local(db: Session, job: Job, logs: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = job.input_json or {}
    app_spec = payload.get("app_spec") if isinstance(payload.get("app_spec"), dict) else {}
    app_slug = _safe_slug(str(app_spec.get("app_slug") or "net-inventory"), default="net-inventory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    deployment_dir = _deployments_root() / app_slug / stamp
    deployment_dir.mkdir(parents=True, exist_ok=True)
    compose_project = _safe_slug(f"xyn-app-{app_slug}-{str(job.id)[:8]}", default="xyn-app")
    compose_path = _materialize_net_inventory_compose(
        app_spec=app_spec,
        deployment_dir=deployment_dir,
        app_port=0,
        compose_project=compose_project,
    )
    _append_job_log(logs, f"Wrote compose: {compose_path}")
    up_cmd = ["docker", "compose", "-p", compose_project, "-f", str(compose_path), "up", "-d"]
    code, stdout, stderr = _run(up_cmd, cwd=deployment_dir)
    _append_job_log(logs, f"Executed: {' '.join(up_cmd)}")
    if stdout:
        _append_job_log(logs, f"compose stdout: {stdout[-600:]}")
    if code != 0:
        _run(["docker", "compose", "-p", compose_project, "-f", str(compose_path), "down", "--remove-orphans"], cwd=deployment_dir)
        raise RuntimeError(f"docker compose up failed: {stderr or stdout}")
    app_port = _resolve_published_port(f"{compose_project}-api", "8080/tcp")
    app_container_name = f"{compose_project}-api"
    app_url = f"http://localhost:{app_port}"
    _append_job_log(logs, f"Local app URL: {app_url}")
    _append_job_log(logs, f"Allocated ports: app={app_port}/tcp")
    _append_job_log(logs, "Compose up succeeded; readiness checks deferred to smoke_test job")
    deploy_output = {
        "app_slug": app_slug,
        "compose_project": compose_project,
        "deployment_dir": str(deployment_dir),
        "compose_path": str(compose_path),
        "app_container_name": app_container_name,
        "app_url": app_url,
        "ports": {"app_tcp": app_port},
    }
    follow_up = [
        {
            "type": "smoke_test",
            "input_json": {
                "deployment": deploy_output,
                "app_spec": app_spec,
                "source_job_id": str(job.id),
            },
        }
    ]
    return deploy_output, follow_up


def _handle_smoke_test(db: Session, job: Job, logs: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = job.input_json or {}
    deployment = payload.get("deployment") if isinstance(payload.get("deployment"), dict) else {}
    app_url = str(deployment.get("app_url") or "").rstrip("/")
    app_container_name = str(deployment.get("app_container_name") or "").strip()
    if not app_url:
        raise RuntimeError("smoke_test missing deployment.app_url")
    if not app_container_name:
        raise RuntimeError("smoke_test missing deployment.app_container_name")
    _append_job_log(logs, f"Smoke testing app URL: {app_url}")
    _append_job_log(logs, f"Waiting for app health up to {APP_DEPLOY_HEALTH_TIMEOUT_SECONDS}s")
    if not _wait_for_container_http_ok(app_container_name, "/health", timeout_seconds=APP_DEPLOY_HEALTH_TIMEOUT_SECONDS):
        raise RuntimeError(f"App health endpoint failed to become ready in container {app_container_name}")
    health_code, health_json, health_text = _container_http_json(app_container_name, "GET", "/health")
    if health_code != 200:
        raise RuntimeError(f"Health check failed ({health_code}): {health_text}")
    routes_ok: dict[str, Any] = {}
    list_code, list_json, list_text = _container_http_json(app_container_name, "GET", "/devices")
    routes_ok["list_devices"] = {"code": list_code, "body": list_json or list_text}
    if list_code != 200:
        raise RuntimeError(f"GET /devices failed ({list_code}): {list_text}")
    create_payload = {"name": "core-router-1", "ip": "10.10.0.1", "workspace_id": str(job.workspace_id)}
    create_code, create_json, create_text = _container_http_json(app_container_name, "POST", "/devices", payload=create_payload)
    routes_ok["create_device"] = {"code": create_code, "body": create_json or create_text}
    if create_code not in {200, 201}:
        raise RuntimeError(f"POST /devices failed ({create_code}): {create_text}")
    _append_job_log(logs, "App API smoke checks passed (/health, GET /devices, POST /devices)")

    workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
    workspace_slug = str(getattr(workspace, "slug", "default") or "default")
    sibling_name = _safe_slug(f"smoke-{deployment.get('app_slug') or 'app'}-{str(job.id)[:6]}", default="smoke-app")
    _append_job_log(logs, f"Provisioning sibling Xyn instance for smoke checks: {sibling_name}")
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                provision_local_instance,
                ProvisionLocalRequest(
                    name=sibling_name,
                    force=True,
                    workspace_slug=workspace_slug,
                ),
            )
            sibling = future.result(timeout=SMOKE_SIBLING_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        raise RuntimeError(
            f"Sibling Xyn provisioning timed out after {SMOKE_SIBLING_TIMEOUT_SECONDS}s"
        ) from exc
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        raise RuntimeError(f"Sibling Xyn provisioning failed: {detail}") from exc
    _append_job_log(logs, f"Sibling Xyn URLs: ui={sibling.get('ui_url')} api={sibling.get('api_url')}")
    return {
        "app_health": {"code": health_code, "body": health_json or health_text},
        "app_checks": routes_ok,
        "sibling_xyn": {
            "deployment_id": sibling.get("deployment_id"),
            "compose_project": sibling.get("compose_project"),
            "ui_url": sibling.get("ui_url"),
            "api_url": sibling.get("api_url"),
        },
        "status": "passed",
    }, []


def _claim_next_job(db: Session) -> Optional[Job]:
    row = (
        db.query(Job)
        .filter(Job.status == JobStatus.QUEUED.value)
        .order_by(Job.created_at.asc())
        .first()
    )
    if not row:
        return None
    row.status = JobStatus.RUNNING.value
    row.updated_at = _utc_now()
    prefix = row.logs_text.rstrip() + "\n" if row.logs_text else ""
    row.logs_text = f"{prefix}[{_iso_now()}] Worker claimed job {row.id} ({row.type})"
    db.commit()
    db.refresh(row)
    return row


def _enqueue_job(db: Session, *, workspace_id: uuid.UUID, job_type: str, input_json: dict[str, Any]) -> str:
    next_job = Job(
        workspace_id=workspace_id,
        type=job_type,
        status=JobStatus.QUEUED.value,
        input_json=input_json,
        output_json={},
        logs_text=f"[{_iso_now()}] Queued by app-job-worker.",
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    db.add(next_job)
    db.flush()
    return str(next_job.id)


def _recover_running_jobs(db: Session) -> None:
    running = db.query(Job).filter(Job.status == JobStatus.RUNNING.value).all()
    if not running:
        return
    for row in running:
        row.status = JobStatus.FAILED.value
        payload = row.output_json if isinstance(row.output_json, dict) else {}
        payload["error"] = "Job interrupted by process restart before completion."
        row.output_json = payload
        prefix = row.logs_text.rstrip() + "\n" if row.logs_text else ""
        row.logs_text = (
            f"{prefix}[{_iso_now()}] Worker startup recovered stale RUNNING job as FAILED."
        )
        row.updated_at = _utc_now()
    db.commit()


def _execute_job(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        logs: list[str] = []
        output_json: dict[str, Any] = {}
        follow_up_jobs: list[dict[str, Any]] = []
        _append_job_log(logs, f"Executing job type={job.type}")
        try:
            if job.type == "generate_app_spec":
                output_json, follow_up_jobs = _handle_generate_app_spec(db, job, logs)
            elif job.type == "deploy_app_local":
                output_json, follow_up_jobs = _handle_deploy_app_local(db, job, logs)
            elif job.type == "smoke_test":
                output_json, follow_up_jobs = _handle_smoke_test(db, job, logs)
            else:
                raise RuntimeError(f"Unsupported job type: {job.type}")
            queued_ids = []
            for item in follow_up_jobs:
                next_id = _enqueue_job(
                    db,
                    workspace_id=job.workspace_id,
                    job_type=str(item.get("type") or "").strip(),
                    input_json=item.get("input_json") if isinstance(item.get("input_json"), dict) else {},
                )
                queued_ids.append({"job_type": item.get("type"), "job_id": next_id})
            if queued_ids:
                output_json["queued_jobs"] = queued_ids
                for item in queued_ids:
                    _append_job_log(logs, f"Queued follow-up job: {item['job_type']} ({item['job_id']})")
            job.status = JobStatus.SUCCEEDED.value
            job.output_json = output_json
            _append_job_log(logs, "Job completed successfully")
        except Exception as exc:
            job.status = JobStatus.FAILED.value
            output_json = output_json or {}
            output_json["error"] = str(exc)
            job.output_json = output_json
            _append_job_log(logs, f"Job failed: {exc}")
        existing = job.logs_text.rstrip() + "\n" if job.logs_text else ""
        job.logs_text = existing + "\n".join(logs)
        job.updated_at = _utc_now()
        db.commit()
    finally:
        db.close()


def _worker_loop(stop_event: threading.Event) -> None:
    bootstrap_db = SessionLocal()
    try:
        _recover_running_jobs(bootstrap_db)
    finally:
        bootstrap_db.close()
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            row = _claim_next_job(db)
            if not row:
                time.sleep(POLL_SECONDS)
                continue
            _execute_job(row.id)
        finally:
            db.close()


@dataclass
class AppJobWorkerHandle:
    thread: threading.Thread
    stop_event: threading.Event


def start_app_job_worker() -> AppJobWorkerHandle:
    stop_event = threading.Event()
    thread = threading.Thread(target=_worker_loop, args=(stop_event,), daemon=True, name="xyn-app-job-worker")
    thread.start()
    return AppJobWorkerHandle(thread=thread, stop_event=stop_event)


def stop_app_job_worker(handle: Optional[AppJobWorkerHandle]) -> None:
    if not handle:
        return
    handle.stop_event.set()
    handle.thread.join(timeout=5)
