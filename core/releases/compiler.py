"""ReleaseSpec to RuntimeSpec compiler (deterministic, fail-fast)."""
from __future__ import annotations

from typing import Dict, Any, List


def _sorted_by_name(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("name", ""))


def _env_dict_to_list(env: Dict[str, str]) -> List[Dict[str, str]]:
    return [{"name": key, "value": env[key]} for key in sorted(env.keys())]


def _ports_release_to_runtime(ports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    runtime_ports: List[Dict[str, Any]] = []
    for port in ports:
        runtime_port = {
            "containerPort": port["containerPort"],
            "protocol": port.get("protocol", "tcp"),
        }
        if port.get("name"):
            runtime_port["name"] = port["name"]
        if port.get("hostPort") is not None:
            runtime_port["publishedPort"] = port["hostPort"]
        runtime_ports.append(runtime_port)
    return runtime_ports


def compile_release_to_runtime(
    release_spec: Dict[str, Any],
    revision: int = 1,
    release_id: str | None = None
) -> Dict[str, Any]:
    """Compile ReleaseSpec into RuntimeSpec with deterministic ordering."""
    metadata = release_spec["metadata"]
    namespace = metadata["namespace"]
    name = metadata["name"]
    resolved_release_id = release_id or f"{namespace}.{name}"
    backend = release_spec["backend"]

    runtime = {
        "apiVersion": "xyn.seed/v1",
        "kind": "Runtime",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": dict(sorted(metadata.get("labels", {}).items()))
        },
        "release": {
            "releaseId": resolved_release_id,
            "revision": revision,
            "backend": backend
        },
        "networks": _sorted_by_name(
            [
                {key: value for key, value in network.items() if key != "type"}
                for network in release_spec.get("networks", [])
            ]
        ),
        "volumes": _sorted_by_name(
            [
                {key: value for key, value in volume.items() if key != "type"}
                for volume in release_spec.get("volumes", [])
            ]
        ),
        "deployments": [],
        "services": [],
        "routes": release_spec.get("routes", [])
    }

    for component in _sorted_by_name(release_spec["components"]):
        build = component.get("build")
        image = component.get("image")
        if build and build.get("imageName"):
            image = build["imageName"]
        if not image:
            image = f"{namespace}.{name}.{component['name']}:local"

        containers = [{
            "name": component["name"],
            "image": image,
            "ports": _ports_release_to_runtime(component.get("ports", [])),
            "env": _env_dict_to_list(component.get("env", {})),
            "volumeMounts": [
                {
                    "name": mount["volume"],
                    "mountPath": mount["mountPath"],
                    **({"readOnly": mount["readOnly"]} if "readOnly" in mount else {})
                }
                for mount in component.get("volumeMounts", [])
            ],
            "resources": component.get("resources", {})
        }]

        deployment = {
            "name": component["name"],
            "replicas": component.get("replicas", 1),
            "dependsOn": sorted(component.get("dependsOn", [])),
            "podTemplate": {
                "labels": {"app": component["name"]},
                "containers": containers
            }
        }
        runtime["deployments"].append(deployment)

        ports = component.get("ports", [])
        if ports:
            service_ports = []
            for port in ports:
                service_ports.append({
                    "name": port.get("name"),
                    "port": port.get("hostPort", port["containerPort"]),
                    "targetPort": port["containerPort"],
                    "protocol": port.get("protocol", "tcp")
                })
            runtime["services"].append({
                "name": component["name"],
                "selector": {"app": component["name"]},
                "ports": service_ports
            })

    runtime["deployments"] = _sorted_by_name(runtime["deployments"])
    runtime["services"] = _sorted_by_name(runtime["services"])

    return runtime
