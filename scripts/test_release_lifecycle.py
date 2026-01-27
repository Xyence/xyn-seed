import json
import os
import time
from pathlib import Path
from urllib import request, error


BASE_URL = os.environ.get("XYNSEED_BASE_URL", "http://localhost:8001/api/v1").rstrip("/")
TOKEN = os.environ.get("XYNSEED_API_TOKEN")


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return headers


def _request_json(method: str, path: str, payload=None) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=f"{BASE_URL}{path}",
        method=method,
        data=data,
        headers=_headers()
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body}") from exc


def _load_runner_fixture() -> dict:
    root = Path(__file__).resolve().parents[1]
    fixture = root.parent / "xyn-contracts" / "fixtures" / "runner.release.json"
    return json.loads(fixture.read_text())


def _wait_for_status(release_id: str, predicate, timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = _request_json("GET", f"/releases/{release_id}/status")
        if predicate(status):
            return status
        time.sleep(2)
    raise RuntimeError("Timed out waiting for release status")


def main():
    release_spec = _load_runner_fixture()
    release_spec["metadata"]["name"] = "runner-lifecycle"
    release_spec["metadata"]["namespace"] = "core"
    release_id = f"{release_spec['metadata']['namespace']}.{release_spec['metadata']['name']}"

    print("Planning release...")
    plan = _request_json("POST", "/releases/plan", {"release_spec": release_spec})
    op = _request_json("POST", "/releases/apply", {"release_id": release_id, "plan_id": plan["planId"]})
    if op["status"] != "succeeded":
        raise RuntimeError(f"Apply failed: {op}")

    print("Waiting for running services...")
    _wait_for_status(release_id, lambda s: any(svc["state"] == "running" for svc in s.get("services", [])))

    print("Planning stop...")
    stop_plan = _request_json("POST", f"/releases/{release_id}/plan/stop", {})
    stop_op = _request_json("POST", "/releases/apply", {"release_id": release_id, "plan_id": stop_plan["planId"]})
    if stop_op["status"] != "succeeded":
        raise RuntimeError(f"Stop failed: {stop_op}")

    print("Waiting for stopped services...")
    _wait_for_status(release_id, lambda s: all(svc["state"] != "running" for svc in s.get("services", [])))

    print("Planning restart...")
    restart_plan = _request_json(
        "POST",
        f"/releases/{release_id}/plan/restart",
        {"serviceName": "runner-api"}
    )
    restart_op = _request_json(
        "POST",
        "/releases/apply",
        {"release_id": release_id, "plan_id": restart_plan["planId"]}
    )
    if restart_op["status"] != "succeeded":
        raise RuntimeError(f"Restart failed: {restart_op}")

    print("Waiting for running services...")
    _wait_for_status(release_id, lambda s: any(svc["state"] == "running" for svc in s.get("services", [])))

    print("Planning destroy...")
    destroy_plan = _request_json(
        "POST",
        f"/releases/{release_id}/plan/destroy",
        {"removeVolumes": False}
    )
    destroy_op = _request_json(
        "POST",
        "/releases/apply",
        {"release_id": release_id, "plan_id": destroy_plan["planId"]}
    )
    if destroy_op["status"] != "succeeded":
        raise RuntimeError(f"Destroy failed: {destroy_op}")

    print("Lifecycle test succeeded.")


if __name__ == "__main__":
    main()
