import json
import os
from pathlib import Path

from api.enums import Environment

ENVIRONMENT = os.getenv("ENVIRONMENT", Environment.LOCAL.value)
# Absolute path to the project root directory (i.e. the directory containing
# the top-level api/ package). Having a single canonical location helps
# when constructing file-system paths elsewhere in the codebase.
APP_ROOT_DIR: Path = Path(__file__).resolve().parent

FILLER_SOUND_PROBABILITY = 0.0

VOICEMAIL_RECORDING_DURATION = 5.0

# Langfuse Configuration
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

# URLs for deployment
BACKEND_API_ENDPOINT = os.getenv("BACKEND_API_ENDPOINT", "http://localhost:8000")
UI_APP_URL = os.getenv("UI_APP_URL", "http://localhost:3010")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "oss")
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "local")
DOGRAH_MPS_SECRET_KEY = os.getenv("DOGRAH_MPS_SECRET_KEY", None)
MPS_API_URL = os.getenv("MPS_API_URL", "https://services.dograh.com")

# The hosted Model Provider Service (MPS) at services.dograh.com is not available
# to self-hosted forks. When this flag is false (the default), a fresh OSS user is NOT
# auto-provisioned with an MPS-backed config — they get an empty config and choose their
# own provider + API key in Settings. Set true only if you have MPS access.
ENABLE_DOGRAH_MPS_AUTO_PROVISION = (
    os.getenv("ENABLE_DOGRAH_MPS_AUTO_PROVISION", "false").lower() == "true"
)

# Storage Configuration
ENABLE_AWS_S3 = os.getenv("ENABLE_AWS_S3", "false").lower() == "true"

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "voice-audio")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# AWS S3 Configuration
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

# Sentry configuration
SENTRY_DSN = os.getenv("SENTRY_DSN")

# PostHog configuration
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")


ENABLE_ARI_STASIS = os.getenv("ENABLE_ARI_STASIS", "false").lower() == "true"
SERIALIZE_LOG_OUTPUT = os.getenv("SERIALIZE_LOG_OUTPUT", "false").lower() == "true"

# Logging configuration
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", None)
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

# Log rotation configuration
LOG_ROTATION_SIZE = os.getenv("LOG_ROTATION_SIZE", "100 MB")
LOG_RETENTION = os.getenv("LOG_RETENTION", "7 days")
LOG_COMPRESSION = os.getenv("LOG_COMPRESSION", "gz")
ENABLE_TELEMETRY = os.getenv("ENABLE_TELEMETRY", "false").lower() == "true"


def _get_version() -> str:
    """Read version from pyproject.toml."""
    try:
        import tomllib

        pyproject_path = APP_ROOT_DIR / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        return pyproject.get("project", {}).get("version", "dev")
    except Exception:
        return "dev"


# Application version (read from pyproject.toml)
APP_VERSION = _get_version()

# Country code mapping: ISO country code -> international dialing prefix
COUNTRY_CODES = {
    "US": "1",  # United States
    "CA": "1",  # Canada
    "GB": "44",  # United Kingdom
    "IN": "91",  # India
    "AU": "61",  # Australia
    "DE": "49",  # Germany
    "FR": "33",  # France
    "BR": "55",  # Brazil
    "MX": "52",  # Mexico
    "IT": "39",  # Italy
    "ES": "34",  # Spain
    "NL": "31",  # Netherlands
    "SE": "46",  # Sweden
    "NO": "47",  # Norway
    "DK": "45",  # Denmark
    "FI": "358",  # Finland
    "CH": "41",  # Switzerland
    "AT": "43",  # Austria
    "BE": "32",  # Belgium
    "LU": "352",  # Luxembourg
    "IE": "353",  # Ireland
}

DEFAULT_ORG_CONCURRENCY_LIMIT = os.getenv("DEFAULT_ORG_CONCURRENCY_LIMIT", 2)
DEFAULT_CAMPAIGN_RETRY_CONFIG = {
    "enabled": True,
    "max_retries": 1,
    "retry_delay_seconds": 120,
    "retry_on_busy": True,
    "retry_on_no_answer": True,
    "retry_on_voicemail": False,
}


