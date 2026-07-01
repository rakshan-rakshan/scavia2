"""Write every completed telephony call to the shared Supabase leads table.

This runs unconditionally for all allowlisted workflow runs, regardless of
outcome. Only site-visit-booked calls additionally fire the Google Sheet
webhook (see :mod:`api.services.lead_delivery.delivery`).

Gating (all enforced in :func:`log_call_to_supabase`):
  * ``SUPABASE_URL`` must be set, else no-op.
  * ``SUPABASE_SERVICE_ROLE_KEY`` must be set, else no-op.
  * the run's ``workflow_id`` must be in ``SUPABASE_LOG_WORKFLOW_IDS``.

Delivery is fully exception-guarded: any failure is logged and swallowed.
It must never break or delay call completion.
"""

from datetime import UTC, datetime
from typing import Any, Optional

import httpx
from loguru import logger

from api.constants import (
    SUPABASE_LOG_CAMPAIGN,
    SUPABASE_LOG_WORKFLOW_IDS,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)
from api.db import db_client
from api.db.models import WorkflowRunModel

_HTTP_TIMEOUT_SECONDS = 30.0

# Lead fields lifted from gathered_context, matching the leads table columns.
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

# LeadGen funnel fields (IVR→AI tracks). Each has its own leads-table column.
# Absent from legacy maira/maira2 runs, so every one falls back to None.
_LEADGEN_DIRECT_FIELDS = (
    "property_type",   # flat | villa | plot | farm
    "decision_maker",  # bool: prospect is the sole/primary decider
    "location_zone",   # west | north | south | east | unsure
)

# Captured-but-no-dedicated-column fields → folded into the raw jsonb blob so
# the CRM can surface them without a migration per field.
_LEADGEN_RAW_FIELDS = (
    "micro_location",
    "finance_type",
    "stage_of_search",
)


def build_supabase_payload(
    workflow_run: WorkflowRunModel,
    transcript: Optional[str] = None,
) -> dict[str, Any]:
    """Build the Supabase insert payload for a finished run.

    Maps all lead + call fields so the CRM row contains the full picture of
    the conversation without needing a separate join.
    """
    gathered = workflow_run.gathered_context or {}
    cost = workflow_run.cost_info or {}

    payload: dict[str, Any] = {field: gathered.get(field) for field in _LEAD_FIELDS}

    # LeadGen direct-column fields (None for legacy maira/maira2 runs).
    for f in _LEADGEN_DIRECT_FIELDS:
        payload[f] = gathered.get(f)

    # 0–100 lead score (LeadGen only). Also mirror to intent_score (0–10) so the
    # legacy v_leads_scored hotness fallback keeps working for any consumer that
    # still reads intent_score. Only written when the agent produced a score.
    score = gathered.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        score = max(0, min(100, int(round(score))))
        payload["score"] = score
        payload["intent_score"] = round(score / 10)
    else:
        payload["score"] = None
        # Maira/Maira2 agents emit a 0–10 intent_score directly (no LeadGen score).
        agent_intent = gathered.get("intent_score")
        if isinstance(agent_intent, (int, float)) and not isinstance(agent_intent, bool):
            payload["intent_score"] = int(round(agent_intent))

    # Location for the CRM's location column (location_news). Prefer an
    # agent-extracted location_news (Maira/Maira2), then the LeadGen micro area,
    # then the broad IVR zone.
    location = (
        gathered.get("location_news")
        or gathered.get("micro_location")
        or gathered.get("location_zone")
    )
    if location:
        payload["location_news"] = location

    # Fold remaining captured fields into the raw jsonb blob.
    raw_extra = {
        f: gathered.get(f)
        for f in _LEADGEN_RAW_FIELDS
        if gathered.get(f) is not None
    }
    if raw_extra:
        payload["raw"] = raw_extra

    # Campaign tag so CRM queries can filter by campaign.
    payload["campaign"] = SUPABASE_LOG_CAMPAIGN

    # Call metadata — mirrors the columns added in the unify_leads_for_crm migration.
    payload["workflow_id"] = str(workflow_run.id)
    payload["call_mode"] = workflow_run.mode
    payload["call_disposition"] = gathered.get("call_disposition")
    payload["call_duration_seconds"] = gathered.get("duration_seconds") or cost.get(
        "duration_seconds"
    )
    payload["call_cost_usd"] = cost.get("total_usd")
    payload["recording_url"] = workflow_run.recording_url
    payload["transcript_url"] = workflow_run.transcript_url

    # Inline transcript for quick CRM lookup (same as the Sheet payload).
    payload["transcript"] = transcript or ""

    # visit_booked mirrors the boolean the CRM uses to count confirmed site visits.
    payload["visit_booked"] = bool(payload.get("visit_datetime"))

    # created_at: use the run's own timestamp so the CRM row aligns with the call.
    if workflow_run.created_at:
        payload["created_at"] = workflow_run.created_at.isoformat()

    return payload


async def log_call_to_supabase(
    workflow_run_id: int,
    transcript: Optional[str] = None,
) -> bool:
    """Write a completed call to the Supabase leads table.

    Returns ``True`` when the row was upserted successfully, else ``False``.
    Never raises — every failure path logs and returns ``False``.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.debug(
            "Supabase call log skipped for run {}: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set",
            workflow_run_id,
        )
        return False

    try:
        workflow_run = await db_client.get_workflow_run_by_id(workflow_run_id)
    except Exception:
        logger.exception(
            "Supabase call log: failed to load workflow run {}", workflow_run_id
        )
        return False

    if workflow_run is None:
        logger.debug(
            "Supabase call log skipped: workflow run {} not found", workflow_run_id
        )
        return False

    if workflow_run.workflow_id not in SUPABASE_LOG_WORKFLOW_IDS:
        logger.debug(
            "Supabase call log skipped for run {}: workflow_id {} not in allowlist",
            workflow_run_id,
            workflow_run.workflow_id,
        )
        return False

    try:
        payload = build_supabase_payload(workflow_run, transcript)
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/leads"

        logger.info(
            "Logging call to Supabase for run {} (workflow {})",
            workflow_run_id,
            workflow_run.workflow_id,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    # Insert new row; on phone+campaign conflict, update all columns.
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

        logger.info(
            "Supabase call logged for run {}: {}", workflow_run_id, response.status_code
        )
        return True

    except httpx.HTTPStatusError as e:
        logger.warning(
            "Supabase call log for run {} failed: {} - {}",
            workflow_run_id,
            e.response.status_code,
            e.response.text[:200],
        )
        return False
    except httpx.RequestError as e:
        logger.warning(
            "Supabase call log for run {} request error: {}", workflow_run_id, e
        )
        return False
    except Exception:
        logger.exception(
            "Supabase call log for run {} unexpected error", workflow_run_id
        )
        return False
