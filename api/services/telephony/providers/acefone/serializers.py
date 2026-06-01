"""Acefone WebSocket frame serializer.

Acefone uses G.711 mu-law encoding at 8 kHz with base64-encoded payloads
in a JSON envelope. This serializer converts between pipecat frames and
the Acefone WebSocket protocol.
"""

import base64
import json
from typing import cast

from loguru import logger

from pipecat.audio.utils import create_stream_resampler, pcm_to_ulaw, ulaw_to_pcm
from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InputDTMFFrame,
    InterruptionFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


def align_payload(data: bytes) -> bytes:
    """Pad payload to a multiple of 160 bytes as required by Acefone."""
    remainder = len(data) % 160
    if remainder == 0:
        return data
    padding = 160 - remainder
    return data + b"\x00" * padding


class AcefoneFrameSerializer(FrameSerializer):
    """Serializer for Acefone bi-directional audio streaming WebSocket protocol.

    Acefone uses G.711 mu-law encoding at 8 kHz with base64-encoded payloads
    wrapped in JSON envelopes. Outgoing media payloads must be at least 160
    bytes (or a multiple of 160 bytes).
    """

    class InputParams(FrameSerializer.InputParams):
        """Configuration parameters for AcefoneFrameSerializer.

        Parameters:
            acefone_sample_rate: Sample rate used by Acefone, defaults to 8000 Hz.
            sample_rate: Optional override for pipeline input sample rate.
            auto_hang_up: Whether to automatically terminate call on EndFrame.
            ignore_rtvi_messages: Inherited from base FrameSerializer, defaults to True.
        """

        acefone_sample_rate: int = 8000
        sample_rate: int | None = None
        auto_hang_up: bool = True

    def __init__(
        self,
        stream_sid: str,
        call_sid: str | None = None,
        api_key: str | None = None,
        params: InputParams | None = None,
    ):
        """Initialize the AcefoneFrameSerializer.

        Args:
            stream_sid: The Acefone stream SID.
            call_sid: The associated Acefone call SID (optional).
            api_key: Acefone API key (required for auto hang-up).
            params: Configuration parameters.
        """
        params = params or AcefoneFrameSerializer.InputParams()
        super().__init__(params)
        self._params: AcefoneFrameSerializer.InputParams = params

        if self._params.auto_hang_up:
            missing_credentials = []
            if not call_sid:
                missing_credentials.append("call_sid")
            if not api_key:
                missing_credentials.append("api_key")
            if missing_credentials:
                raise ValueError(
                    f"auto_hang_up is enabled but missing required parameters: "
                    f"{', '.join(missing_credentials)}"
                )

        self._stream_sid = stream_sid
        self._call_sid = call_sid
        self._api_key = api_key

        self._acefone_sample_rate = self._params.acefone_sample_rate
        self._sample_rate = 0  # Pipeline input rate

        self._input_resampler = create_stream_resampler()
        self._output_resampler = create_stream_resampler()
        self._hangup_attempted = False

    async def setup(self, frame: StartFrame):
        """Sets up the serializer with pipeline configuration.

        Args:
            frame: The StartFrame containing pipeline configuration.
        """
        self._sample_rate = self._params.sample_rate or frame.audio_in_sample_rate

    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Serializes a pipecat frame to Acefone WebSocket format.

        Args:
            frame: The pipecat frame to serialize.

        Returns:
            Serialized data as string or None if the frame isn't handled.
        """
        if (
            self._params.auto_hang_up
            and not self._hangup_attempted
            and isinstance(frame, (EndFrame, CancelFrame))
        ):
            self._hangup_attempted = True
            return None
        elif isinstance(frame, InterruptionFrame):
            answer = {"event": "clear", "streamSid": self._stream_sid}
            return json.dumps(answer)
        elif isinstance(frame, AudioRawFrame):
            data = frame.audio

            serialized_data = await pcm_to_ulaw(
                data, frame.sample_rate, self._acefone_sample_rate, self._output_resampler
            )
            if serialized_data is None or len(serialized_data) == 0:
                return None

            serialized_data = align_payload(serialized_data)

            payload = base64.b64encode(serialized_data).decode("utf-8")
            answer = {
                "event": "media",
                "streamSid": self._stream_sid,
                "media": {"payload": payload},
            }

            return json.dumps(answer)
        elif isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            if self.should_ignore_frame(frame):
                return None
            return json.dumps(frame.message)

        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        """Deserializes Acefone WebSocket data to pipecat frames.

        Handles acefone media, dtmf, and stop events.

        Args:
            data: The raw WebSocket data from Acefone.

        Returns:
            A pipecat frame corresponding to the Acefone event, or None if unhandled.
        """
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Acefone JSON message")
            return None

        event = message.get("event")

        if event == "media":
            payload_base64 = message.get("media", {}).get("payload")
            if not payload_base64:
                return None

            payload = base64.b64decode(payload_base64)

            deserialized_data = await ulaw_to_pcm(
                payload, self._acefone_sample_rate, self._sample_rate, self._input_resampler
            )
            if deserialized_data is None or len(deserialized_data) == 0:
                return None

            audio_frame = InputAudioRawFrame(
                audio=deserialized_data, num_channels=1, sample_rate=self._sample_rate
            )
            return audio_frame
        elif event == "dtmf":
            digit = message.get("dtmf", {}).get("digit")
            if digit:
                from pipecat.audio.dtmf.types import KeypadEntry

                try:
                    return InputDTMFFrame(KeypadEntry(digit))
                except ValueError:
                    logger.warning(f"Invalid DTMF digit received: {digit}")
                    return None
        elif event == "stop":
            logger.debug(f"Acefone stream stopped for call {self._call_sid}")
            return None

        return None