# Circuit breaker defaults for campaign call failure detection
DEFAULT_CIRCUIT_BREAKER_CONFIG = {
    "enabled": True,
    "failure_threshold": 0.5,  # 50% failure rate trips the breaker
    "window_seconds": 120,  # 2-minute sliding window
    "min_calls_in_window": 5,  # Don't trip until at least 5 outcomes
}


TURN_SECRET = os.getenv("TURN_SECRET")
TURN_HOST = os.getenv("TURN_HOST", "localhost")
TURN_PORT = int(os.getenv("TURN_PORT", "3478"))
TURN_TLS_PORT = int(os.getenv("TURN_TLS_PORT", "5349"))
TURN_CREDENTIAL_TTL = int(os.getenv("TURN_CREDENTIAL_TTL", "86400"))
# Diagnostic flag: when true, strip all non-relay ICE candidates from the
# answer SDP so every media path must traverse the TURN server. Use for
# verifying TURN connectivity end-to-end; expect connection failures if
# TURN is misconfigured or unreachable.
FORCE_TURN_RELAY = os.getenv("FORCE_TURN_RELAY", "false").lower() == "true"

# OSS Email/Password Auth
OSS_JWT_SECRET = os.getenv("OSS_JWT_SECRET", "change-me-in-production")
OSS_JWT_EXPIRY_HOURS = int(os.getenv("OSS_JWT_EXPIRY_HOURS", "720"))  # 30 days

TUNER_BASE_URL = os.getenv("TUNER_BASE_URL", "https://api.usetuner.ai")

# ---------------------------------------------------------------------------
# Lead delivery (server-side post-call webhook)
# ---------------------------------------------------------------------------
# Completed voice/telephony runs have no browser to deliver a lead client-side
# (unlike chat/WebRTC sessions, which post the lead from the visitor's page).
# When configured, the lead_delivery service builds a structured lead from a
# finished run's gathered_context + transcript and POSTs it to a webhook (the
# same Google Sheet endpoint the maira-microsite uses).
#
# Strictly gated and OFF by default:
#   - LEAD_DELIVERY_WEBHOOK_URL unset  -> no-op for every run.
#   - LEAD_DELIVERY_WORKFLOW_IDS is an explicit allowlist of workflow ids that
#     may deliver. A run whose workflow_id is not listed is a no-op. This keeps
#     the hook from firing for arbitrary workflows/tenants.
#   - LEAD_DELIVERY_WEBHOOK_TOKEN, when set, is appended as ?token=... on the
#     webhook URL to satisfy the Apps Script SHEET_TOKEN shared-secret gate.
LEAD_DELIVERY_WEBHOOK_URL = os.getenv("LEAD_DELIVERY_WEBHOOK_URL")
LEAD_DELIVERY_WEBHOOK_TOKEN = os.getenv("LEAD_DELIVERY_WEBHOOK_TOKEN")
# Comma-separated list of workflow ids (e.g. "11,12"). Empty/unset -> no run delivers.
LEAD_DELIVERY_WORKFLOW_IDS = frozenset(
    int(wid.strip())
    for wid in os.getenv("LEAD_DELIVERY_WORKFLOW_IDS", "").split(",")
    if wid.strip().isdigit()
)

