"""
Acefone Mock Server — Development/Testing Tool

Simulates Acefone's bi-directional audio streaming WebSocket API
and REST endpoints for local development and testing.

Protocol matches Acefone's (Twilio-compatible) Media Streams API:
  - WS server on port 9002: bidirectional audio streaming
  - HTTP server on port 9003: REST API + Admin UI

Usage:
    python server.py
"""

import asyncio
import base64
import json
import logging
import time
import uuid
from collections import deque

import aiohttp
from aiohttp import web
import websockets
from websockets.asyncio.server import serve as ws_serve

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WS_HOST = "0.0.0.0"
WS_PORT = 9002
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 9003

SAMPLE_RATE = 8000
FRAME_MS = 20
FRAME_SIZE = SAMPLE_RATE * FRAME_MS // 1000  # 160 bytes

# mu-law silence: 0x7F is the mid-scale (zero) value
SILENCE_BYTE = b"\x7f"
SILENCE_FRAME = SILENCE_BYTE * FRAME_SIZE

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger("acefone-mock")


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
class CallState:
    def __init__(self):
        self.active_ws: websockets.asyncio.server.ServerConnection | None = None
        self.stream_sid: str = ""
        self.call_sid: str = ""
        self.account_sid: str = ""
        self.call_active: bool = False
        self.media_task: asyncio.Task | None = None
        self.events: deque = deque(maxlen=2000)
        self.event_listeners: list[asyncio.Queue] = []
        self.admin_client_queues: list[asyncio.Queue] = []

    def add_event(self, direction: str, data: dict):
        entry = {
            "timestamp": time.time(),
            "iso": time.strftime("%H:%M:%S", time.localtime()),
            "direction": direction,
            "data": data,
        }
        self.events.append(entry)
        logger.debug("[%s] %s", direction, data.get("event", json.dumps(data)[:80]))
        for q in self.admin_client_queues:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass
        return entry

    def generate_call_ids(self, from_number="+15551234567", to_number="+15557654321"):
        self.stream_sid = "MZ" + uuid.uuid4().hex[:16]
        self.call_sid = "CA" + uuid.uuid4().hex[:16]
        self.account_sid = "AC" + uuid.uuid4().hex[:8]
        self.from_number = from_number
        self.to_number = to_number


state = CallState()


# ---------------------------------------------------------------------------
# Mu-law frame helpers
# ---------------------------------------------------------------------------
def encode_mulaw_frame(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


# ---------------------------------------------------------------------------
# WebSocket server – speaks Acefone / Twilio-compatible protocol
# ---------------------------------------------------------------------------
async def ws_handler(websocket):
    """Handle a WebSocket client (Dograh) connecting to the mock Acefone."""
    state.active_ws = websocket
    state.generate_call_ids()
    state.call_active = True
    remote = websocket.remote_address
    logger.info("WS client connected: %s", remote)

    try:
        # 1. connected event
        connected = {"event": "connected"}
        await websocket.send(json.dumps(connected))
        state.add_event("server->client", connected)
        await asyncio.sleep(0.05)

        # 2. start event
        start = {
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "streamSid": state.stream_sid,
                "callSid": state.call_sid,
                "accountSid": state.account_sid,
                "from": state.from_number,
                "to": state.to_number,
                "direction": "inbound",
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": SAMPLE_RATE,
                    "bitRate": 64,
                    "bitDepth": 8,
                },
            },
        }
        await websocket.send(json.dumps(start))
        state.add_event("server->client", start)
        await asyncio.sleep(0.05)

        # 3. spawn background silence-media sender
        async def _send_media():
            seq = 1
            while state.call_active and state.active_ws and not state.active_ws.closed:
                try:
                    media = {
                        "event": "media",
                        "streamSid": state.stream_sid,
                        "media": {
                            "payload": encode_mulaw_frame(SILENCE_FRAME),
                            "track": "outbound",
                        },
                    }
                    await state.active_ws.send(json.dumps(media))
                    seq += 1
                    await asyncio.sleep(FRAME_MS / 1000)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception:
                    break

        state.media_task = asyncio.create_task(_send_media())

        # 4. read loop – handle client messages
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("invalid JSON from client: %.100s", message)
                continue

            state.add_event("client->server", data)
            event_type = data.get("event")

            if event_type == "media":
                payload_b64 = data.get("media", {}).get("payload", "")
                raw = base64.b64decode(payload_b64) if payload_b64 else b""
                logger.debug("client media: %d bytes", len(raw))

            elif event_type == "mark":
                name = data.get("mark", {}).get("name", "")
                echo = {
                    "event": "mark",
                    "streamSid": state.stream_sid,
                    "mark": {"name": name},
                }
                await websocket.send(json.dumps(echo))
                state.add_event("server->client", echo)

            elif event_type == "clear":
                logger.info("clear event: %s", data)

            elif event_type == "dtmf":
                digit = data.get("dtmf", {}).get("digit", "")
                logger.info("DTMF from client: digit=%s", digit)

    except websockets.exceptions.ConnectionClosed:
        logger.info("WS client disconnected")
    except Exception as exc:
        logger.error("WS handler error: %s", exc)
    finally:
        state.call_active = False
        if state.media_task:
            state.media_task.cancel()
            state.media_task = None
        state.active_ws = None


