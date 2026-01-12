"""Domain exceptions for Xyn Seed"""
from typing import Optional, Dict, Any
from uuid import UUID


class LostLeaseError(Exception):
    """Raised when a worker loses ownership/lease of a run during execution."""
    pass


class PackInstallationError(Exception):
    """Base exception for pack installation errors."""

    def __init__(self, message: str, pack_ref: str, env_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.pack_ref = pack_ref
        self.env_id = env_id
        self.details = details or {}


class PackAlreadyInstalledError(PackInstallationError):
    """Raised when attempting to install a pack that is already installed."""

    def __init__(self, pack_ref: str, env_id: str, installation_id: UUID, installed_by_run_id: Optional[UUID] = None):
        super().__init__(
            f"Pack '{pack_ref}' is already installed in environment '{env_id}'",
            pack_ref,
            env_id,
            {
                "existing_installation_id": str(installation_id),
                "existing_run_id": str(installed_by_run_id) if installed_by_run_id else None
            }
        )
        self.installation_id = installation_id
        self.installed_by_run_id = installed_by_run_id


class PackInstallationInProgressError(PackInstallationError):
    """Raised when attempting to install a pack that is currently being installed."""

    def __init__(self, pack_ref: str, env_id: str, installation_id: UUID, installing_by_run_id: Optional[UUID] = None):
        super().__init__(
            f"Pack '{pack_ref}' installation is already in progress in environment '{env_id}'",
            pack_ref,
            env_id,
            {
                "existing_installation_id": str(installation_id),
                "existing_run_id": str(installing_by_run_id) if installing_by_run_id else None
            }
        )
        self.installation_id = installation_id
        self.installing_by_run_id = installing_by_run_id


class PackInstallationFailedError(PackInstallationError):
    """Raised when attempting to install a pack that previously failed."""

    def __init__(self, pack_ref: str, env_id: str, installation_id: UUID, error_details: Optional[Dict[str, Any]] = None, last_error_at=None):
        super().__init__(
            f"Pack '{pack_ref}' installation previously failed in environment '{env_id}'. Retry or cleanup required.",
            pack_ref,
            env_id,
            {
                "existing_installation_id": str(installation_id),
                "error": error_details,
                "last_error_at": last_error_at.isoformat() if last_error_at else None
            }
        )
        self.installation_id = installation_id
        self.error_details = error_details
        self.last_error_at = last_error_at


class PackNotFoundError(Exception):
    """Raised when a pack reference is not found in the registry."""

    def __init__(self, pack_ref: str):
        super().__init__(f"Pack not found: {pack_ref}")
        self.pack_ref = pack_ref


class PackNotInstalledError(Exception):
    """Raised when attempting to upgrade a pack that is not installed."""

    def __init__(self, pack_ref: str, env_id: str):
        super().__init__(f"Pack '{pack_ref}' is not installed in environment '{env_id}'")
        self.pack_ref = pack_ref
        self.env_id = env_id


class PackInstallationInvariantError(Exception):
    """Raised when a required invariant is violated during installation."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


class PackInstallationConflictError(Exception):
    """Raised when attempting to finalize an installation owned by a different run."""

    def __init__(self, message: str, expected_run_id: Optional[UUID] = None, actual_run_id: Optional[UUID] = None):
        super().__init__(message)
        self.expected_run_id = expected_run_id
        self.actual_run_id = actual_run_id
