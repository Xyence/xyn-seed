"""Seed-owned AI bootstrap handshake into xyn-api."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def ensure_default_agent_via_api() -> None:
    """Request xyn-api to upsert default AI agent state using seed-resolved env."""
    base_url = str(os.getenv("XYN_API_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        logger.warning("Skipping AI bootstrap: XYN_API_BASE_URL is not configured")
        return
    token = str(os.getenv("XYN_INTERNAL_TOKEN") or "").strip()
    if not token:
        logger.warning("Skipping AI bootstrap: XYN_INTERNAL_TOKEN missing")
        return
    url = f"{base_url}/xyn/internal/ai/bootstrap-default-agent"
    try:
        response = requests.post(
            url,
            timeout=15,
            headers={"X-Internal-Token": token, "Content-Type": "application/json"},
            json={},
        )
        if response.status_code >= 400:
            logger.warning("AI bootstrap request failed status=%s body=%s", response.status_code, response.text[:300])
            return
        payload = response.json() if response.content else {}
        logger.info(
            "AI bootstrap ensured default agent provider=%s model=%s key_present=%s",
            payload.get("provider"),
            payload.get("model"),
            payload.get("key_present"),
        )
    except Exception:
        logger.exception("AI bootstrap handshake failed")
