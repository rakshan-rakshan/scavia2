# Acefone Mock Server

A development/testing mock that simulates the Acefone bi-directional audio streaming API (Twilio Media Streams compatible).

## Quick Start

```bash
cd tools/acefone-mock
pip install -r requirements.txt
python server.py
```

This starts two servers in the same process:

| Server | Port | Purpose |
|--------|------|---------|
| WebSocket | **9002** | Acefone audio streaming protocol (connect from SCAIVA) |
| HTTP | **9003** | REST API + Admin UI |

## WebSocket Protocol (port 9002)

When SCAIVA connects to `ws://localhost:9002/stream?token=test`, the mock server automatically:

1. Sends `{"event": "connected"}`
2. Sends `{"event": "start", ...}` with stream/call metadata
3. Sends silence mu-law media frames (20ms @ 8kHz) every 100ms
4. Listens for client `media`, `mark`, `clear`, and `dtmf` events

### Supported client events

| Event  | Behaviour |
|--------|-----------|
| `media` | Logged — payload is decoded and length recorded |
| `mark`  | Echoed back as a mark-completion event |
| `clear` | Logged |
| `dtmf`  | Logged with digit value |

## REST API (port 9003)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/admin` | Admin UI for manual testing |
| POST | `/click-to-call` | Mock click-to-call; responds with `call_id` / `status` |
| POST | `/dynamic-endpoint` | Mock dynamic endpoint; returns `wss_url` |
| POST | `/webhook` | Echo endpoint — logs received payloads |

## Admin UI

Open `http://localhost:9003/admin` in a browser:

- **Simulate Inbound Call** — sends a `start` event on the active WS connection
- **Send DTMF** — sends a DTMF digit event
- **Hangup** — sends a `stop` event
- **Event Log** — real-time stream of all WS events (via SSE)

## Testing with SCAIVA

Configure SCAIVA to use the mock Acefone:

- WS endpoint: `ws://localhost:9002/stream?token=test`
- Click-to-call: `http://localhost:9003/click-to-call`
- Webhook: `http://localhost:9003/webhook`
