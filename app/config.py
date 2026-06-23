"""Central configuration: env loading + model/voice IDs.

All secrets come from the environment (see .env.example). Nothing secret is
hard-coded. Import `settings` everywhere; do not read os.environ elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    """Required env var — fail loudly at startup, not mid-call."""
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required env var {name!r}. Copy .env.example to .env and fill it."
        )
    return val


def _opt(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- Language → TTS routing (D3) ----------------------------------------------
# English uses Cartesia (premium voice). Hindi/Telugu use Sarvam bulbul:v2.
SUPPORTED_LANGUAGES = ("en", "hi", "te")
LANGUAGE_NAMES = {"en": "english", "hi": "hindi", "te": "telugu"}

# Sarvam bulbul:v2 language codes for Indic TTS.
SARVAM_TTS_LANG_CODE = {"hi": "hi-IN", "te": "te-IN", "en": "en-IN"}


@dataclass(frozen=True)
class Settings:
    # LLM (D4)
    anthropic_api_key: str = field(default_factory=lambda: _req("ANTHROPIC_API_KEY"))
    # Per D4: Sonnet for live calls (latency/cost); escalate to Opus only if quality demands.
    anthropic_model: str = field(default_factory=lambda: _opt("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # STT (D2) — Sarvam saaras:v3, transcribe mode, auto-detect.
    sarvam_api_key: str = field(default_factory=lambda: _req("SARVAM_API_KEY"))
    sarvam_stt_model: str = field(default_factory=lambda: _opt("SARVAM_STT_MODEL", "saaras:v3"))

    # TTS (EN) — Cartesia (D3). OPTIONAL: if unset, English falls back to
    # Sarvam bulbul:v2 (en-IN), so you can demo the agent with no Cartesia account.
    cartesia_api_key: str = field(default_factory=lambda: _opt("CARTESIA_API_KEY", ""))
    # Voice ID is account-specific; supply a premium English voice in .env.
    cartesia_voice_id: str = field(default_factory=lambda: _opt("CARTESIA_VOICE_ID", ""))
    cartesia_model: str = field(default_factory=lambda: _opt("CARTESIA_MODEL", "sonic-2"))

    # TTS (HI/TE) — Sarvam bulbul:v2 (D3). Reuses SARVAM_API_KEY.
    sarvam_tts_model: str = field(default_factory=lambda: _opt("SARVAM_TTS_MODEL", "bulbul:v2"))
    sarvam_tts_speaker: str = field(default_factory=lambda: _opt("SARVAM_TTS_SPEAKER", "anushka"))

    # Database (Supabase) — service key, server-side only. OPTIONAL: if unset, the
    # agent runs in DEMO mode — qualification still works and tool calls are logged,
    # but leads are not persisted. Set both for production lead capture.
    supabase_url: str = field(default_factory=lambda: _opt("SUPABASE_URL", ""))
    supabase_service_key: str = field(default_factory=lambda: _opt("SUPABASE_SERVICE_KEY", ""))

    # Server
    host: str = field(default_factory=lambda: _opt("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_opt("PORT", "7860")))

    # Telephony (Phase 2 — Acefone). OPTIONAL: the browser channel works without
    # these; they are only needed to provision/operate inbound PSTN calls.
    acefone_api_token: str = field(default_factory=lambda: _opt("ACEFONE_API_TOKEN", ""))
    acefone_did: str = field(default_factory=lambda: _opt("ACEFONE_DID", ""))

    def cartesia_enabled(self) -> bool:
        # Need both a key and a voice id; otherwise English falls back to Sarvam.
        return bool(self.cartesia_api_key and self.cartesia_voice_id)

    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    def acefone_enabled(self) -> bool:
        return bool(self.acefone_api_token)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. First call validates required env vars."""
    return Settings()
