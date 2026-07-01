"""Unit tests for the server-side lead-delivery and Supabase call-logging hooks.

Self-contained: the DB client and HTTP client are mocked, and the gating
constants are patched, so these tests need no real DB, network, or env beyond
what conftest already loads for import.

Covers:
  deliver_lead_for_run:
    (a) unset webhook OR non-allowlisted workflow -> no POST
    (b) no visit_datetime in gathered_context -> no POST (new gate)
    (c) allowlisted workflow + visit_datetime + set webhook -> POSTs full payload
    (d) HTTP/unexpected errors are swallowed (return False, never raise)

  log_call_to_supabase:
    (e) unset SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY -> no-op
    (f) non-allowlisted workflow -> no-op
    (g) allowlisted workflow -> POSTs full payload with service-role headers
    (h) errors are swallowed (return False, never raise)

  build_lead_payload / build_supabase_payload:
    (i) field mapping and new fields (intent, visit_datetime)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.services.lead_delivery import (
    build_lead_payload,
    build_supabase_payload,
    deliver_lead_for_run,
    log_call_to_supabase,
)

DELIVERY = "api.services.lead_delivery.delivery"
SUPABASE_LOGGER = "api.services.lead_delivery.supabase_logger"


@dataclass
class FakeWorkflowRun:
    """Minimal stand-in for WorkflowRunModel (only fields the hooks read)."""

    id: int = 99
    workflow_id: int = 12
    mode: str = "acefone"
    gathered_context: Dict[str, Any] = field(default_factory=dict)
    cost_info: Dict[str, Any] = field(default_factory=dict)
    recording_url: Optional[str] = None
    transcript_url: Optional[str] = None
    created_at: Optional[datetime] = None


def _sample_gathered_context(*, with_site_visit: bool = False) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+919812345678",
        "purpose": "investment",
        "config_interest": "3 BHK",
        "budget_band": "5-8 Cr",
        "timeline": "3-6 months",
        "job": "doctor",
        "whatsapp_ok": True,
        "outcome": "site_visit_booked" if with_site_visit else "handoff",
        "summary": "NRI investor interested in 3 BHK.",
        "intent": "3 BHK Brundavan Heights, investment, ₹5-8 Cr, 3-6mo",
        # Noise that must NOT leak into the lead payload:
        "call_tags": ["user_speech"],
        "trace_url": "https://trace.example/abc",
    }
    if with_site_visit:
        ctx["visit_datetime"] = "2026-07-15T10:00:00+05:30"
    return ctx


def _leadgen_gathered_context(*, score: int, with_site_visit: bool = False):
    """An IVR→AI LeadGen run's gathered_context (Track 1 fields)."""
    ctx: Dict[str, Any] = {
        "name": "Ravi Kumar",
        "phone": "+919800011122",
        "property_type": "plot",
        "budget_band": "plot:20-50k/sqyd",
        "location_zone": "south",
        "micro_location": "Shadnagar",
        "purpose": "investment",
        "timeline": "this month",
        "finance_type": "own funds",
        "stage_of_search": "not started",
        "decision_maker": True,
        "whatsapp_ok": True,
        "intent": "Plot in Shadnagar, ₹20-50k/sqyd, investment, buying this month",
        "outcome": "handoff",
        "summary": "Investor wants a plot in Shadnagar, ready this month.",
        "score": score,
    }
    if with_site_visit:
        ctx["visit_datetime"] = "2026-07-20T11:00:00+05:30"
    return ctx


def _patch_delivery_config(url, token, allowlist):
    """Patch the gating constants as imported into the delivery module."""
    return patch.multiple(
        DELIVERY,
        LEAD_DELIVERY_WEBHOOK_URL=url,
        LEAD_DELIVERY_WEBHOOK_TOKEN=token,
        LEAD_DELIVERY_WORKFLOW_IDS=allowlist,
    )


def _patch_supabase_config(supabase_url, service_role_key, allowlist, campaign="maira"):
    return patch.multiple(
        SUPABASE_LOGGER,
        SUPABASE_URL=supabase_url,
        SUPABASE_SERVICE_ROLE_KEY=service_role_key,
        SUPABASE_LOG_WORKFLOW_IDS=allowlist,
        SUPABASE_LOG_CAMPAIGN=campaign,
    )


