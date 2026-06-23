# Hosting Cost & Capacity — 20–30 concurrent calls

> Prices are **approximate** (verify current rates). All sized for sustained
> real-time audio, which needs **dedicated vCPUs** (not shared/burstable).

## What drives the server size
Per concurrent call the box runs: WebRTC media (Opus), **Silero VAD** (per-stream
ONNX inference), and audio resampling. The LLM/STT/TTS run on external APIs, so
the server is CPU-bound on audio, not AI. Rule of thumb (conservative, validate
with a load test): **~3–4 calls per dedicated vCPU**.

- ~30 concurrent  → **~16 dedicated vCPU / 32 GB** (comfortable + headroom)
- ~10–15 concurrent → **~8 dedicated vCPU / 16–32 GB** (lean start, then scale)

Network is trivial (~3–6 Mbps for 30 audio calls).

## Server cost comparison — TARGET (~30 calls, 16 vCPU dedicated / 32 GB)

| Provider | Region | Spec | ~ $/mo | Notes |
|---|---|---|---|---|
| **Hetzner CCX43** | EU only | 16 ded. vCPU / 64 GB | **~$140** | Cheapest by far. BUT +~130 ms to Indian users *and* to Sarvam (India API) — audible in conversation. |
| **Vultr Optimized** | Bangalore | 16 vCPU / 32 GB | **~$320** | India region, good price |
| **DigitalOcean CPU-Optimized** | Bangalore (BLR1) | 16 vCPU / 32 GB | **~$336** | India region, simplest UX |
| **AWS c7g.4xlarge** | Mumbai | 16 vCPU / 32 GB | ~$430 on-demand (~$260 w/ 1-yr reserved) | Enterprise; +EBS/egress |

## Server cost comparison — LEAN START (~10–15 calls, 8 vCPU dedicated)

| Provider | Region | Spec | ~ $/mo |
|---|---|---|---|
| Hetzner CCX33 | EU | 8 ded. vCPU / 32 GB | ~$70 |
| Vultr Optimized | Bangalore | 8 vCPU / 16 GB | ~$160 |
| DigitalOcean CPU-Optimized | BLR1 | 8 vCPU / 16 GB | ~$168 |
| AWS c7g.2xlarge | Mumbai | 8 vCPU / 16 GB | ~$216 (~$130 reserved) |

## ⚠️ The cost that actually dominates: API usage
At 30 concurrent calls the **per-minute API spend dwarfs the server bill.**
Very rough, per ~5-minute call (verify against live pricing):
- Claude Sonnet 4.6 (LLM): ~$0.10–0.30
- Sarvam STT + TTS: ~$0.05–0.20
- (Cartesia EN TTS, optional): ~$0.05–0.15
→ **~$0.30–0.65 per call.** 30 calls running back-to-back ≈ ~$60–150 **per hour**
of API cost. Server cost is a rounding error next to this — model your budget on
call-minutes, not the droplet.

## Honesty on capacity (must do before trusting 30 concurrent)
The app **works** but has **not been load-tested or tuned for high concurrency**:
1. It currently runs a single uvicorn process → needs **multiple worker
   processes / containers** to use all cores.
2. WebRTC peer state is held **in-process** (`_connections` dict), so multi-worker
   needs **sticky routing** (or each call must stay on the worker that answered
   its `/api/offer`). Minor code/infra work before scaling.
3. The 3–4 calls/vCPU figure is an estimate — **run a load test** to calibrate
   before committing to a tier.

## Hetzner CCX line (chosen) — dedicated AMD vCPU, EU

> Decision: starting on Hetzner for cost. Prices ~excl. VAT, verify live.

| Plan | vCPU / RAM | ~ €/mo | Est. concurrent calls* | Use |
|---|---|---|---|---|
| **CCX23** | 4 ded. / 16 GB | ~€25 | **~12–15** | Pilot / local-parity testing |
| **CCX33** | 8 ded. / 32 GB | ~€49 | **~24–32** | The real 20–30 target |
| CCX43 | 16 ded. / 64 GB | ~€96 | ~48–60 | Headroom / growth |

*at ~3–4 calls/vCPU, conservative — confirm with a load test.

**So:** CCX23 is fine to start and prove it out, but **CCX33 is the one that
actually meets 20–30 concurrent.** Pick the EU location closest to India —
**Falkenstein or Nuremberg (Germany)** — for the least bad latency.

⚠️ **Hetzner = EU latency, eyes open.** The audio loop crosses to the EU twice
each turn: Indian caller ↔ EU server (~130 ms) AND EU server ↔ **Sarvam** (STT/TTS
is India-hosted, ~130 ms). OpenRouter (LLM) is global. This adds noticeable
round-trip vs a Bangalore box. Acceptable for testing/pilot; if conversational
latency feels off in production, the fix is a Bangalore server (Vultr/DO) — the
deploy is identical, only the provider/region changes.

## Recommendation
India product → **Vultr or DigitalOcean, Bangalore, 16 vCPU dedicated / 32 GB**
for the 30-call target. Or start on the **8 vCPU lean** box, load-test, and size
up. Pick Hetzner only if budget rules and you accept the EU latency hit.
