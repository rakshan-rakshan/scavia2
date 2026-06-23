# Brigade Gateway — Voice Lead Qualifier

A self-hosted multilingual AI voice agent that qualifies real-estate leads over the browser in real time. The agent (Aria) conducts a structured conversation in English, Hindi, or Telugu, detects intent, applies guardrails (price deflection, legal deferral, cash-deal refusal, opt-out), and writes qualified lead records to Supabase.

---

## Architecture

```
Browser (SmallWebRTC)
        |
        | WebRTC (audio + signalling)
        v
  FastAPI  /offer  /ws
        |
        v
  Pipecat pipeline
  ┌─────────────────────────────────────────────────────────┐
  │  SmallWebRTCTransport (audio I/O)                       │
  │        │                                                │
  │  Silero VAD  ──► SarvamSTTService (saaras:v3, auto)    │
  │                        │                               │
  │                  AnthropicLLMService (claude-sonnet)   │
  │                        │                               │
  │              ┌─────────┴──────────┐                    │
  │     lang=en  │                    │ lang=hi/te         │
  │  CartesiaTTS (sonic-2)   SarvamTTS (bulbul:v2)         │
  │              └─────────┬──────────┘                    │
  │                        │                               │
  │                  SmallWebRTCTransport (playback)        │
  └─────────────────────────────────────────────────────────┘
        |
        | supabase-py (service key)
        v
  Supabase (Postgres) — leads, human_followup tables
```

---

## Prerequisites

- Python 3.12+
- A Supabase project with `db/schema.sql` applied
- API keys: Anthropic, Sarvam, Cartesia, Supabase service key
- Docker (for containerised deploy) or a plain venv (local dev)

---

## Local Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> scaiva2
cd scaiva2

# 2. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
#    requirements.txt pins pipecat-ai==0.0.108. That exact pin matters:
#    it ships the pipecat.services.sarvam.stt module AND pulls the
#    sarvamai (0.1.26) its SarvamSTTService was tested against, which
#    already supports saaras:v3 mode/prompt. Do NOT add a separate
#    sarvamai>= line — it makes pip backtrack pipecat to an STT-less
#    release. See requirements.txt header for the full rationale.
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and fill in all REQUIRED values.

# 5. Apply the database schema
#    Open the Supabase SQL editor (or use psql) and run:
#    db/schema.sql
```

---

## Run Locally

```bash
# Option A — uvicorn reload (recommended for development)
uvicorn app.server:app --reload --host 0.0.0.0 --port 7860

# Option B — module entry-point
python -m app.server
```

Open **http://localhost:7860** in a browser. Click **"Talk to Aria"** and grant mic permission. The agent will greet you in English (switching language if needed).

---

## Docker

```bash
# Build
docker build -t brigade-gateway .

