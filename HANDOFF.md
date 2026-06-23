# Session Handoff — Brigade Gateway Voice Lead Qualifier (`scavia2`)

**Paste this whole file as your first message in the new session.**

---

## 0. First thing the new session must do

This repo's code currently lives **only inside the previous session's container** and in a
git bundle the user holds. Before anything else:

1. Confirm the new session's repo scope **includes `rakshan-rakshan/scavia2`**
   (the prior session was locked to `omi-automation` + `real-estate-voice-agent` and
   physically could not reach `scavia2` — that was the entire blocker, not credentials).
2. The full project (with history) is in **`scavia2.bundle`** that the user has.
   If the new container is empty, ask the user to drop the bundle in, then:
   ```bash
   git clone scavia2.bundle scavia2 && cd scavia2
   git remote set-url origin https://github.com/rakshan-rakshan/scavia2.git
   git push -u origin claude/gracious-meitner-yed7qa
   ```
   If the repo is already cloned/scoped, just verify `git log` shows commit
   `1acdfa6 feat: Phase 0 …` and push the branch.

**Develop on branch:** `claude/gracious-meitner-yed7qa`. Do NOT push elsewhere without asking.

---

## 1. What this project is

A self-hosted, multilingual (English / Hindi / Telugu) **AI voice agent ("Aria")** that
qualifies real-estate leads over the **browser** in real time via WebRTC, applies
business guardrails, and writes qualified-lead rows to **Supabase**.

**Pipeline (pipecat):**
Browser (SmallWebRTC) → FastAPI `/offer` `/ws` → Silero VAD → Sarvam STT (`saaras:v3`) →
Anthropic LLM (`claude-sonnet-4-6`) → TTS split: **Cartesia `sonic-2`** for English,
**Sarvam `bulbul:v2`** for Hindi/Telugu → playback. Tool calls write to Supabase.

---

## 2. Status — Phase 0 is INSTALL-VERIFIED & BOOT-VERIFIED, NOT yet live

- ✅ All source written and committed.
- ✅ **49 fast tests passing** (no keys/network): `pytest` → `tests/test_tools.py`,
  `tests/test_guardrails.py` (guardrail prompt-logic + tool side-effects).
- ✅ **Dependency + import blocker RESOLVED (2026-06-23).** `requirements.txt`
  now pins `pipecat-ai==0.0.108`. Clean-venv install resolves with `pip check`
  clean, every pipecat import path resolves, and the FastAPI app boots
  (`/health` → 200, `/` serves UI). See README "Verification Status".
- ⚠️ **Still never run live.** No real API keys were used. The pipeline has NOT
  connected a real browser call, real STT/TTS, or a real Supabase write yet —
  that is the remaining Phase 0 work (needs the 6 REQUIRED keys + a browser).
- ✅ **pipecat import paths (was the #1 risk) — verified** against the pinned
  0.0.108 for `SarvamSTTService` / `SarvamTTSService` / `CartesiaTTSService` /
  `AnthropicLLMService` / SmallWebRTC transport / Silero VAD.
- ✅ **saaras:v3 / sarvamai (was pipecat issue #3783) — resolved.** There is no
  published `sarvamai 0.1.30`; that old pin was unsatisfiable and blocked every
  install. pipecat 0.0.108 pins `sarvamai==0.1.26`, whose SarvamSTTService
  already accepts `mode`/`prompt`. The override line was removed. Verify:
  `python -c "import pipecat, sarvamai; print(pipecat.__version__, sarvamai.__version__)"`
  → expect `0.0.108 0.1.26`.

---

## 3. File map

```
app/
  server.py         FastAPI app: /offer (WebRTC), /ws, serves static/index.html
  bot.py            Pipecat pipeline assembly + run loop
  transports.py     SmallWebRTC transport wiring
  tools.py          LLM tools: capture_lead, switch_language, flag_for_human,
                    transfer_to_human, end_call  + Supabase upsert/insert helpers
  system_prompt.py  Aria persona, qualification script, guardrail instructions
  config.py         env loading + REQUIRED/OPTIONAL validation
static/index.html   Browser client ("Talk to Aria" button, WebRTC offer)
db/schema.sql       Supabase tables: leads, human_followup, (+ call log)
knowledge/KNOWLEDGE_BASE.md   Project + domain knowledge (Brigade Gateway)
tests/              47 passing fast tests + opt-in live LLM guardrail eval
                    (marker: llm_eval, gated by RUN_LLM_EVAL=1)
.claude/agents/     Subagent role defs (planner, builder-*, verifier, simplifier)
Dockerfile          port 7860, ffmpeg installed
.env.example        all REQUIRED/OPTIONAL vars documented
requirements.txt / requirements-dev.txt / pytest.ini
```

---

## 4. Required env vars (see `.env.example` for full notes)

REQUIRED: `ANTHROPIC_API_KEY`, `SARVAM_API_KEY`, `CARTESIA_API_KEY`,
`CARTESIA_VOICE_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
OPTIONAL (have defaults): `ANTHROPIC_MODEL`, `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL`,
`SARVAM_TTS_SPEAKER`, `CARTESIA_MODEL`, `HOST`, `PORT`.

---

## 5. How to run / verify

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest                                  # expect 47 passing
cp .env.example .env                    # fill in REQUIRED keys
# apply db/schema.sql in Supabase SQL editor
uvicorn app.server:app --reload --host 0.0.0.0 --port 7860
# open http://localhost:7860 → "Talk to Aria" (mic needs HTTPS or localhost)
```

---

## 6. Next steps (recommended order)

1. **Get `scavia2` into scope + push the branch** (section 0).
2. **First live smoke test**: install deps, fix any pipecat import errors, run a real
   browser call with real keys. Confirm Aria greets in English < 3 s.
3. Work the **Phase 0 Definition of Done** checklist in README (barge-in, language
   auto-switch, full qualification → `leads` row, all guardrails fire, opt-out → `end_call`).
4. Optional: run the live guardrail eval — `RUN_LLM_EVAL=1 pytest -m llm_eval`.
5. **Phase 2 (not built)**: telephony via Acefone DID → SIP (placeholders in `.env.example`).
6. **Phase 3 (not built)**: outbound campaigns from CRM events.

---

## 7. Project conventions

- LLM = Anthropic Claude. Default to current models (`claude-sonnet-4-6` for low-latency
  live calls). Do not downgrade.
- Keep `requirements.txt` pins; edit dev deps only in `requirements-dev.txt`.
- Tests must stay runnable with **no keys/network** (live stuff is opt-in behind markers).
