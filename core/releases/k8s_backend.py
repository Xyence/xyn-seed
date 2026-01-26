"""Kubernetes backend stub: validate representability only."""
from __future__ import annotations

from typing import Any, Dict, List


class K8sValidationError(ValueError):
    """Raised when a RuntimeSpec is not representable for K8s."""


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise K8sValidationError(message)


def validate_runtime_spec(runtime_spec: Dict[str, Any]) -> None:
    _ensure(runtime_spec.get("kind") == "Runtime", "RuntimeSpec kind must be 'Runtime'")
    _ensure("metadata" in runtime_spec, "RuntimeSpec metadata is required")
    _ensure("deployments" in runtime_spec, "RuntimeSpec deployments are required")
    _ensure("services" in runtime_spec, "RuntimeSpec services are required")

    for deployment in runtime_spec.get("deployments", []):
        _ensure("name" in deployment, "Deployment name is required")
        pod = deployment.get("podTemplate", {})
        containers = pod.get("containers", [])
        _ensure(len(containers) > 0, f"Deployment {deployment.get('name', '<unknown>')} must have containers")

    for service in runtime_spec.get("services", []):
        _ensure("name" in service, "Service name is required")
        ports = service.get("ports", [])
        _ensure(len(ports) > 0, f"Service {service.get('name', '<unknown>')} must have ports")


__all__ = ["validate_runtime_spec", "K8sValidationError"]
