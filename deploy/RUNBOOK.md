# Aria — Online Deploy Runbook (`aria.vaticanninfra.in`)

Goal: a public HTTPS URL you open in a browser to talk to Aria.

## 0. What only YOU can do first (the real blockers)

| # | Action | Where |
|---|--------|-------|
| 1 | **Add Anthropic credits** (account is at $0 → Aria can't think) | console.anthropic.com → Plans & Billing |
| 2 | **Rotate** the Anthropic + Sarvam keys that were shared in chat | each provider's console |
| 3 | **Create droplet**: DigitalOcean, region **Bangalore (BLR1)**, Ubuntu 24.04, 2 vCPU / 4 GB | digitalocean.com |
| 4 | **DNS**: add A-record `aria.vaticanninfra.in` → droplet public IP | your DNS for vaticanninfra.in |

Cartesia (premium English voice) and Supabase (lead storage) are OPTIONAL —
without them, English uses Sarvam and leads are logged (demo mode). The agent
still talks with just the two required keys.

## 1. Bootstrap the droplet (once)

```bash
ssh root@<droplet-ip>
git clone <your-repo-url> scavia2 && cd scavia2
git checkout claude/kind-hamilton-7knu0b
bash deploy/setup.sh          # installs Docker + opens firewall
```

## 2. Configure secrets

```bash
cp .env.example .env
nano .env
# REQUIRED (rotated values):
#   ANTHROPIC_API_KEY=sk-ant-...
#   SARVAM_API_KEY=...
# OPTIONAL: CARTESIA_*, SUPABASE_* (leave blank for demo mode)
```

## 3. Confirm DNS, then launch

```bash
dig +short aria.vaticanninfra.in     # must show the droplet IP before next step
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
- **"credit balance too low"** in logs → Anthropic credits not added (step 0.1).
- **Sarvam 403** → wrong/rotated key, or Sarvam account issue.

## 6. Update after a code change

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Later: Acefone telephony (Phase 2, already coded)

Point your Acefone DID's media-stream webhook at:
`wss://aria.vaticanninfra.in/telephony/ws`
(No redeploy needed — the endpoint already ships.)
