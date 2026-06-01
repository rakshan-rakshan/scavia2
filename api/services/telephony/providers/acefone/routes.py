"""Acefone webhook and endpoint routes."""

import json

from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter()


@router.post("/acefone/webhook", include_in_schema=False)
async def handle_acefone_webhook(request: Request):
    """Handle Acefone webhook events (status callbacks, etc.)."""
    try:
        data = await request.json()
    except Exception:
        data = await request.body()
    logger.info(f"Acefone webhook received: {data}")
    return {"status": "ok"}


@router.post("/acefone/dynamic-endpoint", include_in_schema=False)
async def handle_acefone_dynamic_endpoint(request: Request):
    """Acefone Dynamic Endpoint resolver.

    Acefone calls this with callId, fromNumber, toNumber, etc.
    Must return ``{"success": true, "wss_url": "wss://..."}``.
    """
    try:
        data = await request.json()
    except Exception:
        data = await request.body()
        data = {}

    logger.info(f"Acefone dynamic endpoint request: {data}")

    wss_url = f"wss://{request.url.hostname}/api/v1/telephony/acefone/stream"

    return {"success": True, "wss_url": wss_url}