# Run (pass all required env vars or use --env-file)
docker run --env-file .env -p 7860:7860 brigade-gateway
```

---

## Coolify Deploy (Hetzner)

1. Push the repo to your Git provider and connect it to Coolify.
2. Coolify auto-detects the `Dockerfile`; set the exposed port to **7860**.
3. Add every `REQUIRED` variable from `.env.example` under **Environment Variables** in the Coolify UI.
4. Enable **HTTPS** (Let's Encrypt) in Coolify's domain settings — required for browser WebRTC (`getUserMedia` only works on HTTPS or localhost).
5. Trigger a deploy. The first build may take a few minutes (ffmpeg install).
6. Access the public URL; the WebRTC connection will use the Coolify-provisioned TLS cert.

---

## Phase 0 Acceptance / Definition of Done

- [ ] Browser WebRTC call connects and Aria greets the caller in English within 3 s.
- [ ] Barge-in works (caller can interrupt Aria mid-sentence).
- [ ] Language auto-switch: caller speaks Hindi/Telugu, Aria responds in kind.
- [ ] Full qualification flow completes and writes a row to the `leads` table in Supabase.
- [ ] Guardrails fire correctly:
  - [ ] Price question → deflect (does not quote a number).
  - [ ] Legal / title question → defer ("our legal team will follow up").
  - [ ] Cash-deal proposal → politely refuse.
  - [ ] Opt-out phrase → `end_call` tool invoked, call terminates.
- [ ] Unknown / ambiguous intent → `human_followup` row written to Supabase.
- [ ] Application runs inside Docker with no external bind-mounts.
- [ ] Coolify HTTPS deploy passes all of the above checks.

---

## Pipecat Import Paths

pipecat reorganises its internal module layout between minor releases — which
is exactly why `requirements.txt` pins `pipecat-ai==0.0.108` rather than a
range. All service import paths used by the app have been verified against
that pin (see "Verification Status" below). If you bump the pin and see an
`ImportError` for a pipecat service class, check the installed package layout:

```bash
python -c "import pipecat; print(pipecat.__file__)"
find "$(python -c 'import pipecat, os; print(os.path.dirname(pipecat.__file__))')" -name "*.py" | xargs grep -l "SarvamSTT\|CartesiaTTS\|AnthropicLLM" 2>/dev/null
```

Then update the lazy imports in `app/transports.py`, `app/bot.py`, and
`app/server.py` accordingly.

> ⚠️ Known trap: pipecat `0.0.92` ships only `pipecat.services.sarvam.tts`
> (no `.stt`). `0.0.108` ships both. Don't downgrade below 0.0.108.

---

## Verification Status (2026-06-23)

The pipeline has **not** had a live WebRTC call yet (that needs real API keys
+ a browser mic). Everything short of that is verified in a clean venv:

- [x] `pip install -r requirements.txt -r requirements-dev.txt` resolves with
      `pip check` clean → `pipecat 0.0.108`, `sarvamai 0.1.26`.
- [x] All pipecat/Sarvam/Cartesia/Anthropic/WebRTC/VAD import paths resolve.
- [x] `SarvamSTTService.InputParams` exposes `mode` + `prompt` (saaras:v3).
- [x] All `app/*` modules import; FastAPI app boots, startup env-validation
      runs, `GET /health` → 200, `GET /` serves the UI.
- [x] `build_pipeline` assembles the full browser-agent pipeline with REAL
      pipecat components (LLM service, context aggregator, all 5 tools) — proven
      by `tests/test_pipeline_smoke.py`, not just imports.
- [x] Fast test suite green: **62 passed, 5 skipped** (`pytest`) — includes the
      Phase 2 telephony serializer/transport tests and the pipeline smoke test.
- [ ] Live call / Supabase write / guardrails firing — pending real keys
      (tracked in the Phase 0 Definition of Done above).

### How to get the final (live) confirmation

The only remaining unknown is a real audio call. To confirm the browser agent
end-to-end on your machine:

```bash
cp .env.example .env          # fill the 6 REQUIRED keys
# apply db/schema.sql in the Supabase SQL editor
uvicorn app.server:app --host 0.0.0.0 --port 7860
# open http://localhost:7860 → "Talk to Aria" (mic works on localhost/HTTPS)
```

Then walk the Phase 0 Definition of Done checklist above.

---

## Phase 2 — Telephony (Acefone) — BUILT

Inbound PSTN calls reach Aria over a WebSocket using Acefone's Voice-Streaming
protocol (a Twilio Media Streams clone: μ-law 8 kHz, base64, `streamSid`
envelope). The **same** `run_bot` pipeline serves both browser and phone — only
the transport differs.

- Endpoint: **`wss://<your-host>/telephony/ws`** (`app/server.py:telephony_ws`).
  Point your Acefone DID's media-stream webhook here.
- Serializer: `AcefoneFrameSerializer` (`app/serializers.py`) — subclasses
  pipecat's `TwilioFrameSerializer`; `auto_hang_up` defaults off (teardown is
  WebSocket-close, so no provider REST creds are required to run).
- Transport: `create_acefone_transport` (`app/transports.py`) wires a
  `FastAPIWebsocketTransport` at 8 kHz with Silero VAD + interruptions.
- Config: `ACEFONE_API_TOKEN`, `ACEFONE_DID` in `.env` (OPTIONAL — the app boots
  and the browser channel works without them).
- Tests: `tests/test_telephony.py` (handshake parsing, μ-law (de)serialization
  round-trip, interruption→`clear`, transport factory) — all keyless.

> Live-call gate (from the original PRD): verify Sarvam STT keepalive/reconnect
> behaviour (pipecat #3699) before relying on long production phone calls.

## Phase 3 — Outbound campaigns (Not Built)

Automated outbound qualification calls triggered from CRM events. Requires a
dialler/origination integration and a consent-management layer.
