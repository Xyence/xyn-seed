"""Middleware for request processing."""
import uuid
import logging
import contextvars
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Context variable for correlation ID (accessible throughout request lifecycle)
correlation_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    'correlation_id', default=None
)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to handle X-Correlation-Id header propagation.

    Behavior:
    - If request includes X-Correlation-Id header, use it
    - If not, generate a new UUID
    - Store in request.state for use by endpoints
    - Add to response headers
    - Include in logging context
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get("x-correlation-id")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in request state for access by endpoints
        request.state.correlation_id = correlation_id

        # Store in context variable for logging and other utilities
        correlation_id_context.set(correlation_id)

        # Log with correlation ID
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={"correlation_id": correlation_id}
        )

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-Id"] = correlation_id

        # Log completion
        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra={"correlation_id": correlation_id}
        )

        return response
