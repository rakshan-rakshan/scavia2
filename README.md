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
#    Note: pipecat[sarvam] bundles an old sarvamai; requirements.txt
#    pins sarvamai>=0.1.30 to support saaras:v3 (pipecat issue #3783).
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

pipecat reorganises its internal module layout between minor releases. If you see `ImportError` for a pipecat service class, check the installed package layout:

```bash
python -c "import pipecat; print(pipecat.__file__)"
find "$(python -c 'import pipecat, os; print(os.dirname(pipecat.__file__))')" -name "*.py" | xargs grep -l "SarvamSTT\|CartesiaTTS\|AnthropicLLM" 2>/dev/null
```

Update the import in `app/pipeline.py` (or equivalent) accordingly.

---

## Phase 2 / 3 (Not Built)

- **Phase 2 — Telephony**: Inbound PSTN calls via Acefone DID → SIP → pipecat `DailyTransport` or `TwilioTransport`. Config placeholders are in `.env.example` (`ACEFONE_API_TOKEN`, `ACEFONE_DID`).
- **Phase 3 — Outbound campaigns**: Automated outbound qualification calls triggered from CRM events. Requires dialler integration and consent-management layer.
