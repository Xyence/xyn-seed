import os
import sys
import tempfile
import time
from pathlib import Path
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.api import releases  # noqa: E402
from core.releases import store  # noqa: E402


def _docker_compose_available() -> bool:
    result = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        check=False
    )
    return result.returncode == 0


def test_release_integration_compose():
    if not _docker_compose_available():
        print("skip - docker compose not available")
        return

    app = FastAPI()
    app.include_router(releases.router, prefix="/api/v1")

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir)
        os.environ["SHINESEED_WORKSPACE"] = str(workspace_root)
        os.environ["SHINESEED_CONTRACTS_ROOT"] = str(Path(__file__).resolve().parents[2] / "xyn-contracts")

        client = TestClient(app)

        token = "secret-token"
        os.environ["SHINESEED_API_TOKEN"] = token

        release_spec = {
            "apiVersion": "xyn.shineseed/v1",
            "kind": "Release",
            "metadata": {
                "name": "integration",
                "namespace": "core",
                "labels": {"owner": "shineseed"}
            },
            "backend": {"type": "compose"},
            "components": [
                {
                    "name": "redis",
                    "image": "redis:7-alpine",
                    "ports": [
                        {"name": "redis", "containerPort": 6379, "hostPort": 16379, "protocol": "tcp"}
                    ]
                }
            ]
        }

        plan_resp = client.post(
            "/api/v1/releases/plan",
            json={"release_spec": release_spec},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert plan_resp.status_code == 200
        plan = plan_resp.json()

        apply_resp = client.post(
            "/api/v1/releases/apply",
            json={"release_id": plan["releaseId"], "plan_id": plan["planId"]},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert apply_resp.status_code == 200
        operation = apply_resp.json()
        assert operation["status"] == "succeeded"

        status = None
        for _ in range(6):
            status_resp = client.get(
                "/api/v1/releases/core.integration/status",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert status_resp.status_code == 200
            status = status_resp.json()
            if status["services"]:
                if any(service.get("state") == "running" for service in status["services"]):
                    break
            time.sleep(1)

        assert status is not None
        assert any(service.get("state") == "running" for service in status["services"])

        compose_path = store.load_compose_path(plan["artifacts"]["composeYamlPath"])
        project_name = "core_integration"
        subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "down"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(compose_path.parent),
            env={"COMPOSE_PROJECT_NAME": project_name, **dict(os.environ)}
        )


if __name__ == "__main__":
    test_release_integration_compose()
    print("ok - test_release_integration")
