"""Compose renderer for RuntimeSpec."""
from __future__ import annotations

from typing import Dict, Any, List


def _sorted_by_name(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("name", ""))


def render_compose(runtime_spec: Dict[str, Any]) -> str:
    metadata = runtime_spec["metadata"]
    namespace = metadata["namespace"]
    name = metadata["name"]
    release_id = runtime_spec["release"]["releaseId"]
    project_name = f"{namespace}_{name}"

    lines: List[str] = [f"name: {project_name}", "", "services:"]

    networks = [net["name"] for net in _sorted_by_name(runtime_spec.get("networks", []))]
    volumes = [vol["name"] for vol in _sorted_by_name(runtime_spec.get("volumes", []))]

    def _append_yaml_value(lines: List[str], indent: int, key: str, value: Any) -> None:
        prefix = " " * indent
        if isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                lines.append(f"{prefix}  - {item}")
        elif isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            for sub_key in sorted(value.keys()):
                sub_value = value[sub_key]
                if isinstance(sub_value, list):
                    lines.append(f"{prefix}  {sub_key}:")
                    for item in sub_value:
                        lines.append(f"{prefix}    - {item}")
                else:
                    lines.append(f"{prefix}  {sub_key}: {sub_value}")
        else:
            lines.append(f"{prefix}{key}: {value}")

    for deployment in _sorted_by_name(runtime_spec["deployments"]):
        service_name = deployment["name"]
        container = deployment["podTemplate"]["containers"][0]
        lines.append(f"  {service_name}:")
        lines.append(f"    image: {container['image']}")

        env = container.get("env", [])
        if env:
            lines.append("    environment:")
            for env_item in sorted(env, key=lambda item: item["name"]):
                if "value" in env_item:
                    lines.append(f"      {env_item['name']}: {env_item['value']}")
                elif "valueFromSecret" in env_item:
                    lines.append(f"      {env_item['name']}: ${env_item['valueFromSecret']}")

        healthcheck = container.get("healthcheck")
        if healthcheck:
            lines.append("    healthcheck:")
            for key in sorted(healthcheck.keys()):
                _append_yaml_value(lines, 6, key, healthcheck[key])

        ports = container.get("ports", [])
        if ports:
            lines.append("    ports:")
            for port in ports:
                published = port.get("publishedPort")
                container_port = port["containerPort"]
                if published:
                    lines.append(f"      - \"{published}:{container_port}\"")
                else:
                    lines.append(f"      - \"{container_port}\"")

        volume_mounts = container.get("volumeMounts", [])
        if volume_mounts:
            lines.append("    volumes:")
            for mount in volume_mounts:
                lines.append(f"      - {mount['name']}:{mount['mountPath']}")

        depends_on = deployment.get("dependsOn", [])
        if depends_on:
            lines.append("    depends_on:")
            for dependency in sorted(depends_on):
                lines.append(f"      - {dependency}")

        if networks:
            lines.append("    networks:")
            for network in networks:
                lines.append(f"      - {network}")

        labels = {
            **metadata.get("labels", {}),
            "release_id": release_id,
            "revision": runtime_spec["release"]["revision"],
            "service": service_name,
        }
        if labels:
            lines.append("    labels:")
            for label_key in sorted(labels.keys()):
                lines.append(f"      {label_key}: {labels[label_key]}")

        lines.append("")

    if volumes:
        lines.append("volumes:")
        for volume in volumes:
            lines.append(f"  {volume}: {{}}")
        lines.append("")

    if networks:
        lines.append("networks:")
        for network in networks:
            lines.append(f"  {network}: {{}}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
