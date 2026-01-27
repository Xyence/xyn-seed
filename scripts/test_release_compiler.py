import json
import sys
from pathlib import Path

from jsonschema import validate


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.releases.compiler import compile_release_to_runtime  # noqa: E402


def load_schema(name: str) -> dict:
    schema_path = ROOT.parent / "xyn-contracts" / "schemas" / name
    return json.loads(schema_path.read_text())


def test_compile_build_image_name_and_published_port():
    release_schema = load_schema("ReleaseSpec.schema.json")
    runtime_schema = load_schema("RuntimeSpec.schema.json")

    release_spec = {
        "apiVersion": "xyn.seed/v1",
        "kind": "Release",
        "metadata": {
            "name": "builder",
            "namespace": "core",
            "labels": {"owner": "shineseed"}
        },
        "backend": {"type": "compose"},
        "components": [
            {
                "name": "build-app",
                "build": {
                    "context": "./app",
                    "imageName": "xyence/build-app:dev"
                },
                "ports": [
                    {
                        "name": "http",
                        "containerPort": 8080,
                        "hostPort": 18080,
                        "protocol": "tcp"
                    }
                ],
                "env": {"LOG_LEVEL": "debug"}
            }
        ]
    }

    validate(instance=release_spec, schema=release_schema)
    runtime_spec = compile_release_to_runtime(release_spec, revision=1)
    validate(instance=runtime_spec, schema=runtime_schema)

    container = runtime_spec["deployments"][0]["podTemplate"]["containers"][0]
    assert container["image"] == "xyence/build-app:dev"
    assert container["ports"][0]["publishedPort"] == 18080
    assert runtime_spec["services"][0]["ports"][0]["port"] == 18080


if __name__ == "__main__":
    test_compile_build_image_name_and_published_port()
    print("ok - test_release_compiler")
