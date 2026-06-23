"""Pipeline factory — transport-agnostic (PRD §4).

run_bot(transport, ...) wires the single shared pipeline:

  transport.input()
    -> Sarvam STT (saaras:v3)
    -> user context aggregator
    -> Anthropic LLM (+ 5 tools)
    -> TTS (Cartesia EN | Sarvam HI/TE)
    -> transport.output()
    -> assistant context aggregator

Barge-in (interruptions) and Silero VAD are enabled. The same function serves
the browser transport today and the Acefone transport in Phase 2.
"""

from __future__ import annotations

import logging

from app.config import LANGUAGE_NAMES, get_settings
from app.system_prompt import build_system_prompt
from app.tools import SessionState, build_tools_schema, register_tools
from app.transports import create_stt_service, create_tts_service

logger = logging.getLogger("aria.bot")


async def run_bot(transport, channel: str = "browser", start_lang: str = "en") -> None:
    """Build and run the conversation pipeline for one session."""
    from pipecat.frames.frames import EndFrame, LLMRunFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
    from pipecat.services.anthropic.llm import AnthropicLLMService

    settings = get_settings()
    state = SessionState(channel=channel, current_language=start_lang)
    state.language_path.append(LANGUAGE_NAMES.get(start_lang, "english"))

    # --- Services ---
    stt = create_stt_service()
    tts = create_tts_service(start_lang)
    llm = AnthropicLLMService(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    # --- Context (system prompt + tools) ---
    messages = [{"role": "system", "content": build_system_prompt(start_lang)}]
    context = OpenAILLMContext(messages, tools=build_tools_schema())
    aggregator = llm.create_context_aggregator(context)

    register_tools(llm, state)

    # Optional transcript capture (best-effort; skipped if API unavailable).
    transcript = _maybe_transcript_processor(state)

    pipeline_stages = [
        transport.input(),
        stt,
        *( [transcript.user()] if transcript else [] ),
        aggregator.user(),
        llm,
        tts,
        transport.output(),
        *( [transcript.assistant()] if transcript else [] ),
        aggregator.assistant(),
    ]
    pipeline = Pipeline(pipeline_stages)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True, enable_metrics=True),
    )

    # --- Wire session hooks the tools call back into ---
    async def _end_session() -> None:
        await task.queue_frames([EndFrame()])

    state.end_session = _end_session
    state.on_language_switch = _make_language_logger()  # P0: log only; hot-swap = P1.5

    # --- Transport lifecycle: greet first, clean up on disconnect ---
    @transport.event_handler("on_client_connected")
    async def _on_connected(_transport, _client):
        logger.info("client connected (%s) — Aria greeting", channel)
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client):
        logger.info("client disconnected — ending task")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


def _make_language_logger():
    async def _log(code: str) -> None:
        logger.info("switch_language -> %s (P0: text-mirroring only; TTS hot-swap is P1.5)", code)
    return _log


def _maybe_transcript_processor(state: SessionState):
    """Attach a TranscriptProcessor if this pipecat version exposes one."""
    try:
        from pipecat.processors.transcript_processor import TranscriptProcessor
    except Exception:  # pragma: no cover - version dependent
        logger.warning("TranscriptProcessor unavailable; call_log transcript will be null")
        return None

    proc = TranscriptProcessor()

    @proc.event_handler("on_transcript_update")
    async def _on_update(_p, frame):  # noqa: ANN001
        for msg in getattr(frame, "messages", []):
            state.transcript.append(
                {
                    "role": getattr(msg, "role", None),
                    "content": getattr(msg, "content", None),
                    "ts": getattr(msg, "timestamp", None),
                }
            )

    return proc
