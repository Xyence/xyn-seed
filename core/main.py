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
from core.api import health, events, runs, artifacts, drafts
from core.ui import ui_events, ui_runs, ui_artifacts
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

# Include UI routers (server-rendered HTML)
app.include_router(ui_events.router, prefix="/ui", tags=["UI - Events"])
app.include_router(ui_runs.router, prefix="/ui", tags=["UI - Runs"])
app.include_router(ui_artifacts.router, prefix="/ui", tags=["UI - Artifacts"])


@app.get("/")
async def root():
    """Root endpoint - redirect to UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/events")


@app.get("/health")
async def root_health():
    """Root health check (non-versioned for convenience)."""
    return {"status": "ok", "version": __version__}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