def _mock_httpx_client(response_or_exc):
    client = MagicMock()
    if isinstance(response_or_exc, Exception):
        client.post = AsyncMock(side_effect=response_or_exc)
    else:
        client.post = AsyncMock(return_value=response_or_exc)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory, client


def _ok_response(status_code: int = 201):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# --------------------------------------------------------------------------- #
# build_lead_payload — field mapping (includes new fields)
# --------------------------------------------------------------------------- #


def test_build_lead_payload_maps_fields_and_metadata():
    run = FakeWorkflowRun(gathered_context=_sample_gathered_context(with_site_visit=True))
    payload = build_lead_payload(run, transcript="Visitor: hi\nMaira: hello")

    assert payload["name"] == "Asha Rao"
    assert payload["email"] == "asha@example.com"
    assert payload["phone"] == "+919812345678"
    assert payload["purpose"] == "investment"
    assert payload["config_interest"] == "3 BHK"
    assert payload["budget_band"] == "5-8 Cr"
    assert payload["timeline"] == "3-6 months"
    assert payload["job"] == "doctor"
    assert payload["whatsapp_ok"] is True
    assert payload["outcome"] == "site_visit_booked"
    assert payload["summary"] == "NRI investor interested in 3 BHK."
    # New fields
    assert payload["intent"] == "3 BHK Brundavan Heights, investment, ₹5-8 Cr, 3-6mo"
    assert payload["visit_datetime"] == "2026-07-15T10:00:00+05:30"
    # Run metadata
    assert payload["modality"] == "acefone"
    assert payload["workflow_run_id"] == 99
    assert payload["source"] == "scaiva-telephony"
    assert payload["transcript"] == "Visitor: hi\nMaira: hello"
    assert "received_at" in payload and payload["received_at"]
    # Noise must not leak
    assert "call_tags" not in payload
    assert "trace_url" not in payload


def test_build_lead_payload_missing_fields_become_none():
    run = FakeWorkflowRun(gathered_context={"name": "Solo"})
    payload = build_lead_payload(run)

    assert payload["name"] == "Solo"
    assert payload["email"] is None
    assert payload["intent"] is None
    assert payload["visit_datetime"] is None
    assert payload["transcript"] == ""


# --------------------------------------------------------------------------- #
# build_supabase_payload — full call metadata
# --------------------------------------------------------------------------- #


