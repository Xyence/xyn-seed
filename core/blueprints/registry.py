"""Blueprint registry - resolves blueprint refs to implementations"""
from typing import Dict, Callable, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BlueprintRegistry:
    """Registry for blueprint implementations."""

    def __init__(self):
        self._blueprints: Dict[str, Callable] = {}

    def register(self, blueprint_ref: str, implementation: Callable):
        """Register a blueprint implementation.

        Args:
            blueprint_ref: Blueprint reference (e.g., 'core.pack.install@v1')
            implementation: Callable that implements the blueprint
        """
        self._blueprints[blueprint_ref] = implementation
        logger.info(f"Registered blueprint: {blueprint_ref}")

    def get(self, blueprint_ref: str) -> Optional[Callable]:
        """Get blueprint implementation.

        Args:
            blueprint_ref: Blueprint reference

        Returns:
            Blueprint implementation callable or None if not found
        """
        return self._blueprints.get(blueprint_ref)

    def list_blueprints(self) -> list[str]:
        """List all registered blueprint refs."""
        return sorted(self._blueprints.keys())


# Global registry instance
_registry = BlueprintRegistry()


def register_blueprint(blueprint_ref: str):
    """Decorator to register a blueprint implementation.

    Example:
        @register_blueprint('core.pack.install@v1')
        async def install_pack(ctx, inputs):
            # Implementation
            pass
    """
    def decorator(func: Callable):
        _registry.register(blueprint_ref, func)
        return func
    return decorator


def get_blueprint(blueprint_ref: str) -> Optional[Callable]:
    """Get a blueprint implementation by reference."""
    return _registry.get(blueprint_ref)


def list_blueprints() -> list[str]:
    """List all registered blueprints."""
    return _registry.list_blueprints()
