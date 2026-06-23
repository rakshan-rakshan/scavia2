"""Frame serializers for telephony transports (Phase 2).

Acefone's "Voice Streaming" WebSocket protocol is a Twilio Media Streams clone:
μ-law 8 kHz audio, base64 payloads, a JSON envelope keyed by ``streamSid``, and
the same event vocabulary (``connected`` / ``start`` / ``media`` / ``stop`` /
``mark`` / ``clear``). Because the wire format is identical, we subclass
pipecat's ``TwilioFrameSerializer`` and reuse its battle-tested (de)serialization
of audio + DTMF frames. We change only what differs for Acefone:

  * ``auto_hang_up`` defaults to **False**. Twilio's serializer hangs up by
    calling Twilio's REST API (and therefore demands account_sid/auth_token).
    Acefone exposes a different REST surface, so for Phase 0/2 we tear the call
    down by closing the WebSocket when an ``EndFrame`` flows through the
    transport — no provider credentials required.
  * A ``parse_start`` helper extracts the stream/call identifiers (and an
    optional caller language) from the ``start`` handshake event, defensively
    handling both the nested (``start.streamSid``) and top-level (``streamSid``)
    placements so it works against either Twilio-exact or lightly-renamed
    Acefone payloads.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from pipecat.serializers.twilio import TwilioFrameSerializer

from app.config import SUPPORTED_LANGUAGES

logger = logging.getLogger("aria.serializers")

# Map a few human language names Acefone might pass as a custom parameter back
# to our internal 2-letter codes.
_LANG_ALIASES = {
    "en": "en", "english": "en",
    "hi": "hi", "hindi": "hi",
    "te": "te", "telugu": "te",
}


class AcefoneFrameSerializer(TwilioFrameSerializer):
    """Twilio-compatible serializer for Acefone Voice Streaming.

    See module docstring for why subclassing Twilio is correct here.
    """

    class InputParams(TwilioFrameSerializer.InputParams):
        """Acefone serializer params.

        Inherits ``twilio_sample_rate`` (the telephony μ-law rate, 8 kHz) and
        ``sample_rate`` from the parent; only the hang-up default changes.
        """

        # Off by default: Acefone teardown is WebSocket-close, not a REST hangup,
        # so we do not require Twilio account credentials to construct this.
        auto_hang_up: bool = False

    def __init__(
        self,
        stream_sid: str,
        call_sid: Optional[str] = None,
        params: Optional["AcefoneFrameSerializer.InputParams"] = None,
    ) -> None:
        super().__init__(
            stream_sid=stream_sid,
            call_sid=call_sid,
            params=params or AcefoneFrameSerializer.InputParams(),
        )

    @staticmethod
    def parse_start(message: dict) -> Tuple[Optional[str], Optional[str], str]:
        """Pull (stream_sid, call_sid, start_lang) out of a ``start`` event.

        Robust to both Twilio-exact and Acefone-variant key placement. Returns
        ``("en")`` for the language when none is supplied as a custom parameter.
        """
        start = message.get("start") or {}

        stream_sid = (
            message.get("streamSid")
            or start.get("streamSid")
            or message.get("stream_sid")
            or start.get("stream_sid")
        )
        call_sid = (
            start.get("callSid")
            or message.get("callSid")
            or start.get("call_sid")
            or message.get("call_sid")
        )

        # Optional caller-language hint via custom parameters
        # (Twilio: start.customParameters.<key>).
        custom = start.get("customParameters") or start.get("custom_parameters") or {}
        raw_lang = str(custom.get("language") or custom.get("lang") or "").strip().lower()
        start_lang = _LANG_ALIASES.get(raw_lang, "en")
        if start_lang not in SUPPORTED_LANGUAGES:
            start_lang = "en"

        return stream_sid, call_sid, start_lang
