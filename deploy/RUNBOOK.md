# Aria — Online Deploy Runbook (`aria.vaticanninfra.in`)

Goal: a public HTTPS URL you open in a browser to talk to Aria.

## 0. What only YOU can do first (the real blockers)

| # | Action | Where |
|---|--------|-------|
| 1 | **Get an OpenRouter key** + add ~$5 credit (the LLM; Anthropic is NOT used) | openrouter.ai → Keys |
| 2 | **Rotate** the Sarvam/Cartesia/Deepgram keys that were shared in chat | each provider's console |
| 3 | **Create server**: Hetzner **CCX33** (8 vCPU/32 GB) for the 20–30 target, or **CCX23** (4 vCPU/16 GB) to pilot; **Falkenstein/Nuremberg**, Ubuntu 24.04 | hetzner.com/cloud |
| 4 | **DNS**: add A-record `aria.vaticanninfra.in` → server public IP | your DNS for vaticanninfra.in |

Cartesia (premium English voice) and Supabase (lead storage) are OPTIONAL —
without them, English uses Sarvam and leads are logged (demo mode). The agent
still talks with just the two required keys.

## 1. Bootstrap the server (once)

```bash
ssh root@<server-ip>
git clone <your-repo-url> scavia2 && cd scavia2
git checkout claude/kind-hamilton-7knu0b
bash deploy/setup.sh          # installs Docker + opens firewall
```

## 2. Configure secrets

```bash
cp .env.example .env
nano .env
# REQUIRED (rotated values):
#   OPENROUTER_API_KEY=sk-or-...        # LLM_PROVIDER defaults to openrouter
#   SARVAM_API_KEY=...
#   LLM_MODEL=openai/gpt-4o-mini        # optional; bump for better quality
# OPTIONAL: CARTESIA_API_KEY+CARTESIA_VOICE_ID (premium EN voice),
#           SUPABASE_URL+SUPABASE_SERVICE_KEY (real lead capture) — blank = demo mode
```

## 3. Confirm DNS, then launch

```bash
dig +short aria.vaticanninfra.in     # must show the server IP before next step
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml logs -f   # watch for "Aria server starting"
```

Caddy will fetch a TLS cert automatically (needs the A-record live + ports 80/443 open).

## 4. Test (the first real voice call)

Open **https://aria.vaticanninfra.in**, click **Talk to Aria**, allow the mic.
Expected: Aria greets in English within ~3s; barge-in works; ask in Hindi/Telugu
to hear it switch.

## 5. Troubleshooting

- **Cert won't issue** → A-record not propagated yet, or port 80 blocked. `dig` it; check `ufw status`.
- **Connects but silent (no audio)** → WebRTC UDP blocked. Confirm `ufw` allows `32768:60999/udp`; some corporate/mobile networks block UDP entirely — that's when you add a TURN server (coturn) as a follow-up.
- **LLM 401/402 in logs** → OpenRouter key wrong or out of credit (step 0.1).
- **Sarvam 403** → wrong/rotated key, or Sarvam account issue.
- **Conversation feels laggy** → expected on an EU (Hetzner) box for India callers
  + India-hosted Sarvam; if unacceptable, redeploy the same stack on a Bangalore
  VM (Vultr/DO) — only the region changes.

## 6. Update after a code change

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Later: Acefone telephony (Phase 2, already coded)

Point your Acefone DID's media-stream webhook at:
`wss://aria.vaticanninfra.in/telephony/ws`
(No redeploy needed — the endpoint already ships.)
