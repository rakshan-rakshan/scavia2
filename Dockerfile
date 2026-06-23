# Brigade Gateway Voice Lead Qualifier
# Base: python:3.12-slim
# Suitable for Coolify auto-deploy on Hetzner.

FROM python:3.12-slim

# System packages needed for:
#   - pipecat silero VAD (native audio ops)
#   - pipecat webrtc (aiortc / SmallWebRTC)
#   - sarvamai / aiohttp TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        libsndfile1 \
        libssl-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY static/ ./static/
COPY knowledge/ ./knowledge/

# Expose the default port (Coolify maps this automatically)
EXPOSE 7860

# PORT can be overridden by Coolify's env var injection.
# uvicorn reads HOST/PORT from the environment via app.server (which calls
# settings.host / settings.port); we pass them explicitly here as a fallback.
CMD ["sh", "-c", "uvicorn app.server:app --host ${HOST:-0.0.0.0} --port ${PORT:-7860}"]
