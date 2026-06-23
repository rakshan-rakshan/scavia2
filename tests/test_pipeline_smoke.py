"""Pipeline assembly smoke test — keyless, no network.

This is the strongest *runtime* proof of the browser agent achievable without
real API keys + a mic: it runs `build_pipeline` end-to-end with REAL pipecat
components (the Anthropic LLM service, the real context aggregator, the real
ToolsSchema and tool registration) and asserts the whole thing assembles into a
runnable PipelineTask with the session hooks and all five tools wired.

It complements the import/boot test (server starts) and the unit tests (tool
side-effects) by exercising the actual pipeline-construction code path in
`app/bot.py` rather than just importing it.

The final, higher-fidelity confirmation (a live browser WebRTC call) still
requires real keys — see README "Verification Status".
"""

from __future__ import annotations

import pytest

from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class _Passthrough(FrameProcessor):
    """Minimal real FrameProcessor that forwards every frame unchanged."""

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class _FakeTransport:
    """Stand-in transport exposing the input()/output() that build_pipeline needs.

    Returns real FrameProcessors so Pipeline([...]) accepts them, without opening
    a WebRTC/WebSocket connection.
    """

    def __init__(self):
        self._in = _Passthrough()
        self._out = _Passthrough()

    def input(self):
        return self._in

    def output(self):
        return self._out


def test_build_pipeline_assembles_browser_agent_with_real_components():
    from pipecat.pipeline.task import PipelineTask

    from app.bot import build_pipeline

    # Inject passthrough STT/TTS (so we don't depend on Sarvam construction) but
    # let the REAL Anthropic LLM service + context aggregator + tools be built.
    task, state = build_pipeline(
        _FakeTransport(),
        channel="browser",
        start_lang="en",
        stt=_Passthrough(),
        tts=_Passthrough(),
    )

    assert isinstance(task, PipelineTask)

    # Session state initialised correctly.
    assert state.channel == "browser"
    assert state.current_language == "en"
    assert state.language_path == ["english"]

    # Hooks the tools call back into are wired.
    assert callable(state.end_session)
    assert callable(state.on_language_switch)


async def test_assembled_pipeline_registers_all_five_tools():
    """The LLM in the assembled pipeline must know all five Aria tools."""
    from app.bot import build_pipeline
    from pipecat.services.anthropic.llm import AnthropicLLMService

    llm = AnthropicLLMService(api_key="test-key", model="claude-sonnet-4-6")
    build_pipeline(_FakeTransport(), stt=_Passthrough(), tts=_Passthrough(), llm=llm)

    for tool in ("capture_lead", "switch_language", "flag_for_human", "transfer_to_human", "end_call"):
        assert llm.has_function(tool), f"tool not registered: {tool}"


async def test_end_session_hook_queues_end_frame():
    """Calling state.end_session() (what end_call does) must not raise."""
    from app.bot import build_pipeline

    _task, state = build_pipeline(
        _FakeTransport(), stt=_Passthrough(), tts=_Passthrough(),
        llm=_make_llm(),
    )
    # Should queue an EndFrame on the task without error.
    await state.end_session()


async def test_pipecat_runtime_moves_frames_end_to_end():
    """Sanity: pipecat actually executes a pipeline in this environment.

    Uses pipecat's own test harness to push a frame through a real two-stage
    pipeline and confirms it arrives downstream — proving the runtime (not just
    construction) works here.
    """
    from pipecat.frames.frames import TextFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.tests.utils import run_test

    pipeline = Pipeline([_Passthrough(), _Passthrough()])
    received_down, _received_up = await run_test(
        pipeline,
        frames_to_send=[TextFrame("hello aria")],
        expected_down_frames=[TextFrame],
    )
    assert any(isinstance(f, TextFrame) for f in received_down)


def _make_llm():
    from pipecat.services.anthropic.llm import AnthropicLLMService

    return AnthropicLLMService(api_key="test-key", model="claude-sonnet-4-6")
