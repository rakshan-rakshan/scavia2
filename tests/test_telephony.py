"""Phase 2 telephony tests — keyless, no network.

Covers the Acefone serializer (Twilio-clone wire format), the start-event
handshake parser, and the transport factory. These prove the telephony plumbing
is correct without a live Acefone call.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock

import pytest

from app.serializers import AcefoneFrameSerializer


# ---------------------------------------------------------------------------
# parse_start — handshake extraction
# ---------------------------------------------------------------------------

def test_parse_start_twilio_exact():
    msg = {
        "event": "start",
        "streamSid": "MZ-stream-123",
        "start": {
            "streamSid": "MZ-stream-123",
            "callSid": "CA-call-456",
            "customParameters": {"language": "hindi"},
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000},
        },
    }
    stream_sid, call_sid, lang = AcefoneFrameSerializer.parse_start(msg)
    assert stream_sid == "MZ-stream-123"
    assert call_sid == "CA-call-456"
    assert lang == "hi"


def test_parse_start_snake_case_variant_and_default_lang():
    msg = {
        "event": "start",
        "start": {"stream_sid": "s-1", "call_sid": "c-1"},
    }
    stream_sid, call_sid, lang = AcefoneFrameSerializer.parse_start(msg)
    assert stream_sid == "s-1"
    assert call_sid == "c-1"
    assert lang == "en"  # no custom language -> default


def test_parse_start_unknown_language_falls_back_to_en():
    msg = {"event": "start", "start": {"streamSid": "s", "customParameters": {"language": "klingon"}}}
    _stream, _call, lang = AcefoneFrameSerializer.parse_start(msg)
    assert lang == "en"


def test_parse_start_missing_sids_returns_none():
    stream_sid, call_sid, lang = AcefoneFrameSerializer.parse_start({"event": "start", "start": {}})
    assert stream_sid is None
    assert call_sid is None
    assert lang == "en"


# ---------------------------------------------------------------------------
# Serializer construction
# ---------------------------------------------------------------------------

def test_auto_hang_up_off_by_default_needs_no_twilio_creds():
    # Twilio's serializer raises if auto_hang_up is on without account creds;
    # ours defaults it off, so plain construction must succeed.
    ser = AcefoneFrameSerializer(stream_sid="s-1", call_sid="c-1")
    assert ser._params.auto_hang_up is False


# ---------------------------------------------------------------------------
# Wire (de)serialization round-trip (μ-law 8 kHz, base64)
# ---------------------------------------------------------------------------

async def _setup_serializer(rate: int = 8000) -> AcefoneFrameSerializer:
    from pipecat.frames.frames import StartFrame

    ser = AcefoneFrameSerializer(stream_sid="stream-xyz")
    start = StartFrame(audio_in_sample_rate=rate, audio_out_sample_rate=rate)
    await ser.setup(start)
    return ser


async def test_deserialize_media_event_to_audio_frame():
    from pipecat.frames.frames import InputAudioRawFrame

    ser = await _setup_serializer()
    # 160 bytes of μ-law silence (0xFF) = one 20 ms telephony frame.
    payload = base64.b64encode(b"\xff" * 160).decode()
    msg = json.dumps({"event": "media", "streamSid": "stream-xyz", "media": {"payload": payload}})

    frame = await ser.deserialize(msg)
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.sample_rate == 8000
    assert len(frame.audio) > 0


async def test_serialize_audio_frame_to_media_event():
    from pipecat.frames.frames import OutputAudioRawFrame

    ser = await _setup_serializer()
    out = OutputAudioRawFrame(audio=b"\x00\x00" * 160, sample_rate=8000, num_channels=1)

    serialized = await ser.serialize(out)
    assert serialized is not None
    decoded = json.loads(serialized)
    assert decoded["event"] == "media"
    assert decoded["streamSid"] == "stream-xyz"
    # payload must be valid base64 μ-law
    assert len(base64.b64decode(decoded["media"]["payload"])) > 0


async def test_interruption_frame_emits_clear_event():
    from pipecat.frames.frames import StartInterruptionFrame

    ser = await _setup_serializer()
    serialized = await ser.serialize(StartInterruptionFrame())
    decoded = json.loads(serialized)
    assert decoded == {"event": "clear", "streamSid": "stream-xyz"}


# ---------------------------------------------------------------------------
# Transport factory
# ---------------------------------------------------------------------------

def test_create_acefone_transport_returns_fastapi_ws_transport():
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

    from app.transports import create_acefone_transport

    transport = create_acefone_transport(MagicMock(), stream_sid="s-1", call_sid="c-1")
    assert isinstance(transport, FastAPIWebsocketTransport)