# ---------------------------------------------------------------------------
# HTTP server – REST API + Admin UI
# ---------------------------------------------------------------------------
async def handle_health(request):
    return web.json_response({"status": "ok", "service": "acefone-mock"})


async def handle_click_to_call(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    to_number = body.get("to_number", "")
    from_number = body.get("from_number", "")
    webhook_url = body.get("webhook_url", "")
    api_key = body.get("api_key", "")
    is_async = body.get("async", 0)

    logger.info(
        "click-to-call: from=%s to=%s webhook=%s async=%s",
        from_number, to_number, webhook_url, is_async,
    )

    if is_async == 1:
        resp = {"async": True, "ref_id": uuid.uuid4().hex[:12]}
    else:
        resp = {
            "call_id": uuid.uuid4().hex[:12],
            "status": "queued",
            "to": to_number,
            "from": from_number,
        }

    # Fire webhook
    if webhook_url:
        asyncio.ensure_future(_fire_webhook(webhook_url, resp))

    return web.json_response(resp)


async def handle_dynamic_endpoint(request):
    body = await request.json() if request.can_read_body else {}
    logger.info("dynamic-endpoint called: %s", json.dumps(body)[:200])
    return web.json_response({
        "success": True,
        "wss_url": f"wss://localhost:{WS_PORT}/stream?token=test",
        "call_id": uuid.uuid4().hex[:12],
    })


async def handle_webhook(request):
    body = await request.json() if request.can_read_body else {}
    logger.info("webhook received: %s", json.dumps(body)[:300])
    state.add_event("webhook", {"payload": body})
    return web.json_response({"success": True, "echo": body})


async def handle_events_sse(request):
    """Server-Sent Events endpoint for admin live log."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    state.admin_client_queues.append(q)
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await resp.prepare(request)
    try:
        # Send existing events
        for ev in list(state.events)[-100:]:
            await resp.write(f"data: {json.dumps(ev)}\n\n".encode())
        while True:
            ev = await q.get()
            await resp.write(f"data: {json.dumps(ev)}\n\n".encode())
    except (ConnectionResetError, ConnectionAbortedError):
        pass
    finally:
        if q in state.admin_client_queues:
            state.admin_client_queues.remove(q)
    return resp


async def handle_simulate_call(request):
    """Admin action: simulate a new inbound call on the active WS connection."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    from_number = body.get("from", "+15551234567")
    to_number = body.get("to", "+15557654321")

    ws = state.active_ws
    if not ws or ws.closed:
        return web.json_response({"error": "no active WS connection"}, status=400)

    state.generate_call_ids(from_number, to_number)

    start = {
        "event": "start",
        "sequenceNumber": "1",
        "start": {
            "streamSid": state.stream_sid,
            "callSid": state.call_sid,
            "accountSid": state.account_sid,
            "from": from_number,
            "to": to_number,
            "direction": "inbound",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": SAMPLE_RATE,
                "bitRate": 64,
                "bitDepth": 8,
            },
        },
    }
    await ws.send(json.dumps(start))
    state.add_event("admin", start)
    return web.json_response({"status": "call_simulated", "call_sid": state.call_sid})


