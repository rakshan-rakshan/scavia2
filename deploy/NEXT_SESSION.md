# Paste this into a new session to continue (deploy Aria online)

## State (everything below is DONE and pushed)
- Repo `rakshan-rakshan/scavia2`, branch **`claude/kind-hamilton-7knu0b`**.
- Phase 0 browser voice agent + Phase 2 Acefone telephony: **code complete, 66 tests pass.**
- Install blocker fixed (pipecat 0.0.108 pin). App boots; full pipeline assembles
  and reaches real APIs (verified). Demo mode = runs with just 2 keys.
- **Deploy artifacts ready** in `deploy/`: `docker-compose.prod.yml`, `Caddyfile`,
  `setup.sh`, `RUNBOOK.md`. Target: `aria.vaticanninfra.in` on a DigitalOcean
  Bangalore droplet, Docker + Caddy (auto-TLS), STUN-only.

## What the human must provide before it can talk (NOT code issues)
1. **Anthropic credits** — account is at $0 (key authenticates but every call
   returns "credit balance too low"). console.anthropic.com → Plans & Billing.
2. **Rotated** Anthropic + Sarvam keys (old ones were shared in chat).
3. **DigitalOcean droplet** (BLR1, Ubuntu 24.04, 2vCPU/4GB) + its public IP.
4. **DNS A-record**: `aria.vaticanninfra.in` → droplet IP.

## The task for the new session
Deploy by following `deploy/RUNBOOK.md`. The user chose **"grant SSH, you drive."**
So: get the droplet IP + SSH access, then run the runbook steps over SSH.
CAVEAT: confirm the session's network can actually SSH out (this prior sandbox
blocked outbound to non-Anthropic hosts). If SSH-out is blocked, hand the user
the copy-paste commands from the runbook instead.

Do NOT re-plan or re-ask settled decisions. Just execute the runbook.
