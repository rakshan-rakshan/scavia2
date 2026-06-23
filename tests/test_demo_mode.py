"""Demo-mode tests — agent runs (and tools succeed) with NO Supabase configured.

This is what lets you test the voice agent with only ANTHROPIC_API_KEY +
SARVAM_API_KEY: tool calls must not crash and must report success to the LLM so
the conversation keeps flowing, just without persisting.
"""

from __future__ import annotations

import pytest

from app.tools import SessionState, _capture_lead, _end_call, _flag_for_human


def _demo_state() -> SessionState:
    """A SessionState whose db() resolves to None (no Supabase)."""
    state = SessionState()
    state._client = None
    state._db_resolved = True  # pretend we already resolved -> None (demo mode)
    return state


def test_db_returns_none_in_demo_mode():
    assert _demo_state().db() is None


async def test_capture_lead_succeeds_without_persisting(fake_params):
    state = _demo_state()
    params = fake_params({"field_updates": {"name": "Asha", "budget_band": "6-7 Cr"}})
    await _capture_lead(state, params)
    assert params.last_result["status"] == "ok"
    assert params.last_result["persisted"] is False
    assert set(params.last_result["saved"]) == {"name", "budget_band"}


async def test_flag_for_human_succeeds_without_persisting(fake_params):
    state = _demo_state()
    params = fake_params({"question": "Is there a metro nearby?", "context": "buyer asked"})
    await _flag_for_human(state, params)
    assert params.last_result["status"] == "ok"
    assert params.last_result["persisted"] is False
    # Guardrail is still recorded in-memory even in demo mode.
    assert any(g["kind"] == "flag_for_human" for g in state.guardrail_flags)


async def test_end_call_succeeds_without_persisting(fake_params):
    state = _demo_state()
    ended = {"v": False}

    async def _end():
        ended["v"] = True

    state.end_session = _end
    params = fake_params({"reason": "caller opted out"})
    await _end_call(state, params)
    assert params.last_result["ended"] is True
    assert ended["v"] is True