async def handle_send_dtmf(request):
    """Admin action: send DTMF event to the active WS connection."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    digit = body.get("digit", "1")
    ws = state.active_ws
    if not ws or ws.closed:
        return web.json_response({"error": "no active WS connection"}, status=400)

    dtmf = {
        "event": "dtmf",
        "streamSid": state.stream_sid,
        "callSid": state.call_sid,
        "dtmf": {
            "digit": digit,
            "tone": digit,
            "duration": 100,
        },
    }
    await ws.send(json.dumps(dtmf))
    state.add_event("admin", dtmf)
    return web.json_response({"status": "dtmf_sent", "digit": digit})


async def handle_hangup(request):
    """Admin action: send stop event and disconnect."""
    ws = state.active_ws
    if not ws or ws.closed:
        return web.json_response({"error": "no active WS connection"}, status=400)

    stop = {
        "event": "stop",
        "streamSid": state.stream_sid,
        "stop": {"callSid": state.call_sid},
    }
    await ws.send(json.dumps(stop))
    state.add_event("admin", stop)
    state.call_active = False
    return web.json_response({"status": "hangup_sent"})


async def handle_admin(request):
    """Admin HTML page."""
    html = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Acefone Mock Server — Admin</title>
<style>
  :root { --bg: #0d1117; --surface: #161b22; --border: #30363d; --text: #c9d1d9; --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; background: var(--bg); color: var(--text); padding: 24px; font-size: 14px; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  .subtitle { color: #8b949e; margin-bottom: 24px; font-size: 13px; }
  .dashboard { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 1200px; }
  @media (max-width: 800px) { .dashboard { grid-template-columns: 1fr; } }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .card h2 { font-size: 15px; margin-bottom: 12px; color: var(--accent); }
  label { display: block; font-size: 12px; margin-top: 10px; margin-bottom: 4px; color: #8b949e; }
  input, select { width: 100%; padding: 8px 10px; background: #0d1117; border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 13px; }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .row { display: flex; gap: 10px; }
  .row > * { flex: 1; }
  button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; margin-top: 12px; transition: opacity .15s; }
  button:hover { opacity: .85; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-success { background: var(--green); color: #fff; }
  .btn-danger { background: var(--red); color: #fff; }
  .btn-warning { background: var(--yellow); color: #fff; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  #log-panel { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 10px; height: 400px; overflow-y: auto; font-family: 'SF Mono','Cascadia Code','Consolas',monospace; font-size: 11px; line-height: 1.6; margin-top: 12px; }
  .log-entry { border-bottom: 1px solid #21262d; padding: 3px 0; }
  .log-time { color: #8b949e; }
  .log-s2c { color: var(--green); }
  .log-c2s { color: var(--accent); }
  .log-admin { color: var(--yellow); }
  .log-webhook { color: #bc8cff; }
  .badge { display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 10px; font-weight: 600; margin-left: 6px; }
  .badge-green { background: #1b3a1f; color: var(--green); }
  .badge-blue { background: #1c314e; color: var(--accent); }
  .conn-status { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .dot-red { background: var(--red); box-shadow: 0 0 6px var(--red); }
  .clear-btn { float: right; font-size: 11px; padding: 3px 10px; margin-top: 0; background: transparent; border: 1px solid var(--border); color: var(--text); }
</style>
</head>
<body>

<h1>Acefone Mock Server</h1>
<p class="subtitle">WS :9002 &middot; HTTP :9003 &middot; <span id="conn-status" class="badge badge-red">Disconnected</span></p>

<div class="dashboard">

  <!-- Column 1: Controls -->
  <div>
    <div class="card">
      <h2>Simulate Inbound Call</h2>
      <div class="row">
        <div>
          <label>From Number</label>
          <input id="from-number" value="+15551234567">
        </div>
        <div>
          <label>To Number</label>
          <input id="to-number" value="+15557654321">
        </div>
      </div>
      <label>Call Duration (seconds)</label>
      <input id="call-duration" type="number" value="10" min="1" max="120">
      <button class="btn-success" id="btn-call">Simulate Inbound Call</button>
    </div>

    <div class="card">
      <h2>Send DTMF</h2>
      <label>Digit</label>
      <select id="dtmf-digit">
        <option>1</option><option>2</option><option>3</option>
        <option>4</option><option>5</option><option>6</option>
        <option>7</option><option>8</option><option>9</option>
        <option>0</option><option>*</option><option>#</option>
      </select>
      <button class="btn-warning" id="btn-dtmf">Send DTMF</button>
    </div>

    <div class="card">
      <h2>Hangup</h2>
      <p style="font-size:13px;color:#8b949e;">Send a stop event to the active call.</p>
      <button class="btn-danger" id="btn-hangup">Hangup</button>
    </div>

    <div class="card">
      <h2>REST API Test</h2>
      <label>Click-to-Call</label>
      <button class="btn-primary" id="btn-ctc">POST /click-to-call</button>
      <label style="margin-top:12px;">Dynamic Endpoint</label>
      <button class="btn-primary" id="btn-dep">POST /dynamic-endpoint</button>
    </div>
  </div>

  <!-- Column 2: Log -->
  <div>
    <div class="card" style="height:100%;display:flex;flex-direction:column;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <h2 style="margin-bottom:0;">Event Log</h2>
        <button class="clear-btn" id="btn-clear-log">Clear</button>
      </div>
      <div id="log-panel"></div>
    </div>
  </div>

</div>

<script>
(function() {
  'use strict';

  const logPanel = document.getElementById('log-panel');
  const connStatus = document.getElementById('conn-status');

  function logEntry(ev) {
    const d = ev.data ? JSON.parse(ev.data) : ev;
    const ts = d.iso || '--:--:--';
    const dir = d.direction || '';
    const data = d.data || {};
    const eventName = data.event || (typeof data === 'string' ? data : '');
    const payload = JSON.stringify(data, null, 0).substring(0, 200);

    const el = document.createElement('div');
    el.className = 'log-entry';

    let dirClass = 'log-s2c';
    if (dir === 'client->server') dirClass = 'log-c2s';
    else if (dir === 'admin') dirClass = 'log-admin';
    else if (dir === 'webhook') dirClass = 'log-webhook';

    let label = dir;
    if (eventName) label += ' ' + eventName;

    el.innerHTML = `<span class="log-time">[${ts}]</span> <span class="${dirClass}">${label}</span> ${payload}`;
    logPanel.appendChild(el);
    logPanel.scrollTop = logPanel.scrollHeight;
  }

  // SSE
  const evtSource = new EventSource('/events');
  evtSource.onmessage = function(ev) {
    logEntry(ev);
    try {
      const d = JSON.parse(ev.data);
      if (d.data && d.data.event === 'connected') {
        connStatus.textContent = 'Connected';
        connStatus.className = 'badge badge-green';
      }
      if (d.data && d.data.event === 'stop') {
        connStatus.textContent = 'Disconnected';
        connStatus.className = 'badge badge-red';
      }
    } catch(e) {}
  };
  evtSource.onerror = function() {
    connStatus.textContent = 'SSE Error';
    connStatus.className = 'badge badge-red';
  };

  document.getElementById('btn-clear-log').onclick = function() {
    logPanel.innerHTML = '';
  };

  async function post(path, body) {
    const r = await fetch(path, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
    const j = await r.json();
    logEntry({ iso: new Date().toLocaleTimeString(), direction: 'admin', data: { event: 'API ' + path, response: j } });
    return j;
  }

  document.getElementById('btn-call').onclick = function() {
    post('/simulate-call', {
      from: document.getElementById('from-number').value,
      to: document.getElementById('to-number').value,
    });
  };

  document.getElementById('btn-dtmf').onclick = function() {
    post('/send-dtmf', { digit: document.getElementById('dtmf-digit').value });
  };

  document.getElementById('btn-hangup').onclick = function() {
    post('/hangup', {});
  };

  document.getElementById('btn-ctc').onclick = function() {
    post('/click-to-call', {
      to_number: '+15557654321',
      from_number: '+15551234567',
      webhook_url: 'http://localhost:9003/webhook',
      api_key: 'test-key-123',
    });
  };

  document.getElementById('btn-dep').onclick = function() {
    post('/dynamic-endpoint', {});
  };

  // Load existing events
  fetch('/events')
    .then(r => r.text())
    .then(text => {
      text.split('\n').filter(l => l.startsWith('data: ')).forEach(l => {
        try { logEntry(JSON.parse(l.slice(6))); } catch(e) {}
      });
    });

})();
</script>
</body>
</html>
"""
    return web.Response(text=html, content_type="text/html")


