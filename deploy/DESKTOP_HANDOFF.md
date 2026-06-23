# Desktop Handoff — run & demo the Aria voice agent locally

**Paste this whole file as your first message to Claude on the desktop (it has full
local PC access: Docker, microphone, browser).** Your job: get the Aria browser
voice agent actually *talking* on this machine, on a cheap provider stack, so the
user can judge it and compare it against **dograh**.

> Why local: the agent needs outbound access to OpenRouter/Sarvam and a real
> mic+browser. A `localhost` page is a "secure context", so the mic works with **no
> domain/HTTPS** — unlike a remote server. This is the fastest path to talking to it.

---

## 1. Get the code

```bash
git clone https://github.com/rakshan-rakshan/scavia2.git && cd scavia2
git checkout claude/kind-hamilton-7knu0b
```
Branch to use: **`claude/kind-hamilton-7knu0b`**. Don't push elsewhere without asking.

---

## 2. What this is (1 paragraph)

"Aria" is a self-hosted, multilingual (EN/HI/TE) AI voice agent that qualifies
real-estate leads for **Brigade Gateway** over the browser in real time, applies
strict business guardrails (never quote price, never invent facts, honour opt-out),
and can capture leads to Supabase. Built on **pipecat**. Pipeline:
Browser (SmallWebRTC/WebRTC) → FastAPI → Silero VAD → **Sarvam STT** →
**LLM (OpenRouter by default)** → TTS (**Cartesia** for English if configured, else
**Sarvam** ) → playback. LLM tool-calls drive lead capture / language switch /
human handoff / end-call.

---

## 3. The provider stack (cheap by design — NOT Anthropic)

The LLM is **provider-flexible** via `LLM_PROVIDER` (`openrouter` default | `openai`
| `anthropic`). Default is **OpenRouter** (`openai/gpt-4o-mini`), so you only need
**two keys to talk to Aria**:

| Role | Provider | Env var(s) | Required? |
|---|---|---|---|
| LLM | **OpenRouter** (cheap, any model) | `OPENROUTER_API_KEY`, `LLM_MODEL` | ✅ required |
| STT + fallback voice | **Sarvam** | `SARVAM_API_KEY` | ✅ required |
| English voice (premium) | **Cartesia** | `CARTESIA_API_KEY` + `CARTESIA_VOICE_ID` | optional (else Sarvam EN) |
| Lead storage | **Supabase** | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | optional (else demo: leads logged to console) |
| Alt STT/TTS | Deepgram | needs `pip install pipecat-ai[deepgram]` | not wired by default |

**Get the actual key values from the user** and put them in `.env` (next step).
The user holds keys for OpenRouter, Sarvam, Cartesia, and Deepgram. Their Anthropic
account is empty — do **not** use `LLM_PROVIDER=anthropic`.
⚠️ Tell the user to **rotate** any keys they pasted into a chat once testing is done.

---

## 4. Run it (Docker — recommended)

```bash
cp .env.example .env
# Edit .env and set AT MINIMUM:
#   OPENROUTER_API_KEY=sk-or-...        (openrouter.ai → add ~$5 credit → create key)
#   SARVAM_API_KEY=...
# Optional for premium English voice:
#   CARTESIA_API_KEY=...  and  CARTESIA_VOICE_ID=<a voice id from the Cartesia dashboard>
# Optional for real lead capture: SUPABASE_URL + SUPABASE_SERVICE_KEY (then apply db/schema.sql)
# LLM_PROVIDER defaults to openrouter; LLM_MODEL defaults to openai/gpt-4o-mini.

docker compose up --build
```
Then open **http://localhost:7860** → click **"Talk to Aria"** → allow the mic.