# ---------------------------------------------------------------------------
# Supabase CRM call logging (server-side, service-role)
# ---------------------------------------------------------------------------
# Every completed telephony run for an allowlisted workflow is written to the
# shared Supabase `leads` table regardless of outcome. Only runs that include a
# site_visit_datetime in gathered_context also fire the Google Sheet webhook.
#
# SUPABASE_LOG_WORKFLOW_IDS falls back to LEAD_DELIVERY_WORKFLOW_IDS when unset,
# so a single LEAD_DELIVERY_WORKFLOW_IDS env var covers both unless you need to
# split them.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_LOG_CAMPAIGN = os.getenv("SUPABASE_LOG_CAMPAIGN", "maira")
_supabase_log_ids_raw = os.getenv("SUPABASE_LOG_WORKFLOW_IDS", "").strip()
SUPABASE_LOG_WORKFLOW_IDS: frozenset[int] = (
    frozenset(
        int(wid.strip())
        for wid in _supabase_log_ids_raw.split(",")
        if wid.strip().isdigit()
    )
    if _supabase_log_ids_raw
    else LEAD_DELIVERY_WORKFLOW_IDS  # fall back to the same allowlist
)


# ---------------------------------------------------------------------------
# TTS pronunciation overrides (spoken output only; never affects chat text)
# ---------------------------------------------------------------------------
# Brand/proper nouns that TTS engines mispronounce. Applied as whole-word,
# case-insensitive replacements on the synthesis path, after sentence
# aggregation (see api/services/pipecat/pronunciation_filter.py). Two profiles
# because English engines and Indian-language engines (Sarvam) need different
# respellings to land the same sound:
#   - default: English engines (Cartesia, Deepgram, ...) -> Latin respelling.
#     "Brigade" -> "Brigaid" so it is spoken "bri-GAYD" (rhymes with "parade").
#   - indic:   Sarvam's Telugu/Hindi voice reads native script reliably, so
#     "Brigade" -> Telugu "బ్రిగేడ్".
# Either profile can be overridden with a JSON env var (no code change needed),
# e.g. TTS_PRONUNCIATION_OVERRIDES='{"Brigade": "Brigayd"}'.
def _load_json_map(env_name: str, default: dict) -> dict:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else default
    except Exception:
        return default


# "sq ft" / "sq.ft" / "sqft" -> "square feet" because TTS otherwise reads the
# abbreviation as "s-q-ft" (the LLM sometimes abbreviates even when prompted to
# write it out). Whole-word, case-insensitive; longest key matched first.
_SQFT_VARIANTS = {
    "sq.ft": "square feet",
    "sq. ft": "square feet",
    "sq ft": "square feet",
    "sqft": "square feet",
    "sq feet": "square feet",
}
TTS_PRONUNCIATION_OVERRIDES = _load_json_map(
    "TTS_PRONUNCIATION_OVERRIDES", {"Brigade": "Brigaid", **_SQFT_VARIANTS}
)
TTS_PRONUNCIATION_OVERRIDES_INDIC = _load_json_map(
    "TTS_PRONUNCIATION_OVERRIDES_INDIC", {"Brigade": "బ్రిగేడ్", **_SQFT_VARIANTS}
)


def _invert_proper_noun_respellings(*maps: dict) -> dict:
    """Build the display-restoration map (respelling -> original) for the
    proper-noun respellings only.

    The phonetic respellings (e.g. "Brigade" -> "Brigaid") must NOT appear in
    human-visible bot text, so they are reversed for captions/transcripts. The
    sq.ft normalizations are deliberately NOT reversed: "square feet" reads fine
    in text and is the form we want shown.
    """
    restore: dict[str, str] = {}
    for m in maps:
        for original, respelling in m.items():
            if original in _SQFT_VARIANTS:
                continue
            if respelling and respelling != original:
                restore[respelling] = original
    return restore


# Reverse of the proper-noun respellings, applied to human-visible bot text
# (live captions, transcripts, logs) so they show the real word while the
# synthesized audio keeps the respelling. Auto-derived from the override maps
# above; override with TTS_PRONUNCIATION_DISPLAY_RESTORE (JSON: respelling -> word).
TTS_PRONUNCIATION_DISPLAY_RESTORE = _load_json_map(
    "TTS_PRONUNCIATION_DISPLAY_RESTORE",
    _invert_proper_noun_respellings(
        TTS_PRONUNCIATION_OVERRIDES, TTS_PRONUNCIATION_OVERRIDES_INDIC
    ),
)
