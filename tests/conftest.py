"""conftest.py — Environment stubbing and shared fixtures.

Executed by pytest BEFORE any test module is imported.  Two jobs:

1. Inject dummy env vars so app.config.get_settings() passes validation without
   real credentials.
2. Stub the `supabase` package in sys.modules so app.tools can be imported even
   when supabase is not installed.

These stubs are deliberately minimal — they satisfy import-time contracts only.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# 1. Dummy env vars — must be set BEFORE app.config or app.tools is imported.
# ---------------------------------------------------------------------------
_DUMMY_ENV = {
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "SARVAM_API_KEY": "test-sarvam-key",
    "CARTESIA_API_KEY": "test-cartesia-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-supabase-service-key",
}

for _k, _v in _DUMMY_ENV.items():
    os.environ.setdefault(_k, _v)

# ---------------------------------------------------------------------------
# 2. Stub `supabase` if not installed so app.tools imports cleanly.
# ---------------------------------------------------------------------------

def _install_supabase_stub() -> None:
    """Put a minimal fake supabase package into sys.modules."""
    if "supabase" in sys.modules:
        return  # real package already present — nothing to do

    # Fake Client: a MagicMock that supports the .table().X().execute() chain.
    class _FakeExecuteResult:
        data: list = [{"id": "fake-lead-id"}]

    class _FakeQueryBuilder:
        def insert(self, *a, **kw):
            return self

        def update(self, *a, **kw):
            return self

        def eq(self, *a, **kw):
            return self

        def execute(self):
            return _FakeExecuteResult()

    class _FakeClient:
        def table(self, name: str):
            return _FakeQueryBuilder()

    def _fake_create_client(url: str, key: str) -> _FakeClient:
        return _FakeClient()

    stub = types.ModuleType("supabase")
    stub.Client = _FakeClient  # type: ignore[attr-defined]
    stub.create_client = _fake_create_client  # type: ignore[attr-defined]
    sys.modules["supabase"] = stub


_install_supabase_stub()

# Invalidate the lru_cache on get_settings so our env vars are picked up even
# if the module was already imported.
try:
    from app.config import get_settings  # noqa: E402
    get_settings.cache_clear()
except Exception:
    pass

# ---------------------------------------------------------------------------
# 3. Shared fixtures
# ---------------------------------------------------------------------------


class FakeParams:
    """Minimal stand-in for pipecat's FunctionCallParams."""

    def __init__(self, arguments: dict[str, Any]) -> None:
        self.arguments = arguments
        self._results: list[Any] = []

    async def result_callback(self, result: Any) -> None:
        self._results.append(result)

    @property
    def last_result(self) -> Any:
        """Most-recent result written by the tool handler."""
        return self._results[-1] if self._results else None


@pytest.fixture
def fake_params():
    """Factory: fake_params(arguments_dict) -> FakeParams instance."""
    def _factory(arguments: dict[str, Any]) -> FakeParams:
        return FakeParams(arguments)
    return _factory


@pytest.fixture
def session_state():
    """Fresh SessionState with a pre-attached fake DB client."""
    from app.tools import SessionState

    # Build a fake supabase-like client with a table() chain that records calls.
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

    state = SessionState()
    state._client = _MockClient()
    return state
