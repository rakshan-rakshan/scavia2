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


def create_acefone_transport(*args, **kwargs):  # pragma: no cover - Phase 2 stub
    """Phase 2: Acefone Voice Streaming transport (Twilio-clone WS protocol).

    Build `AcefoneFrameSerializer` from pipecat's `TwilioFrameSerializer`
    (μ-law 8 kHz, base64, events connected/start/media/stop/mark/clear,
    160-byte frame multiples). Gate: Sarvam STT keepalive/reconnect (#3699)
    MUST be fixed before any live call.
    """
    raise NotImplementedError("Acefone telephony transport is a Phase 2 deliverable (PRD §10).")
