import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.api import releases  # noqa: E402


def test_release_plan_apply_status():
    app = FastAPI()
    app.include_router(releases.router, prefix="/api/v1")

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir)
        os.environ["SHINESEED_WORKSPACE"] = str(workspace_root)
        os.environ["SHINESEED_CONTRACTS_ROOT"] = str(Path(__file__).resolve().parents[2] / "xyn-contracts")

        client = TestClient(app)

        release_spec = {
            "apiVersion": "xyn.seed/v1",
            "kind": "Release",
            "metadata": {
                "name": "runner",
                "namespace": "core",
                "labels": {"owner": "shineseed"}
            },
            "backend": {"type": "k8s"},
            "components": [
                {
                    "name": "runner-api",
                    "image": "xyence/runner-api:dev",
                    "ports": [
                        {"name": "http", "containerPort": 8088, "hostPort": 8088, "protocol": "tcp"}
                    ],
                    "env": {"RUNNER_LOG_LEVEL": "info"}
                }
            ]
        }

        os.environ["SHINESEED_API_TOKEN"] = ""
        plan_resp = client.post(
            "/api/v1/releases/plan",
            json={"release_spec": release_spec}
        )
        assert plan_resp.status_code == 200
        plan = plan_resp.json()
        assert plan["releaseId"] == "core.runner"
        assert plan["revisionTo"] == 1
        assert "runtimeSpecPath" in plan["artifacts"]
        assert not plan["artifacts"].get("composeYamlPath")
        assert plan["actions"]

        apply_resp = client.post(
            "/api/v1/releases/apply",
            json={"release_id": plan["releaseId"], "plan_id": plan["planId"]}
        )
        assert apply_resp.status_code == 200
        operation = apply_resp.json()
        assert operation["status"] == "failed"
        assert operation["artifacts"].get("notImplemented") == "k8s"

        op_resp = client.get(f"/api/v1/operations/{operation['operationId']}")
        assert op_resp.status_code == 200
        op_payload = op_resp.json()
        assert op_payload["operationId"] == operation["operationId"]

        status_resp = client.get("/api/v1/releases/core.runner/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["desiredRevision"] == 1
        assert status["observed"]["backend"] == "k8s"


def test_release_auth_required():
    app = FastAPI()
    app.include_router(releases.router, prefix="/api/v1")

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["SHINESEED_WORKSPACE"] = str(Path(tmpdir))
        os.environ["SHINESEED_CONTRACTS_ROOT"] = str(Path(__file__).resolve().parents[2] / "xyn-contracts")
        os.environ["SHINESEED_API_TOKEN"] = "secret-token"

        client = TestClient(app)
        release_spec = {
            "apiVersion": "xyn.seed/v1",
            "kind": "Release",
            "metadata": {
                "name": "runner",
                "namespace": "core",
                "labels": {"owner": "shineseed"}
            },
            "backend": {"type": "k8s"},
            "components": [
                {
                    "name": "runner-api",
                    "image": "xyence/runner-api:dev"
                }
            ]
        }

        plan_resp = client.post("/api/v1/releases/plan", json={"release_spec": release_spec})
        assert plan_resp.status_code == 401

        plan_resp = client.post(
            "/api/v1/releases/plan",
            headers={"Authorization": "Bearer secret-token"},
            json={"release_spec": release_spec}
        )
        assert plan_resp.status_code == 200

        bad_resp = client.post(
            "/api/v1/releases/plan",
            headers={"Authorization": "Bearer wrong"},
            json={"release_spec": release_spec}
        )
        assert bad_resp.status_code == 403


if __name__ == "__main__":
    test_release_plan_apply_status()
    test_release_auth_required()
    print("ok - test_releases_api")
