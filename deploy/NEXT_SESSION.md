# Handoff — deploy Aria online (Hetzner + OpenRouter)

**Paste this whole file as your first message in the new session.**
Goal of that session: a public HTTPS URL (`https://aria.vaticanninfra.in`) the user
opens in a browser to talk to Aria, on a **Hetzner** server, on the **cheap stack**.

---

## State (DONE and pushed — do not re-do)
- Repo `rakshan-rakshan/scavia2`, branch **`claude/kind-hamilton-7knu0b`**.
- Browser voice agent (Phase 0) + Acefone telephony (Phase 2): **code complete,
  66 tests pass, 5 skipped.** App boots; pipeline assembles.
- **LLM is provider-flexible, default OpenRouter** (cheap, `openai/gpt-4o-mini`).
  Anthropic is NOT used (user's account is empty). Min to run = 2 keys:
  `OPENROUTER_API_KEY` + `SARVAM_API_KEY`. Cartesia/Supabase optional (demo mode).
- **Deploy artifacts ready** in `deploy/`, already updated for Hetzner + OpenRouter:
  `setup.sh` (Docker + ufw), `docker-compose.prod.yml` (host-networking app + Caddy
  auto-TLS), `Caddyfile`, `RUNBOOK.md` (step-by-step), `COSTING.md` (sizing).

## Decisions (settled — don't re-litigate)
- **Host: Hetzner CCX**, EU. Start **CCX23 (4 vCPU/16 GB)** to pilot; use
  **CCX33 (8 vCPU/32 GB)** for the real 20–30 concurrent target. Location
  **Falkenstein or Nuremberg** (least-bad latency to India).
- Trade-off already accepted: an EU box adds latency for Indian callers and to
  India-hosted Sarvam. If prod latency is bad later, redeploy the identical stack
  on a Bangalore VM (Vultr/DO) — only the region/keys change.

## What the human must provide (NOT code issues)
1. **OpenRouter key** + ~$5 credit (the LLM). openrouter.ai → Keys.
2. **Rotated** Sarvam (+ Cartesia/Deepgram if used) keys — old ones were shared in chat.
3. **Hetzner server** (CCX23 or CCX33, Ubuntu 24.04, Falkenstein/Nuremberg) + public IP.
4. **DNS A-record**: `aria.vaticanninfra.in` → server IP. (If a Hetzner Cloud
   Firewall is enabled in the console, open 22/80/443 tcp + 32768-60999 udp there
   too; `setup.sh` already sets ufw on the box.)

## The task
Execute **`deploy/RUNBOOK.md`** end to end:
`bash deploy/setup.sh` → fill `.env` (OPENROUTER + SARVAM) → confirm DNS →
`docker compose -f deploy/docker-compose.prod.yml up -d --build` → open the URL →
Talk to Aria.

**Access model:** user chose "grant SSH, you drive." Get the server IP + SSH access
and run the runbook over SSH.
⚠️ **Caveat:** the Claude-Code-on-the-web sandbox has an egress allowlist that may
block outbound SSH to the server. **Test `ssh root@<ip>` first.** If blocked,
either (a) ask the user to widen this environment's network policy to allow the
server IP, or (b) hand the user the copy-paste runbook commands to run in Hetzner's
web console. Don't burn time fighting egress.

## After it's live
- Smoke test: greeting < ~3 s, barge-in, EN/HI/TE switch, a guardrail (refuse exact
  price), opt-out → ends call. In demo mode, watch server logs for captured fields.
- For true 20–30 concurrent: load-test, then address the multi-worker note in
  `COSTING.md` (in-process `_connections` dict needs sticky routing / per-worker scaling).
- Telephony (already coded): point the Acefone DID media-stream webhook at
  `wss://aria.vaticanninfra.in/telephony/ws`.

Do NOT re-plan settled decisions. Execute the runbook.
