"""Transport + TTS factories.

Phase 0 ships the browser (SmallWebRTC) transport. Phase 2 will add the Acefone
WebSocket transport + AcefoneFrameSerializer (adapted from Twilio's). The pipeline
itself is identical across transports (PRD §4) — only construction differs.
"""

from __future__ import annotations

import logging

from app.config import SARVAM_TTS_LANG_CODE, get_settings

logger = logging.getLogger("aria.transports")


def create_tts_service(lang: str):
    """Return the TTS service for the session's start language (D3).

    English -> Cartesia (premium). Hindi/Telugu -> Sarvam bulbul:v2.
    Falls back to Sarvam if Cartesia isn't configured.
    """
    s = get_settings()

    if lang == "en" and s.cartesia_enabled():
        from pipecat.services.cartesia.tts import CartesiaTTSService

        return CartesiaTTSService(
            api_key=s.cartesia_api_key,
            voice_id=s.cartesia_voice_id,
            model=s.cartesia_model,
        )

    from pipecat.services.sarvam.tts import SarvamTTSService

    return SarvamTTSService(
        api_key=s.sarvam_api_key,
        model=s.sarvam_tts_model,
        voice_id=s.sarvam_tts_speaker,
        params=SarvamTTSService.InputParams(
            language=SARVAM_TTS_LANG_CODE.get(lang, "en-IN"),
        ),
    )


def create_stt_service():
    """Sarvam saaras:v3 in transcribe mode with auto language detection (D2)."""
    from pipecat.services.sarvam.stt import SarvamSTTService

    s = get_settings()
    return SarvamSTTService(
        api_key=s.sarvam_api_key,
        model=s.sarvam_stt_model,
        params=SarvamSTTService.InputParams(mode="transcribe"),
    )


def create_acefone_transport(
    websocket,
    stream_sid: str,
    call_sid: str | None = None,
    *,
    session_timeout_secs: int | None = None,
):
    """Phase 2: Acefone Voice Streaming transport (Twilio-clone WS protocol).

    Wraps a FastAPI/Starlette ``WebSocket`` (already accepted by the route) in a
    pipecat ``FastAPIWebsocketTransport`` driven by ``AcefoneFrameSerializer``.
    Audio is μ-law 8 kHz both ways (telephony), so we pin the transport's audio
    rates to 8000 Hz and disable WAV headers — the serializer converts to/from
    PCM for the pipeline. Silero VAD + interruptions are enabled, exactly as the
    browser transport, so the SAME `run_bot` pipeline serves both channels.

    The websocket MUST already be accepted and the ``start`` handshake consumed
    (use ``AcefoneFrameSerializer.parse_start`` to obtain ``stream_sid`` /
    ``call_sid``) before calling this.
    """
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    from app.serializers import AcefoneFrameSerializer

    serializer = AcefoneFrameSerializer(stream_sid=stream_sid, call_sid=call_sid)

    params = FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        vad_analyzer=SileroVADAnalyzer(),
        serializer=serializer,
        audio_in_sample_rate=8000,
        audio_out_sample_rate=8000,
        session_timeout=session_timeout_secs,
    )

    return FastAPIWebsocketTransport(websocket=websocket, params=params)
