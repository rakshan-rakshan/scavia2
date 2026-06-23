"""tests/test_tools.py — Unit tests for the 5 tool handlers (PRD §6.4).

All DB helpers are monkeypatched; no real Supabase or network required.
Uses pytest-asyncio with asyncio_mode=auto (set in pytest.ini).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.py installs env stubs + supabase stub before this import.
from app.tools import (
    SessionState,
    _LEAD_FIELDS,
    _capture_lead,
    _end_call,
    _flag_for_human,
    _switch_language,
    _transfer_to_human,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeParams:
    """Minimal stand-in for pipecat FunctionCallParams."""

    def __init__(self, arguments: dict[str, Any]) -> None:
        self.arguments = arguments
        self._results: list[Any] = []

    async def result_callback(self, result: Any) -> None:
        self._results.append(result)

    @property
    def last_result(self) -> Any:
        return self._results[-1] if self._results else None


def _state(**kwargs) -> SessionState:
    """Create a SessionState with a stubbed DB client."""

    class _ExecResult:
        data = [{"id": "mock-lead-id"}]

    class _QB:
        def insert(self, *a, **kw):
            return self
        def update(self, *a, **kw):
            return self
        def eq(self, *a, **kw):
            return self
        def execute(self):
            return _ExecResult()

    class _MockClient:
        def table(self, name: str):
            return _QB()

    s = SessionState(**kwargs)
    s._client = _MockClient()
    return s


# ===========================================================================
# capture_lead tests
# ===========================================================================


class TestCaptureLead:
    """Tests for _capture_lead."""

    @pytest.mark.asyncio
    async def test_valid_fields_saved(self):
        """Known fields are saved and echoed back in result."""
        state = _state()
        params = FakeParams({"field_updates": {"name": "Alice", "phone": "9999"}})

        with patch("app.tools._upsert_lead", return_value="lead-001") as mock_upsert:
            await _capture_lead(state, params)

        result = params.last_result
        assert result["status"] == "ok"
        assert result["lead_id"] == "lead-001"
        assert "name" in result["saved"]
        assert "phone" in result["saved"]

    @pytest.mark.asyncio
    async def test_unknown_keys_filtered(self):
        """Keys not in _LEAD_FIELDS must be stripped before the DB call."""
        state = _state()
        params = FakeParams({
            "field_updates": {
                "name": "Bob",
                "INJECTED_COLUMN": "DROP TABLE leads;",   # must be filtered
                "source": "hacked",                        # must be filtered
            }
        })

        captured_fields: dict = {}

        def fake_upsert(client, lead_id, fields):
            captured_fields.update(fields)
            return "lead-002"

        with patch("app.tools._upsert_lead", side_effect=fake_upsert):
            await _capture_lead(state, params)

        assert "INJECTED_COLUMN" not in captured_fields
        assert "source" not in captured_fields
        assert "name" in captured_fields

    @pytest.mark.asyncio
    async def test_all_lead_field_whitelist_allowed(self):
        """Every field in _LEAD_FIELDS is accepted."""
        state = _state()
        all_fields = {f: f"value_{f}" for f in _LEAD_FIELDS}
        params = FakeParams({"field_updates": all_fields})

        captured_fields: dict = {}

        def fake_upsert(client, lead_id, fields):
            captured_fields.update(fields)
            return "lead-003"

        with patch("app.tools._upsert_lead", side_effect=fake_upsert):
            await _capture_lead(state, params)

        for field in _LEAD_FIELDS:
            assert field in captured_fields, f"{field!r} should pass the whitelist"

    @pytest.mark.asyncio
    async def test_empty_values_dropped(self):
        """None and empty-string values must be excluded from the DB call."""
        state = _state()
        params = FakeParams({
            "field_updates": {
                "name": "Carol",
                "email": "",          # empty — must be dropped
                "phone": None,        # None — must be dropped
            }
        })

        captured_fields: dict = {}

        def fake_upsert(client, lead_id, fields):
            captured_fields.update(fields)
            return "lead-004"

        with patch("app.tools._upsert_lead", side_effect=fake_upsert):
            await _capture_lead(state, params)

        assert "email" not in captured_fields
        assert "phone" not in captured_fields
        assert "name" in captured_fields

    @pytest.mark.asyncio
    async def test_no_valid_fields_returns_noop(self):
        """If nothing survives filtering, the handler returns status=noop."""
        state = _state()
        params = FakeParams({"field_updates": {"FAKE": "x", "email": ""}})

        with patch("app.tools._upsert_lead") as mock_upsert:
            await _capture_lead(state, params)

        assert params.last_result["status"] == "noop"
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_call_inserts_sets_lead_id(self):
        """First call (lead_id=None) triggers insert and populates state.lead_id."""
        state = _state()
        assert state.lead_id is None

        def fake_upsert(client, lead_id, fields):
            assert lead_id is None, "first call must be an insert (lead_id=None)"
            return "new-lead-999"

        params = FakeParams({"field_updates": {"name": "Dan"}})
        with patch("app.tools._upsert_lead", side_effect=fake_upsert):
            await _capture_lead(state, params)

        assert state.lead_id == "new-lead-999"

    @pytest.mark.asyncio
    async def test_second_call_updates_reuses_lead_id(self):
        """Second call (lead_id already set) triggers update and keeps the same id."""
        state = _state()
        state.lead_id = "existing-lead-42"

        calls: list[str | None] = []

        def fake_upsert(client, lead_id, fields):
            calls.append(lead_id)
            return lead_id  # update returns the same id

        params = FakeParams({"field_updates": {"email": "dan@example.com"}})
        with patch("app.tools._upsert_lead", side_effect=fake_upsert):
            await _capture_lead(state, params)

        assert calls[0] == "existing-lead-42", "second call must pass existing lead_id"
        assert state.lead_id == "existing-lead-42"

    @pytest.mark.asyncio
    async def test_db_exception_returns_error_status(self):
        """DB errors must be caught; the tool must return status=error, not raise."""
        state = _state()
        params = FakeParams({"field_updates": {"name": "Eve"}})

        with patch("app.tools._upsert_lead", side_effect=RuntimeError("DB down")):
            await _capture_lead(state, params)

        result = params.last_result
        assert result["status"] == "error"
        assert "DB down" in result["detail"]


# ===========================================================================
# switch_language tests
# ===========================================================================


class TestSwitchLanguage:
    """Tests for _switch_language."""

    @pytest.mark.asyncio
    async def test_hindi_maps_to_hi(self):
        state = _state()
        params = FakeParams({"language": "hindi"})
        await _switch_language(state, params)
        assert state.current_language == "hi"
        assert params.last_result["status"] == "ok"
        assert params.last_result["language"] == "hindi"

    @pytest.mark.asyncio
    async def test_telugu_maps_to_te(self):
        state = _state()
        params = FakeParams({"language": "telugu"})
        await _switch_language(state, params)
        assert state.current_language == "te"

    @pytest.mark.asyncio
    async def test_english_maps_to_en(self):
        state = _state()
        state.current_language = "hi"
        params = FakeParams({"language": "english"})
        await _switch_language(state, params)
        assert state.current_language == "en"

    @pytest.mark.asyncio
    async def test_language_path_appended(self):
        """language_path grows when a new language is selected."""
        state = _state()
        params = FakeParams({"language": "hindi"})
        await _switch_language(state, params)
        assert "hindi" in state.language_path

    @pytest.mark.asyncio
    async def test_language_path_no_duplicates(self):
        """Same language called twice must NOT produce duplicate entries."""
        state = _state()
        params1 = FakeParams({"language": "hindi"})
        params2 = FakeParams({"language": "hindi"})
        await _switch_language(state, params1)
        await _switch_language(state, params2)
        # count occurrences — must be exactly one
        assert state.language_path.count("hindi") == 1

    @pytest.mark.asyncio
    async def test_unsupported_language_returns_error(self):
        state = _state()
        params = FakeParams({"language": "french"})
        await _switch_language(state, params)
        result = params.last_result
        assert result["status"] == "error"
        assert "french" in result["detail"]

    @pytest.mark.asyncio
    async def test_on_language_switch_hook_invoked(self):
        """If on_language_switch is set, it must be awaited with the language code."""
        received: list[str] = []

        async def hook(code: str) -> None:
            received.append(code)

        state = _state()
        state.on_language_switch = hook
        params = FakeParams({"language": "telugu"})
        await _switch_language(state, params)
        assert received == ["te"]

    @pytest.mark.asyncio
    async def test_no_hook_does_not_crash(self):
        """Absence of on_language_switch hook must not raise."""
        state = _state()
        state.on_language_switch = None
        params = FakeParams({"language": "hindi"})
        await _switch_language(state, params)
        assert params.last_result["status"] == "ok"


# ===========================================================================
# flag_for_human tests
# ===========================================================================


class TestFlagForHuman:
    """Tests for _flag_for_human."""

    @pytest.mark.asyncio
    async def test_inserts_followup_row(self):
        """A successful call must attempt to write to human_followup."""
        state = _state()
        params = FakeParams({"question": "What's the RERA number?", "context": "caller asked"})

        with patch("app.tools._insert_followup") as mock_insert:
            await _flag_for_human(state, params)

        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args
        # _insert_followup(client, lead_id, question, context)
        assert call_kwargs.args[2] == "What's the RERA number?"
        assert call_kwargs.args[3] == "caller asked"

    @pytest.mark.asyncio
    async def test_records_guardrail_flag(self):
        """Calling flag_for_human must record a guardrail entry on the state."""
        state = _state()
        params = FakeParams({"question": "Exact price?", "context": "price push"})

        with patch("app.tools._insert_followup"):
            await _flag_for_human(state, params)

        assert len(state.guardrail_flags) == 1
        assert state.guardrail_flags[0]["kind"] == "flag_for_human"

    @pytest.mark.asyncio
    async def test_returns_ok_on_success(self):
        state = _state()
        params = FakeParams({"question": "Q?", "context": "C"})
        with patch("app.tools._insert_followup"):
            await _flag_for_human(state, params)
        assert params.last_result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_db_error_returns_error_status(self):
        state = _state()
        params = FakeParams({"question": "Q?", "context": "C"})
        with patch("app.tools._insert_followup", side_effect=RuntimeError("DB gone")):
            await _flag_for_human(state, params)
        assert params.last_result["status"] == "error"


# ===========================================================================
# transfer_to_human tests
# ===========================================================================


class TestTransferToHuman:
    """Tests for _transfer_to_human (Phase 0 — log only)."""

    @pytest.mark.asyncio
    async def test_returns_phase0_logged_mode(self):
        state = _state()
        params = FakeParams({"reason": "caller demands a person"})
        await _transfer_to_human(state, params)
        result = params.last_result
        assert result["status"] == "ok"
        assert result["mode"] == "phase0_logged"

    @pytest.mark.asyncio
    async def test_records_guardrail_flag(self):
        """transfer_to_human must record a guardrail entry."""
        state = _state()
        params = FakeParams({"reason": "escalation requested"})
        await _transfer_to_human(state, params)
        assert any(f["kind"] == "transfer_to_human" for f in state.guardrail_flags)

    @pytest.mark.asyncio
    async def test_say_field_present(self):
        """The result must include a 'say' script for the voice agent."""
        state = _state()
        params = FakeParams({"reason": "any"})
        await _transfer_to_human(state, params)
        assert "say" in params.last_result

    @pytest.mark.asyncio
    async def test_no_real_transfer_occurs(self):
        """Phase 0: no side-effects beyond the guardrail log."""
        state = _state()
        params = FakeParams({"reason": "test"})
        # Should complete cleanly with no DB writes or hook calls.
        await _transfer_to_human(state, params)
        assert params.last_result["status"] == "ok"


# ===========================================================================
# end_call tests
# ===========================================================================


class TestEndCall:
    """Tests for _end_call."""

    @pytest.mark.asyncio
    async def test_writes_call_log(self):
        """end_call must attempt to write to call_logs."""
        state = _state()
        params = FakeParams({"reason": "caller said goodbye"})

        with patch("app.tools._insert_call_log") as mock_log:
            await _end_call(state, params)

        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_invokes_end_session_hook(self):
        """If end_session is wired, it must be awaited after logging."""
        ended: list[bool] = []

        async def hook():
            ended.append(True)

        state = _state()
        state.end_session = hook
        params = FakeParams({"reason": "goodbye"})

        with patch("app.tools._insert_call_log"):
            await _end_call(state, params)

        assert ended == [True]

    @pytest.mark.asyncio
    async def test_returns_ended_true(self):
        state = _state()
        params = FakeParams({"reason": "done"})
        with patch("app.tools._insert_call_log"):
            await _end_call(state, params)
        result = params.last_result
        assert result["status"] == "ok"
        assert result["ended"] is True

    @pytest.mark.asyncio
    async def test_db_error_does_not_prevent_end_session(self):
        """A DB failure must not prevent the end_session hook from running."""
        ended: list[bool] = []

        async def hook():
            ended.append(True)

        state = _state()
        state.end_session = hook
        params = FakeParams({"reason": "goodbye"})

        with patch("app.tools._insert_call_log", side_effect=RuntimeError("DB gone")):
            await _end_call(state, params)

        # end_session hook must still be called despite DB error
        assert ended == [True]

    @pytest.mark.asyncio
    async def test_no_hook_does_not_crash(self):
        """Absence of end_session hook must not raise."""
        state = _state()
        state.end_session = None
        params = FakeParams({"reason": "done"})
        with patch("app.tools._insert_call_log"):
            await _end_call(state, params)
        assert params.last_result["ended"] is True


# ===========================================================================
# build_tools_schema tests (skipped if pipecat not installed)
# ===========================================================================


class TestBuildToolsSchema:
    """Validates that build_tools_schema returns the correct shape."""

    def test_build_tools_schema_skipped_without_pipecat(self):
        """Skip gracefully when pipecat is absent."""
        pipecat = pytest.importorskip("pipecat", reason="pipecat not installed")
        from app.tools import build_tools_schema
        schema = build_tools_schema()
        # ToolsSchema exposes .standard_tools
        tool_names = [t.name for t in schema.standard_tools]
        assert set(tool_names) == {
            "capture_lead",
            "switch_language",
            "flag_for_human",
            "transfer_to_human",
            "end_call",
        }

    def test_capture_lead_exposes_field_enums_skipped_without_pipecat(self):
        """capture_lead must expose the budget_band and purpose enums."""
        pytest.importorskip("pipecat", reason="pipecat not installed")
        from app.tools import build_tools_schema
        schema = build_tools_schema()
        capture = next(t for t in schema.standard_tools if t.name == "capture_lead")
        props = capture.properties["field_updates"]["properties"]
        assert "enum" in props["budget_band"]
        assert "enum" in props["purpose"]
        assert "5-6 Cr" in props["budget_band"]["enum"]
        assert "self-use" in props["purpose"]["enum"]


# ===========================================================================
# _LEAD_FIELDS whitelist sanity check
# ===========================================================================


def test_lead_fields_whitelist_contains_expected_columns():
    """_LEAD_FIELDS must contain exactly the documented qualification fields."""
    expected = {
        "name", "email", "phone", "job", "purpose", "budget_band",
        "timeline", "visit_datetime", "preferred_language", "outcome",
    }
    assert _LEAD_FIELDS == expected
