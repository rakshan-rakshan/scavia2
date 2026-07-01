"""Acefone webhook and endpoint routes."""

import json
import uuid
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pipecat.utils.run_context import set_current_run_id

from api.db import db_client
from api.enums import CallType, WorkflowRunMode
from api.services.telephony.factory import get_telephony_provider_for_run
from api.services.telephony.status_processor import (
    StatusCallbackRequest,
    _process_status_update,
)
from api.utils.common import get_backend_endpoints

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


@router.post("/acefone/status-callback/{workflow_run_id}", include_in_schema=False)
async def handle_acefone_status_callback(workflow_run_id: int, request: Request):
    """Handle Acefone Click-to-Call status callbacks for an outbound run.

    ``AcefoneProvider.initiate_call`` registers this URL as ``status_callback``
    on every outbound call. Mirrors the Twilio handler: load the run, resolve
    its provider, normalize the payload, and hand it to the shared status
    processor (which advances run state / records cost).

    Acefone is a Twilio-clone and posts form-encoded status fields, but some
    deployments post JSON — parse the raw body defensively for either. Always
    returns 200 so the platform does not retry-storm on a transient error.
    """
    set_current_run_id(workflow_run_id)

    raw = await request.body()
    callback_data: Dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                callback_data = parsed
        except Exception:
            callback_data = dict(parse_qsl(raw.decode("utf-8", "ignore")))

    logger.info(
        f"[run {workflow_run_id}] Acefone status callback: {callback_data}"
    )

    workflow_run = await db_client.get_workflow_run_by_id(workflow_run_id)
    if not workflow_run:
        logger.warning(
            f"Workflow run {workflow_run_id} not found for Acefone status callback"
        )
        return {"status": "ignored", "reason": "workflow_run_not_found"}

    workflow = await db_client.get_workflow_by_id(workflow_run.workflow_id)
    if not workflow:
        logger.warning(f"Workflow {workflow_run.workflow_id} not found")
        return {"status": "ignored", "reason": "workflow_not_found"}

    provider = await get_telephony_provider_for_run(
        workflow_run, workflow.organization_id
    )
    parsed_data = provider.parse_status_callback(callback_data)

    status_update = StatusCallbackRequest(
        call_id=parsed_data["call_id"],
        status=parsed_data["status"],
        from_number=parsed_data.get("from_number"),
        to_number=parsed_data.get("to_number"),
        direction=parsed_data.get("direction"),
        duration=parsed_data.get("duration"),
        extra=parsed_data.get("extra", {}),
    )
    await _process_status_update(workflow_run_id, status_update)
    return {"status": "success"}


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


async def build_dynamic_endpoint_response(
    params: Dict[str, Any], request_host: Optional[str] = None
) -> Dict[str, Any]:
    """Resolve an inbound Acefone Voice-Streaming call to a per-call WS URL.

    Acefone's Dynamic endpoint sends the predefined params
    ``callId``/``fromNumber``/``toNumber``/``status`` plus any custom key/value
    pairs configured on the endpoint. We require a ``workflow_id`` custom param
    (the bot to run); optional ``use_draft`` runs the draft definition (for
    pre-publish voice validation) and optional ``telephony_configuration_id``
    selects a specific Acefone config when the org has several.

    Creates an INITIALIZED inbound workflow run and returns the strict envelope
    Acefone requires: ``{"success": true, "wss_url": "wss://..."}`` and nothing
    else. Raises ``ValueError`` when the call can't be resolved (the route turns
    that into a non-200 so the platform hangs up cleanly).
    """
    call_id = params.get("callId") or params.get("call_id") or ""
    from_number = params.get("fromNumber") or params.get("from") or ""
    to_number = params.get("toNumber") or params.get("to") or ""

    raw_workflow_id = params.get("workflow_id") or params.get("workflowId")
    if not raw_workflow_id:
        raise ValueError(
            "Acefone dynamic endpoint requires a 'workflow_id' custom parameter"
        )
    workflow_id = int(raw_workflow_id)

    workflow = await db_client.get_workflow_by_id(workflow_id)
    if not workflow:
        raise ValueError(f"Workflow {workflow_id} not found")

    user_id = workflow.user_id
    organization_id = workflow.organization_id

    # The run must carry a telephony_configuration_id so the WS handler can load
    # Acefone credentials (get_telephony_provider_for_run). Without an Acefone
    # config the handler would fall back to the org default and reject the call
    # with a provider mismatch.
    configs = await db_client.list_telephony_configurations_by_provider(
        organization_id, WorkflowRunMode.ACEFONE.value
    )
    if not configs:
        raise ValueError(
            f"No Acefone telephony configuration for org {organization_id}"
        )

    telephony_configuration_id = configs[0].id
    override_cfg = params.get("telephony_configuration_id")
    if override_cfg:
        try:
            wanted = int(override_cfg)
            telephony_configuration_id = next(
                (c.id for c in configs if c.id == wanted),
                telephony_configuration_id,
            )
        except (TypeError, ValueError):
            pass

    use_draft = _truthy(params.get("use_draft", False))

    numeric_suffix = int(str(uuid.uuid4()).replace("-", "")[:8], 16) % 100000000
    run = await db_client.create_workflow_run(
        f"WR-TEL-IN-{numeric_suffix:08d}",
        workflow_id,
        WorkflowRunMode.ACEFONE.value,
        user_id=user_id,
        call_type=CallType.INBOUND,
        use_draft=use_draft,
        initial_context={
            "caller_number": from_number,
            "called_number": to_number,
            "direction": "inbound",
            "provider": WorkflowRunMode.ACEFONE.value,
            "telephony_configuration_id": telephony_configuration_id,
        },
        gathered_context={"call_id": call_id},
        logs={"acefone_dynamic_endpoint": params},
    )

    # Build the WS URL on the SAME host Acefone dialed (request_host) so the
    # TLS cert matches. Acefone's WS client verifies TLS; deriving the host
    # from BACKEND_API_ENDPOINT can hand back a bare-IP/self-signed origin it
    # cannot connect to (prod serves the API behind a real domain via nginx
    # but BACKEND_API_ENDPOINT may be the IP). Fall back to BACKEND_API_ENDPOINT
    # when there is no request host (internal callers / tests).
    if request_host:
        wss_base = f"wss://{request_host}"
    else:
        _, wss_base = await get_backend_endpoints()
    wss_url = f"{wss_base}/api/v1/telephony/ws/{workflow_id}/{user_id}/{run.id}"
    logger.info(
        f"Acefone dynamic endpoint -> run {run.id} "
        f"(workflow={workflow_id}, use_draft={use_draft}) wss={wss_url}"
    )
    return {"success": True, "wss_url": wss_url}


@router.post("/acefone/dynamic-endpoint", include_in_schema=False)
async def handle_acefone_dynamic_endpoint(request: Request):
    """Acefone Voice-Streaming Dynamic Endpoint resolver.

    Returns ``{"success": true, "wss_url": "wss://..."}`` (HTTP 200, exactly
    those keys, < 2000 ms) or a non-200 to make Acefone decline and hang up.
    """
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    params: Dict[str, Any] = {**dict(request.query_params), **body}
    logger.info(f"Acefone dynamic endpoint request: {params}")

    try:
        return await build_dynamic_endpoint_response(
            params, request_host=request.url.hostname
        )
    except Exception as e:
        logger.error(f"Acefone dynamic endpoint failed: {e}")
        # Non-200 → Acefone declines and hangs up (per the strict contract).
        return JSONResponse(status_code=502, content={"error": str(e)})
