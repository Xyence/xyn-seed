from __future__ import annotations

import os
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

LOG_LEVEL = os.getenv("RUNNER_LOG_LEVEL", "info").lower()
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
)
logger = structlog.get_logger()

app = FastAPI(title="Xyn Runner API", version=os.getenv("RUNNER_VERSION", "dev"))


class ToolInvokeRequest(BaseModel):
    tool: str
    payload: dict


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "version": os.getenv("RUNNER_VERSION", "dev"),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/tools/invoke")
async def tools_invoke(request: ToolInvokeRequest):
    logger.info("tool.invoke", tool=request.tool)
    raise HTTPException(status_code=501, detail="Tool execution not implemented yet")
