"""Xyn Seed Core Service - Main FastAPI Application"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from core import __version__
from core.database import init_db
from core.api import health, events, runs, artifacts, drafts, packs, debug, domain, ops, releases
from core.ui import ui_events, ui_runs, ui_artifacts, ui_domain
from core.middleware import CorrelationIdMiddleware


# Configure logging with correlation ID support
class CorrelationIdFilter(logging.Filter):
    """Add correlation_id to log records if available."""
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = '-'
        return True

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
)

# Add filter to root logger
correlation_filter = CorrelationIdFilter()
logging.getLogger().addFilter(correlation_filter)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting Xyn Seed Core v{__version__}")

    # Initialize database
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    # Register blueprints
    logger.info("Registering blueprints...")
    from core.blueprints import pack_install, pack_upgrade, test_orchestrator, core_migrations_apply_v1  # noqa - Import to register blueprints
    from core.blueprints.registry import list_blueprints
    registered = list_blueprints()
    logger.info(f"Registered {len(registered)} blueprints: {', '.join(registered)}")

    yield

    logger.info("Shutting down Xyn Seed Core")


# Create FastAPI application
app = FastAPI(
    title="Xyn Seed Core",
    description="Xyn Seed Platform Core Service - v0.0",
    version=__version__,
    lifespan=lifespan
)

# Add CORS middleware (permissive for localhost development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add correlation ID middleware
app.add_middleware(CorrelationIdMiddleware)

# Include API routers (versioned)
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(events.router, prefix="/api/v1", tags=["Events"])
app.include_router(runs.router, prefix="/api/v1", tags=["Runs"])
app.include_router(artifacts.router, prefix="/api/v1", tags=["Artifacts"])
app.include_router(drafts.router, prefix="/api/v1", tags=["Drafts"])
app.include_router(packs.router, prefix="/api/v1", tags=["Packs"])
app.include_router(debug.router, prefix="/api/v1", tags=["Debug"])
app.include_router(domain.router, prefix="/api/v1", tags=["Domain"])
app.include_router(ops.router, prefix="/api/v1", tags=["Operations"])
app.include_router(releases.router, prefix="/api/v1", tags=["Releases"])

# Include UI routers (server-rendered HTML)
app.include_router(ui_events.router, prefix="/ui", tags=["UI - Events"])
app.include_router(ui_runs.router, prefix="/ui", tags=["UI - Runs"])
app.include_router(ui_artifacts.router, prefix="/ui", tags=["UI - Artifacts"])
app.include_router(ui_domain.router, prefix="/ui", tags=["UI - Domain"])


@app.get("/")
async def root():
    """Root endpoint - redirect to UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/events")


@app.get("/health")
async def root_health():
    """Root health check (non-versioned for convenience)."""
    return {"status": "ok", "version": __version__}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.

    Exposes runtime metrics collected by the metrics collector:
    - Queue health (depth, ready/future, oldest waiting)
    - Lease health (expired vs active leases)
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi import Response

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