### Or run without Docker
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest                       # expect 66 passed, 5 skipped (no keys/network needed)
uvicorn app.server:app --host 0.0.0.0 --port 7860
```

---

## 5. What success looks like (demo checklist)

- Page loads, mic permission granted, "Talk to Aria" connects (WebRTC).
- Aria **greets in English within a few seconds**, 1–3 short sentences.
- Natural back-and-forth; she qualifies (name, purpose, budget band, timeline)
  without interrogating, and proposes two site-visit slots.
- **Guardrails hold**: if asked for an exact price she declines ("On Request",
  offers a consultant callback); she never invents unit facts; if the user says
  "don't contact me" she apologises, confirms, and ends the call.
- Say "switch to Hindi"/"Telugu" → she continues in that language (Sarvam voice).
- In demo mode (no Supabase), watch the server console: captured lead fields and
  tool calls are logged there.

If anything underperforms, the cheapest knob is `LLM_MODEL` in `.env` — try a
stronger OpenRouter model (e.g. `openai/gpt-4o`, `anthropic/claude-3.5-sonnet`,
`google/gemini-2.0-flash-001`) and restart.

---

## 6. Troubleshooting

- **Mic blocked**: must be `http://localhost` (secure context). A LAN IP or plain
  http remote will have the mic disabled by the browser — use localhost here.
- **Startup error about a missing key**: `config.py` validates provider-aware —
  for `openrouter` you need `OPENROUTER_API_KEY`; always need `SARVAM_API_KEY`.
- **403 / auth errors mid-call**: a provider key is wrong or out of credit.
- **No English audio / odd voice**: Cartesia not set → English falls back to Sarvam
  (expected). For premium EN, set both `CARTESIA_API_KEY` and `CARTESIA_VOICE_ID`.
- **Port busy**: change `PORT` in `.env` (and the compose port mapping).
- **Tool calls not firing** (lead not captured): weaker models sometimes skip
  tools — bump `LLM_MODEL`.

---

## 7. The actual ask: compare with dograh, keep the best

The user also self-hosts **dograh** (open-source Vapi/Retell alternative,
`github.com/dograh-hq/dograh`) which they like for its simplicity (BYOK, visual
builder, in-dashboard "Web Call"). They want to run **both** and keep whichever is
better. Help them:
1. Get this (scavia2/Aria) talking locally per above.
2. If their dograh clone has errors, help fix it (they'll share that repo).
3. Compare on: voice latency/quality, guardrail reliability, multilingual EN/HI/TE,
   ease of editing the qualification flow, and cost. Recommend a path.

The substance of scavia2 worth preserving regardless of platform: the **Aria
persona + qualification script + guardrails** (`app/system_prompt.py`), the
**knowledge base** (`knowledge/KNOWLEDGE_BASE.md`), the **lead schema**
(`db/schema.sql`), and the **tools** (`app/tools.py`). These port into dograh as a
prompt/workflow + webhook if dograh wins.

---

## 8. Later: host it for real (20–30 concurrent calls)

See `deploy/COSTING.md`. Summary: needs a **dedicated-CPU** box (this is CPU-bound
on WebRTC media + Silero VAD; the AI runs on APIs, no GPU). Plan ~3–4 calls/vCPU →
~8 vCPU to start (resize to 16 for full 30 after a load test). Recommended:
DigitalOcean/Vultr **Bangalore**, CPU-Optimized 8 vCPU/16 GB, Ubuntu 24.04. A remote
deploy needs a **domain + HTTPS** (browser mic requires a secure context on remote).
API usage cost dominates the server cost at that concurrency — budget on call-minutes.
Repo has deploy artifacts (Dockerfile, Caddy/WebRTC config under `deploy/`).

---

## 9. Conventions

- Tests must run with **no keys/network** (live LLM eval is opt-in behind
  `RUN_LLM_EVAL=1 pytest -m llm_eval`). Keep them green.
- Keep `requirements.txt` pins (`pipecat-ai==0.0.108`); dev-only deps go in
  `requirements-dev.txt`.
- Don't hardcode secrets — everything via `.env` / `config.py`.
- Develop on `claude/kind-hamilton-7knu0b`; commit with clear messages.
