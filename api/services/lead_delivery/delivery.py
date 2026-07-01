"""Build and deliver a structured lead for a completed workflow run.

This mirrors the maira-microsite lead contract (``app/api/lead/route.ts`` +
``lib/leads.ts``) so leads from phone calls land in the same Google Sheet as
the browser sessions. The microsite delivers leads client-side; telephony has
no browser and ends server-side, so this runs in the post-call worker.

Gating (all enforced in :func:`deliver_lead_for_run`):
  * ``LEAD_DELIVERY_WEBHOOK_URL`` must be set, else no-op.
  * the run's ``workflow_id`` must be in ``LEAD_DELIVERY_WORKFLOW_IDS``, else no-op.

Delivery is fully exception-guarded: any failure (DB lookup, HTTP error,
timeout, unexpected exception) is logged and swallowed. It must never break or
delay call completion.
"""

from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from api.constants import (
    LEAD_DELIVERY_WEBHOOK_TOKEN,
    LEAD_DELIVERY_WEBHOOK_URL,
    LEAD_DELIVERY_WORKFLOW_IDS,
)
from api.db import db_client
from api.db.models import WorkflowRunModel

# Lead fields lifted from gathered_context, matching the microsite's Lead shape
# (maira-microsite/lib/leads.ts). Keys absent from gathered_context map to None.
# intent and visit_datetime are new fields the outbound agent populates.
_LEAD_FIELDS = (
    "name",
    "email",
    "phone",
    "purpose",
    "config_interest",
    "budget_band",
    "timeline",
    "job",
    "whatsapp_ok",
    "outcome",
    "summary",
    "intent",
    "visit_datetime",
)

# LeadGen funnel fields (IVR→AI tracks). Carried to the Sheet too so consultants
# see the full lead on the rows that do get delivered. Absent from legacy runs → None.
_LEADGEN_FIELDS = (
    "property_type",
    "location_zone",
    "micro_location",
    "finance_type",
    "stage_of_search",
    "decision_maker",
    "score",
)

# Webhook POST timeout. Matches the existing webhook-node executor in
# api/tasks/run_integrations.py.
_HTTP_TIMEOUT_SECONDS = 30.0


def build_lead_payload(
    workflow_run: WorkflowRunModel,
    transcript: Optional[str] = None,
) -> dict[str, Any]:
    """Build the lead JSON payload from a finished run + transcript.

    Maps ``gathered_context`` into the same field names the microsite uses, and
    adds run metadata (modality, workflow_run_id, source, received_at) plus the
    transcript text. Unknown/missing structured fields are ``None`` so the
    Google Sheet leaves those cells empty.
    """
    gathered = workflow_run.gathered_context or {}

    payload: dict[str, Any] = {field: gathered.get(field) for field in _LEAD_FIELDS}

    # LeadGen funnel fields (None for legacy maira/maira2 runs).
    for f in _LEADGEN_FIELDS:
        payload[f] = gathered.get(f)

    # modality: the run's transport mode (e.g. "acefone", "twilio", "webrtc").
    # Telephony runs surface their provider here.
    payload["modality"] = workflow_run.mode
    payload["workflow_run_id"] = workflow_run.id
    payload["source"] = "scaiva-telephony"
    payload["received_at"] = datetime.now(UTC).isoformat()
    payload["transcript"] = transcript or ""

    return payload


def _build_webhook_url(base_url: str, token: Optional[str]) -> str:
    """Append ``?token=...`` to satisfy the Apps Script SHEET_TOKEN gate.

    Preserves any query string already present on the configured URL.
    """
    if not token:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': token})}"


async def deliver_lead_for_run(
    workflow_run_id: int,
    transcript: Optional[str] = None,
) -> bool:
    """Deliver a lead for a completed run, if and only if it is configured to.

    Returns ``True`` when a lead was POSTed and accepted (2xx), else ``False``.
    Never raises — every failure path logs and returns ``False`` so it cannot
    break or delay call completion.
    """
    # Gate 1: webhook must be configured.
    if not LEAD_DELIVERY_WEBHOOK_URL:
        logger.debug(
            "Lead delivery skipped for run {}: LEAD_DELIVERY_WEBHOOK_URL not set",
            workflow_run_id,
        )
        return False

    try:
        workflow_run = await db_client.get_workflow_run_by_id(workflow_run_id)
    except Exception:
        logger.exception(
            "Lead delivery: failed to load workflow run {}", workflow_run_id
        )
        return False

    if workflow_run is None:
        logger.debug("Lead delivery skipped: workflow run {} not found", workflow_run_id)
        return False

    # Gate 2: the run's workflow must be explicitly allowlisted.
    if workflow_run.workflow_id not in LEAD_DELIVERY_WORKFLOW_IDS:
        logger.debug(
            "Lead delivery skipped for run {}: workflow_id {} not in allowlist",
            workflow_run_id,
            workflow_run.workflow_id,
        )
        return False

    # Gate 3: deliver to Google Sheets ONLY when the caller booked a site visit.
    # All calls are logged to Supabase unconditionally by log_call_to_supabase();
    # the Sheet is reserved for confirmed bookings so the sales team sees only
    # actionable rows.
    gathered = workflow_run.gathered_context or {}
    if not gathered.get("visit_datetime"):
        logger.info(
            "Lead delivery skipped for run {}: no visit_datetime in gathered_context",
            workflow_run_id,
        )
        return False

    try:
        payload = build_lead_payload(workflow_run, transcript)
        url = _build_webhook_url(
            LEAD_DELIVERY_WEBHOOK_URL, LEAD_DELIVERY_WEBHOOK_TOKEN
        )

        logger.info(
            "Delivering lead for run {} (workflow {}) to lead webhook",
            workflow_run_id,
            workflow_run.workflow_id,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

        logger.info(
            "Lead delivered for run {}: {}", workflow_run_id, response.status_code
        )
        return True

    except httpx.HTTPStatusError as e:
        logger.warning(
            "Lead delivery for run {} failed: {} - {}",
            workflow_run_id,
            e.response.status_code,
            e.response.text[:200],
        )
        return False
    except httpx.RequestError as e:
        logger.warning("Lead delivery for run {} request error: {}", workflow_run_id, e)
        return False
    except Exception:
        logger.exception("Lead delivery for run {} unexpected error", workflow_run_id)
        return False
