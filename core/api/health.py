"""Health check API endpoints"""
import time
from datetime import datetime
from fastapi import APIRouter

from core import __version__
from core.schemas import HealthResponse

router = APIRouter()

# Track startup time for uptime calculation
_startup_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint.

    Returns current system status and version information.
    """
    uptime = int(time.time() - _startup_time)

    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=uptime,
        now=datetime.utcnow()
    )