async def _fire_webhook(url: str, payload: dict):
    """Fire-and-forget webhook call."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)):
                pass
    except Exception as exc:
        logger.warning("webhook call failed: %s", exc)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_http_app() -> web.Application:
    app = web.Application()

    app.router.add_get("/health", handle_health)
    app.router.add_get("/admin", handle_admin)
    app.router.add_get("/events", handle_events_sse)
    app.router.add_post("/click-to-call", handle_click_to_call)
    app.router.add_post("/dynamic-endpoint", handle_dynamic_endpoint)
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_post("/simulate-call", handle_simulate_call)
    app.router.add_post("/send-dtmf", handle_send_dtmf)
    app.router.add_post("/hangup", handle_hangup)

    return app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
async def main():
    ws_server = await ws_serve(ws_handler, WS_HOST, WS_PORT)

    http_app = create_http_app()
    http_runner = web.AppRunner(http_app)
    await http_runner.setup()
    http_site = web.TCPSite(http_runner, HTTP_HOST, HTTP_PORT)
    await http_site.start()

    logger.info("=" * 50)
    logger.info("Acefone Mock Server started")
    logger.info("  WS  server -> ws://%s:%d/stream?token=test", WS_HOST, WS_PORT)
    logger.info("  HTTP server -> http://%s:%d", HTTP_HOST, HTTP_PORT)
    logger.info("  Admin UI    -> http://%s:%d/admin", HTTP_HOST, HTTP_PORT)
    logger.info("=" * 50)

    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        pass
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await http_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