def test_build_supabase_payload_includes_call_metadata():
    run = FakeWorkflowRun(
        id=42,
        workflow_id=12,
        mode="acefone",
        gathered_context={
            **_sample_gathered_context(with_site_visit=True),
            "call_disposition": "answered",
            "duration_seconds": 120,
        },
        cost_info={"total_usd": 0.045, "duration_seconds": 120},
        recording_url="recordings/42.wav",
        transcript_url="transcripts/42.txt",
        created_at=datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    # Patch campaign constant for deterministic assertion
    with patch(f"{SUPABASE_LOGGER}.SUPABASE_LOG_CAMPAIGN", "maira"):
        payload = build_supabase_payload(run, transcript="hello")

    assert payload["campaign"] == "maira"
    assert payload["workflow_id"] == "42"
    assert payload["call_mode"] == "acefone"
    assert payload["call_disposition"] == "answered"
    assert payload["call_duration_seconds"] == 120
    assert payload["call_cost_usd"] == 0.045
    assert payload["recording_url"] == "recordings/42.wav"
    assert payload["transcript_url"] == "transcripts/42.txt"
    assert payload["transcript"] == "hello"
    assert payload["intent"] == "3 BHK Brundavan Heights, investment, ₹5-8 Cr, 3-6mo"
    assert payload["visit_datetime"] == "2026-07-15T10:00:00+05:30"
    assert payload["visit_booked"] is True
    assert "2026-07-01" in payload["created_at"]


def test_build_supabase_payload_maps_leadgen_fields():
    """LeadGen funnel fields land in their columns; score mirrors to intent_score."""
    run = FakeWorkflowRun(
        id=51,
        workflow_id=15,
        mode="acefone",
        gathered_context=_leadgen_gathered_context(score=84),
    )
    with patch(f"{SUPABASE_LOGGER}.SUPABASE_LOG_CAMPAIGN", "leadgen"):
        payload = build_supabase_payload(run, transcript="hello")

    # Direct columns
    assert payload["property_type"] == "plot"
    assert payload["location_zone"] == "south"
    assert payload["decision_maker"] is True
    # 0–100 score + mirrored 0–10 intent_score
    assert payload["score"] == 84
    assert payload["intent_score"] == 8
    # Human-readable location prefers the specific area
    assert payload["location_news"] == "Shadnagar"
    # Overflow fields folded into raw
    assert payload["raw"]["finance_type"] == "own funds"
    assert payload["raw"]["stage_of_search"] == "not started"
    assert payload["raw"]["micro_location"] == "Shadnagar"
    assert payload["campaign"] == "leadgen"


def test_build_supabase_payload_score_absent_is_none():
    """Legacy runs with no score: score is None, intent_score untouched."""
    run = FakeWorkflowRun(gathered_context=_sample_gathered_context())
    payload = build_supabase_payload(run)
    assert payload["score"] is None
    assert "intent_score" not in payload  # not overwritten for legacy rows
    assert payload["property_type"] is None


def test_build_supabase_payload_clamps_score():
    run = FakeWorkflowRun(gathered_context=_leadgen_gathered_context(score=140))
    payload = build_supabase_payload(run)
    assert payload["score"] == 100
    assert payload["intent_score"] == 10


def test_build_supabase_payload_maps_maira_intent_score_and_location():
    """Maira/Maira2 agents emit intent_score (0–10) + location_news directly — both flow through."""
    run = FakeWorkflowRun(
        workflow_id=14,
        gathered_context={
            "property_type": "Flat",
            "budget_band": "5-6cr",
            "location_news": "West",
            "timeline": "1-3mo",
            "decision_maker": True,
            "intent_score": 8,
            "visit_datetime": "Saturday 28 June, 11am",
            "outcome": "booked_visit",
            "intent": "Flat in West, 5-6cr, books a visit Saturday",
        },
    )
    payload = build_supabase_payload(run)
    assert payload["intent_score"] == 8  # agent's 0–10 score passes through
    assert payload["score"] is None  # no LeadGen 0–100 score on Maira
    assert payload["location_news"] == "West"
    assert payload["property_type"] == "Flat"
    assert payload["decision_maker"] is True
    assert payload["intent"] == "Flat in West, 5-6cr, books a visit Saturday"
    assert payload["outcome"] == "booked_visit"


# --------------------------------------------------------------------------- #
# (a) deliver_lead_for_run: gating — unset webhook / non-allowlisted
# --------------------------------------------------------------------------- #


async def test_no_post_when_webhook_unset():
    factory, client = _mock_httpx_client(_ok_response())
    with (
        _patch_delivery_config(None, None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock()
        delivered = await deliver_lead_for_run(99)

    assert delivered is False
    client.post.assert_not_called()
    mock_db.get_workflow_run_by_id.assert_not_called()


async def test_no_post_when_workflow_not_allowlisted():
    run = FakeWorkflowRun(
        workflow_id=7,
        gathered_context=_sample_gathered_context(with_site_visit=True),
    )
    factory, client = _mock_httpx_client(_ok_response())
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({11, 12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(99)

    assert delivered is False
    client.post.assert_not_called()


# --------------------------------------------------------------------------- #
# (b) deliver_lead_for_run: visit_datetime gate
# --------------------------------------------------------------------------- #


async def test_no_post_when_no_visit_datetime():
    """Google Sheet must NOT receive calls that didn't result in a site visit."""
    run = FakeWorkflowRun(
        workflow_id=12,
        gathered_context=_sample_gathered_context(with_site_visit=False),
    )
    factory, client = _mock_httpx_client(_ok_response())
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(99)

    assert delivered is False
    client.post.assert_not_called()


async def test_no_post_for_hot_leadgen_lead_without_visit():
    """Sheet is visit-booked ONLY: even a HOT lead (score 88) with no visit is NOT sent.
    It is still logged to Supabase by log_call_to_supabase() — just not the Sheet."""
    run = FakeWorkflowRun(
        workflow_id=15,
        gathered_context=_leadgen_gathered_context(score=88, with_site_visit=False),
    )
    factory, client = _mock_httpx_client(_ok_response())
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({15})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(99)

    assert delivered is False
    client.post.assert_not_called()


async def test_posts_leadgen_fields_when_visit_booked():
    """A LeadGen lead that booked a visit reaches the Sheet with the new fields."""
    run = FakeWorkflowRun(
        id=77,
        workflow_id=15,
        gathered_context=_leadgen_gathered_context(score=88, with_site_visit=True),
    )
    factory, client = _mock_httpx_client(_ok_response(200))
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({15})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(77, transcript="hi")

    assert delivered is True
    client.post.assert_awaited_once()
    _args, kwargs = client.post.call_args
    payload = kwargs["json"]
    assert payload["property_type"] == "plot"
    assert payload["location_zone"] == "south"
    assert payload["score"] == 88
    assert payload["visit_datetime"] == "2026-07-20T11:00:00+05:30"


# --------------------------------------------------------------------------- #
# (c) deliver_lead_for_run: full path — site visit booked, posts full payload
# --------------------------------------------------------------------------- #


async def test_posts_payload_with_token_when_site_visit_booked():
    run = FakeWorkflowRun(
        id=42,
        workflow_id=12,
        mode="acefone",
        gathered_context=_sample_gathered_context(with_site_visit=True),
    )
    factory, client = _mock_httpx_client(_ok_response(200))
    with (
        _patch_delivery_config("https://hook.example/exec", "s3cr3t", frozenset({11, 12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(42, transcript="hello world")

    assert delivered is True
    client.post.assert_awaited_once()

    args, kwargs = client.post.call_args
    posted_url = args[0] if args else kwargs.get("url")
    assert posted_url == "https://hook.example/exec?token=s3cr3t"

    payload = kwargs["json"]
    assert payload["workflow_run_id"] == 42
    assert payload["name"] == "Asha Rao"
    assert payload["intent"] == "3 BHK Brundavan Heights, investment, ₹5-8 Cr, 3-6mo"
    assert payload["visit_datetime"] == "2026-07-15T10:00:00+05:30"
    assert payload["transcript"] == "hello world"


async def test_posts_without_token_when_token_unset():
    run = FakeWorkflowRun(
        gathered_context=_sample_gathered_context(with_site_visit=True)
    )
    factory, client = _mock_httpx_client(_ok_response(200))
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(99)

    assert delivered is True
    args, kwargs = client.post.call_args
    posted_url = args[0] if args else kwargs.get("url")
    assert posted_url == "https://hook.example/exec"


# --------------------------------------------------------------------------- #
# (d) deliver_lead_for_run: errors are swallowed
# --------------------------------------------------------------------------- #


async def test_http_status_error_is_swallowed():
    run = FakeWorkflowRun(
        gathered_context=_sample_gathered_context(with_site_visit=True)
    )
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.text = "boom"
    resp = MagicMock()
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
    )
    factory, _client = _mock_httpx_client(resp)

    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(99)

    assert delivered is False


async def test_request_error_is_swallowed():
    run = FakeWorkflowRun(
        gathered_context=_sample_gathered_context(with_site_visit=True)
    )
    factory, _client = _mock_httpx_client(
        httpx.ConnectError("unreachable", request=MagicMock())
    )

    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        delivered = await deliver_lead_for_run(99)

    assert delivered is False


async def test_db_lookup_error_is_swallowed():
    factory, client = _mock_httpx_client(_ok_response())
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(side_effect=RuntimeError("db down"))
        delivered = await deliver_lead_for_run(99)

    assert delivered is False
    client.post.assert_not_called()


async def test_run_not_found_is_noop():
    factory, client = _mock_httpx_client(_ok_response())
    with (
        _patch_delivery_config("https://hook.example/exec", None, frozenset({12})),
        patch(f"{DELIVERY}.db_client") as mock_db,
        patch(f"{DELIVERY}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=None)
        delivered = await deliver_lead_for_run(99)

    assert delivered is False
    client.post.assert_not_called()


# --------------------------------------------------------------------------- #
# (e/f) log_call_to_supabase: gating
# --------------------------------------------------------------------------- #


async def test_supabase_log_skipped_when_url_unset():
    factory, client = _mock_httpx_client(_ok_response(201))
    with (
        _patch_supabase_config(None, "key", frozenset({12})),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock()
        logged = await log_call_to_supabase(99)

    assert logged is False
    client.post.assert_not_called()
    mock_db.get_workflow_run_by_id.assert_not_called()


async def test_supabase_log_skipped_when_key_unset():
    factory, client = _mock_httpx_client(_ok_response(201))
    with (
        _patch_supabase_config("https://xxx.supabase.co", None, frozenset({12})),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock()
        logged = await log_call_to_supabase(99)

    assert logged is False
    client.post.assert_not_called()


async def test_supabase_log_skipped_when_workflow_not_allowlisted():
    run = FakeWorkflowRun(workflow_id=7, gathered_context=_sample_gathered_context())
    factory, client = _mock_httpx_client(_ok_response(201))
    with (
        _patch_supabase_config("https://xxx.supabase.co", "svc_key", frozenset({11, 12})),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        logged = await log_call_to_supabase(99)

    assert logged is False
    client.post.assert_not_called()


# --------------------------------------------------------------------------- #
# (g) log_call_to_supabase: full path — posts to Supabase with correct headers
# --------------------------------------------------------------------------- #


async def test_supabase_log_posts_with_service_role_headers():
    run = FakeWorkflowRun(
        id=42,
        workflow_id=12,
        mode="acefone",
        gathered_context=_sample_gathered_context(with_site_visit=True),
        cost_info={"total_usd": 0.05},
    )
    factory, client = _mock_httpx_client(_ok_response(201))
    with (
        _patch_supabase_config(
            "https://abc.supabase.co", "svc_role_key", frozenset({12})
        ),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        logged = await log_call_to_supabase(42, transcript="full transcript text")

    assert logged is True
    client.post.assert_awaited_once()

    args, kwargs = client.post.call_args
    posted_url = args[0] if args else kwargs.get("url")
    assert posted_url == "https://abc.supabase.co/rest/v1/leads"

    headers = kwargs["headers"]
    assert headers["apikey"] == "svc_role_key"
    assert headers["Authorization"] == "Bearer svc_role_key"
    assert "merge-duplicates" in headers["Prefer"]

    payload = kwargs["json"]
    assert payload["campaign"] == "maira"
    assert payload["workflow_id"] == "42"
    assert payload["name"] == "Asha Rao"
    assert payload["intent"] == "3 BHK Brundavan Heights, investment, ₹5-8 Cr, 3-6mo"
    assert payload["visit_datetime"] == "2026-07-15T10:00:00+05:30"
    assert payload["transcript"] == "full transcript text"
    assert payload["call_cost_usd"] == 0.05


async def test_supabase_log_fires_even_without_site_visit():
    """Supabase logging is unconditional — no visit_datetime gate."""
    run = FakeWorkflowRun(
        workflow_id=12,
        gathered_context=_sample_gathered_context(with_site_visit=False),
    )
    factory, client = _mock_httpx_client(_ok_response(201))
    with (
        _patch_supabase_config("https://abc.supabase.co", "svc_key", frozenset({12})),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        logged = await log_call_to_supabase(99)

    assert logged is True
    client.post.assert_awaited_once()


# --------------------------------------------------------------------------- #
# (h) log_call_to_supabase: errors are swallowed
# --------------------------------------------------------------------------- #


async def test_supabase_log_http_error_swallowed():
    run = FakeWorkflowRun(gathered_context=_sample_gathered_context())
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.text = "db error"
    resp = MagicMock()
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
    )
    factory, _client = _mock_httpx_client(resp)

    with (
        _patch_supabase_config("https://abc.supabase.co", "svc_key", frozenset({12})),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        logged = await log_call_to_supabase(99)  # must not raise

    assert logged is False


async def test_supabase_log_request_error_swallowed():
    run = FakeWorkflowRun(gathered_context=_sample_gathered_context())
    factory, _client = _mock_httpx_client(
        httpx.ConnectError("unreachable", request=MagicMock())
    )

    with (
        _patch_supabase_config("https://abc.supabase.co", "svc_key", frozenset({12})),
        patch(f"{SUPABASE_LOGGER}.db_client") as mock_db,
        patch(f"{SUPABASE_LOGGER}.httpx.AsyncClient", factory),
    ):
        mock_db.get_workflow_run_by_id = AsyncMock(return_value=run)
        logged = await log_call_to_supabase(99)  # must not raise

    assert logged is False
