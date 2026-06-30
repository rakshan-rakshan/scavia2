import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from api.enums import CallType, WorkflowRunMode
from api.services.telephony.providers.acefone.routes import (
    build_dynamic_endpoint_response,
    handle_acefone_dynamic_endpoint,
)


def _json_request(payload: dict, query: str = "") -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "server": ("example.test", 443),
            "path": "/api/v1/telephony/acefone/dynamic-endpoint",
            "query_string": query.encode("utf-8"),
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


def _patch_db(*, configs):
    """Patch the routes module's db_client + get_backend_endpoints.

    Returns the patched db_client mock so tests can assert call args.
    """
    db_client = patch(
        "api.services.telephony.providers.acefone.routes.db_client"
    ).start()
    db_client.get_workflow_by_id = AsyncMock(
        return_value=SimpleNamespace(id=12, user_id=1, organization_id=1)
    )
    db_client.list_telephony_configurations_by_provider = AsyncMock(
        return_value=configs
    )
    db_client.create_workflow_run = AsyncMock(
        return_value=SimpleNamespace(id=999)
    )
    backend = patch(
        "api.services.telephony.providers.acefone.routes.get_backend_endpoints",
        new_callable=AsyncMock,
        return_value=("https://maira.test", "wss://maira.test"),
    ).start()
    return db_client, backend


@pytest.mark.asyncio
async def test_dynamic_endpoint_returns_strict_envelope():
    db_client, _ = _patch_db(configs=[SimpleNamespace(id=5)])
    try:
        result = await handle_acefone_dynamic_endpoint(
            _json_request(
                {
                    "callId": "CA-1",
                    "fromNumber": "+919999999999",
                    "toNumber": "+918888888888",
                    "status": "answered",
                    "workflow_id": 12,
                    "use_draft": "true",
                }
            )
        )
    finally:
        patch.stopall()

    # Strict contract: HTTP 200, exactly {success, wss_url}, nothing else.
    # wss host is derived from the request host (example.test in this scope),
    # not BACKEND_API_ENDPOINT, so the URL Acefone receives matches the cert
    # of the domain it dialed.
    assert result == {
        "success": True,
        "wss_url": "wss://example.test/api/v1/telephony/ws/12/1/999",
    }
    assert set(result.keys()) == {"success", "wss_url"}

    db_client.create_workflow_run.assert_awaited_once()
    _, kwargs = db_client.create_workflow_run.call_args
    assert kwargs["use_draft"] is True
    assert kwargs["call_type"] is CallType.INBOUND
    ctx = kwargs["initial_context"]
    assert ctx["provider"] == WorkflowRunMode.ACEFONE.value
    assert ctx["telephony_configuration_id"] == 5
    assert ctx["caller_number"] == "+919999999999"
    assert ctx["called_number"] == "+918888888888"


@pytest.mark.asyncio
async def test_dynamic_endpoint_defaults_to_published_when_no_use_draft():
    db_client, _ = _patch_db(configs=[SimpleNamespace(id=5)])
    try:
        result = await build_dynamic_endpoint_response(
            {"callId": "CA-2", "toNumber": "+918888888888", "workflow_id": "12"}
        )
    finally:
        patch.stopall()

    assert result["success"] is True
    _, kwargs = db_client.create_workflow_run.call_args
    assert kwargs["use_draft"] is False


@pytest.mark.asyncio
async def test_dynamic_endpoint_missing_workflow_id_returns_non_200():
    _patch_db(configs=[SimpleNamespace(id=5)])
    try:
        response = await handle_acefone_dynamic_endpoint(
            _json_request({"callId": "CA-3", "toNumber": "+918888888888"})
        )
    finally:
        patch.stopall()

    # Non-200 makes Acefone decline + hang up cleanly.
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_dynamic_endpoint_no_acefone_config_returns_non_200():
    _patch_db(configs=[])
    try:
        response = await handle_acefone_dynamic_endpoint(
            _json_request({"callId": "CA-4", "workflow_id": 12})
        )
    finally:
        patch.stopall()

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_build_response_reads_query_string_fallback():
    _patch_db(configs=[SimpleNamespace(id=7)])
    try:
        # workflow_id arriving via query string (GET-style dynamic endpoint).
        result = await handle_acefone_dynamic_endpoint(
            _json_request({}, query="workflow_id=12&callId=CA-5")
        )
    finally:
        patch.stopall()

    assert result == {
        "success": True,
        "wss_url": "wss://example.test/api/v1/telephony/ws/12/1/999",
    }
