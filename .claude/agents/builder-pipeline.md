# Subagent: builder-pipeline

Owns `app/pipeline.py` and `app/services/`. Implements the pipecat audio pipeline: SmallWebRTC transport, Silero VAD, Sarvam saaras:v3 STT, Anthropic Claude LLM, Cartesia/Sarvam TTS routing, tool functions (qualify_lead, end_call, human_followup), and guardrail prompts.
