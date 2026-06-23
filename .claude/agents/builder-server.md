# Subagent: builder-server

Owns `app/server.py`. Implements the FastAPI application: `/offer` WebRTC signalling endpoint, `/ws` websocket (if needed), static file serving for `static/`, lifespan startup/shutdown, and uvicorn entry-point. Coordinates with builder-pipeline on how the pipeline is instantiated per call.
