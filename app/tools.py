"""The 5 function-calling tools (PRD §6.4) + Supabase persistence.

Design notes
------------
- All DB writes go through the Supabase *service* key (server-side only, RLS on).
- The Supabase Python client is synchronous; we offload calls with
  `asyncio.to_thread` so a slow write never blocks the audio pipeline.
- Tool handlers use pipecat's FunctionCallParams contract:
  `params.arguments` (dict) in, `await params.result_callback(dict)` out.
- A single `SessionState` object carries per-call state (lead id, language
  path, guardrail flags, transcript) and small callbacks the pipeline wires in
  (`on_language_switch`, `end_session`).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from supabase import Client, create_client

from app.config import LANGUAGE_NAMES, get_settings

logger = logging.getLogger("aria.tools")

# Whitelisted lead columns capture_lead is allowed to write (defensive: the LLM
# cannot inject arbitrary columns).
_LEAD_FIELDS = {
    "name", "email", "phone", "job", "purpose", "budget_band",
    "timeline", "visit_datetime", "preferred_language", "outcome",
}


def _supabase() -> Optional[Client]:
    """Build a Supabase client, or return None in demo mode (no DB configured)."""
    s = get_settings()
    if not s.supabase_enabled():
        return None
    return create_client(s.supabase_url, s.supabase_service_key)


@dataclass
class SessionState:
    """Per-session mutable state shared between the pipeline and the tools."""

    channel: str = "browser"
    current_language: str = "en"            # 'en' | 'hi' | 'te'
    lead_id: Optional[str] = None
    language_path: list[str] = field(default_factory=list)
    guardrail_flags: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)

    # Wired by the pipeline (transports/bot). Defaults are no-ops so tools never
    # crash if a hook is missing.
    on_language_switch: Callable[[str], Awaitable[None]] | None = None
    end_session: Callable[[], Awaitable[None]] | None = None

    _client: Client | None = None
    _db_resolved: bool = False

    def db(self) -> Optional[Client]:
        """Return the Supabase client, or None when running in demo mode."""
        if not self._db_resolved:
            if self._client is None:
                self._client = _supabase()
            self._db_resolved = True
        return self._client

    def record_guardrail(self, kind: str, detail: str) -> None:
        self.guardrail_flags.append({"kind": kind, "detail": detail})


# --- DB helpers (sync, run via to_thread) ------------------------------------

def _upsert_lead(client: Client, lead_id: Optional[str], fields: dict[str, Any]) -> str:
    if lead_id:
        client.table("leads").update(fields).eq("id", lead_id).execute()
        return lead_id
    row = {"source": "voice_agent", **fields}
    res = client.table("leads").insert(row).execute()
    return res.data[0]["id"]


def _insert_followup(client: Client, lead_id: Optional[str], question: str, context: str) -> None:
    client.table("human_followup").insert(
        {"lead_id": lead_id, "question": question, "context": context}
    ).execute()


def _insert_call_log(client: Client, state: "SessionState", duration_seconds: int | None) -> None:
    client.table("call_logs").insert(
        {
            "lead_id": state.lead_id,
            "channel": state.channel,
            "transcript": state.transcript or None,
            "duration_seconds": duration_seconds,
            "language_path": state.language_path or [LANGUAGE_NAMES.get(state.current_language)],
            "guardrail_flags": state.guardrail_flags or None,
        }
    ).execute()


# --- Tool handlers ------------------------------------------------------------
# Each is a closure-friendly coroutine taking (state, params).

async def _capture_lead(state: SessionState, params) -> None:
    updates: dict[str, Any] = dict(params.arguments.get("field_updates") or {})
    clean = {k: v for k, v in updates.items() if k in _LEAD_FIELDS and v not in (None, "")}
    if not clean:
        await params.result_callback({"status": "noop", "reason": "no valid fields"})
        return
    client = state.db()
    if client is None:  # demo mode — no Supabase configured
        logger.info("capture_lead (DEMO, not persisted): fields=%s", list(clean))
        await params.result_callback({"status": "ok", "persisted": False, "saved": list(clean)})
        return
    try:
        state.lead_id = await asyncio.to_thread(_upsert_lead, client, state.lead_id, clean)
        logger.info("capture_lead: lead=%s fields=%s", state.lead_id, list(clean))
        await params.result_callback({"status": "ok", "lead_id": state.lead_id, "saved": list(clean)})
    except Exception as exc:  # never crash the call on a DB hiccup
        logger.exception("capture_lead failed")
        await params.result_callback({"status": "error", "detail": str(exc)})


async def _switch_language(state: SessionState, params) -> None:
    lang = str(params.arguments.get("language", "")).lower()
    code = {"hindi": "hi", "telugu": "te", "english": "en", "hi": "hi", "te": "te", "en": "en"}.get(lang)
    if not code:
        await params.result_callback({"status": "error", "detail": f"unsupported language {lang!r}"})
        return
    state.current_language = code
    name = LANGUAGE_NAMES[code]
    if not state.language_path or state.language_path[-1] != name:
        state.language_path.append(name)
    # Hot-swap is Phase 1.5 (PRD §6.3). If a router hook is wired, use it;
    # otherwise we still acknowledge so the LLM mirrors the language in text.
    if state.on_language_switch:
        try:
            await state.on_language_switch(code)
        except Exception:
            logger.exception("language hot-swap hook failed")
    await params.result_callback({"status": "ok", "language": name})


async def _flag_for_human(state: SessionState, params) -> None:
    question = str(params.arguments.get("question", "")).strip()
    context = str(params.arguments.get("context", "")).strip()
    state.record_guardrail("flag_for_human", question[:200])
    client = state.db()
    if client is None:  # demo mode — no Supabase configured
        logger.info("flag_for_human (DEMO, not persisted): %s", question[:200])
        await params.result_callback({"status": "ok", "persisted": False})
        return
    try:
        await asyncio.to_thread(_insert_followup, client, state.lead_id, question, context)
        await params.result_callback({"status": "ok"})
    except Exception as exc:
        logger.exception("flag_for_human failed")
        await params.result_callback({"status": "error", "detail": str(exc)})


async def _transfer_to_human(state: SessionState, params) -> None:
    reason = str(params.arguments.get("reason", "")).strip()
    state.record_guardrail("transfer_to_human", reason[:200])
    # Phase 0: log + promise a callback. Phase 2 wires Acefone bot→agent handoff.
    logger.info("transfer_to_human (P0 log-only): %s", reason)
    await params.result_callback(
        {
            "status": "ok",
            "mode": "phase0_logged",
            "say": "I'll have a senior consultant call you back shortly.",
        }
    )


async def _end_call(state: SessionState, params) -> None:
    reason = str(params.arguments.get("reason", "")).strip()
    logger.info("end_call: %s", reason)
    client = state.db()
    if client is not None:
        try:
            await asyncio.to_thread(_insert_call_log, client, state, None)
        except Exception:
            logger.exception("call_log write failed (continuing to end)")
    else:
        logger.info("end_call (DEMO): call_log not persisted")
    await params.result_callback({"status": "ok", "ended": True})
    if state.end_session:
        try:
            await state.end_session()
        except Exception:
            logger.exception("end_session hook failed")


# --- Registration -------------------------------------------------------------

def register_tools(llm, state: SessionState) -> None:
    """Bind the 5 tools to an AnthropicLLMService for this session."""

    def bind(fn):
        async def handler(params):
            await fn(state, params)
        return handler

    llm.register_function("capture_lead", bind(_capture_lead))
    llm.register_function("switch_language", bind(_switch_language))
    llm.register_function("flag_for_human", bind(_flag_for_human))
    llm.register_function("transfer_to_human", bind(_transfer_to_human))
    llm.register_function("end_call", bind(_end_call))


def build_tools_schema():
    """Return a pipecat ToolsSchema describing the 5 tools (provider-agnostic)."""
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    capture_lead = FunctionSchema(
        name="capture_lead",
        description=(
            "Save one or more qualification fields for this lead as soon as you "
            "learn them. Call this incrementally throughout the conversation."
        ),
        properties={
            "field_updates": {
                "type": "object",
                "description": "Map of fields to save. Only include fields you actually learned.",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "job": {"type": "string"},
                    "purpose": {"type": "string", "enum": ["self-use", "investment", "both", "other"]},
                    "budget_band": {"type": "string", "enum": ["5-6 Cr", "6-7 Cr", "7-8 Cr", "8 Cr+"]},
                    "timeline": {"type": "string", "enum": ["within 30 days", "1-3 months", "after 3 months"]},
                    "visit_datetime": {"type": "string", "description": "ISO 8601 datetime of the booked visit"},
                    "preferred_language": {"type": "string", "enum": ["english", "hindi", "telugu"]},
                    "outcome": {"type": "string", "enum": ["visit_booked", "callback", "not_interested", "do_not_contact"]},
                },
            }
        },
        required=["field_updates"],
    )

    switch_language = FunctionSchema(
        name="switch_language",
        description="Switch the spoken language when the caller asks to continue in Hindi or Telugu.",
        properties={"language": {"type": "string", "enum": ["hindi", "telugu", "english"]}},
        required=["language"],
    )

    flag_for_human = FunctionSchema(
        name="flag_for_human",
        description=(
            "Use whenever the caller asks something NOT covered by your knowledge "
            "base. Logs the question for a human to answer and call back."
        ),
        properties={
            "question": {"type": "string", "description": "The exact question to route to a human."},
            "context": {"type": "string", "description": "Brief context to help the human answer."},
        },
        required=["question", "context"],
    )

    transfer_to_human = FunctionSchema(
        name="transfer_to_human",
        description="Use when the caller wants to speak to a human consultant now.",
        properties={"reason": {"type": "string"}},
        required=["reason"],
    )

    end_call = FunctionSchema(
        name="end_call",
        description="End the conversation gracefully after capturing the final outcome, or on opt-out/hostility.",
        properties={"reason": {"type": "string"}},
        required=["reason"],
    )

    return ToolsSchema(standard_tools=[
        capture_lead, switch_language, flag_for_human, transfer_to_human, end_call,
    ])
