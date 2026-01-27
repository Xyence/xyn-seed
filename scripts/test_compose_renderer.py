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
            "labels": {"owner": "shineseed"}
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
                            "image": "xyence/runner-api:dev",
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
        "    image: xyence/runner-api:dev\n"
        "    environment:\n"
        "      RUNNER_LOG_LEVEL: info\n"
        "    ports:\n"
        "      - \"8088:8088\"\n"
        "    volumes:\n"
        "      - runner-workspace:/workspace\n"
        "    networks:\n"
        "      - runner-net\n"
        "    labels:\n"
        "      owner: shineseed\n"
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
