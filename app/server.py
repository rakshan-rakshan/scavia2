"""FastAPI server — serves the SmallWebRTC browser UI and the /api/offer signaling.

Phase 0 entry point. Run with:
    uvicorn app.server:app --host 0.0.0.0 --port 7860
or:
    python -m app.server
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.bot import run_bot
from app.config import SUPPORTED_LANGUAGES, get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aria.server")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Aria — Brigade Gateway Voice Agent")

# Active SmallWebRTC connections, keyed by pc_id (for renegotiation/cleanup).
_connections: dict[str, object] = {}


@app.on_event("startup")
async def _validate_env() -> None:
    # Fail fast if required secrets are missing (raises before serving traffic).
    get_settings()
    logger.info("Aria server starting; required env validated.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/offer")
async def offer(request: dict, background_tasks: BackgroundTasks) -> dict:
    """WebRTC signaling handshake from the browser (matches static/index.html)."""
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    sdp = request.get("sdp")
    sdp_type = request.get("type")
    pc_id = request.get("pc_id")
    lang = (request.get("lang") or "en").lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"

    # Renegotiation of an existing connection.
    if pc_id and pc_id in _connections:
        conn = _connections[pc_id]
        await conn.renegotiate(sdp=sdp, type=sdp_type)
        return conn.get_answer()

    ice = [IceServer(urls="stun:stun.l.google.com:19302")]
    conn = SmallWebRTCConnection(ice)
    await conn.initialize(sdp=sdp, type=sdp_type)

    @conn.event_handler("closed")
    async def _on_closed(c):  # noqa: ANN001
        _connections.pop(c.pc_id, None)
        logger.info("connection closed: %s", c.pc_id)

    transport = SmallWebRTCTransport(
        webrtc_connection=conn,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Run the conversation pipeline for this connection in the background.
    background_tasks.add_task(run_bot, transport, "browser", lang)

    answer = conn.get_answer()
    _connections[answer["pc_id"]] = conn
    return answer


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# Serve any additional static assets (app.js / style.css if the UI split them).
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run("app.server:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    main()
