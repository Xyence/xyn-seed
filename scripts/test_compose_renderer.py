import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.releases.compose_renderer import render_compose  # noqa: E402


def test_render_compose_uses_published_port():
    runtime_spec = {
        "apiVersion": "xyn.seed/v1",
        "kind": "Runtime",
        "metadata": {
            "name": "runner",
            "namespace": "core",
            "labels": {"owner": "xyn-seed"}
        },
        "release": {
            "releaseId": "core.runner",
            "revision": 1,
            "backend": {"type": "compose"}
        },
        "networks": [{"name": "runner-net"}],
        "volumes": [{"name": "runner-workspace"}],
        "deployments": [
            {
                "name": "runner-api",
                "replicas": 1,
                "podTemplate": {
                    "labels": {"app": "runner-api"},
                    "containers": [
                        {
                            "name": "runner-api",
                            "image": "xyence/xyn-runner-api:git-b56708f",
                            "ports": [
                                {
                                    "name": "http",
                                    "containerPort": 8088,
                                    "publishedPort": 8088,
                                    "protocol": "tcp"
                                }
                            ],
                            "env": [
                                {"name": "RUNNER_LOG_LEVEL", "value": "info"}
                            ],
                            "healthcheck": {
                                "test": ["CMD", "curl", "-f", "http://localhost:8088/healthz"],
                                "interval": "10s",
                                "timeout": "5s",
                                "retries": 5
                            },
                            "volumeMounts": [
                                {"name": "runner-workspace", "mountPath": "/workspace"}
                            ]
                        }
                    ]
                }
            }
        ],
        "services": []
    }

    rendered = render_compose(runtime_spec)
    expected = (
        "name: core_runner\n"
        "\n"
        "services:\n"
        "  runner-api:\n"
        "    image: xyence/xyn-runner-api:git-b56708f\n"
        "    environment:\n"
        "      RUNNER_LOG_LEVEL: info\n"
        "    healthcheck:\n"
        "      interval: 10s\n"
        "      retries: 5\n"
        "      test:\n"
        "        - CMD\n"
        "        - curl\n"
        "        - -f\n"
        "        - http://localhost:8088/healthz\n"
        "      timeout: 5s\n"
        "    ports:\n"
        "      - \"8088:8088\"\n"
        "    volumes:\n"
        "      - runner-workspace:/workspace\n"
        "    networks:\n"
        "      - runner-net\n"
        "    labels:\n"
        "      owner: xyn-seed\n"
        "      release_id: core.runner\n"
        "      revision: 1\n"
        "      service: runner-api\n"
        "\n"
        "volumes:\n"
        "  runner-workspace: {}\n"
        "\n"
        "networks:\n"
        "  runner-net: {}\n"
    )

    assert rendered == expected


if __name__ == "__main__":
    test_render_compose_uses_published_port()
    print("ok - test_compose_renderer")
