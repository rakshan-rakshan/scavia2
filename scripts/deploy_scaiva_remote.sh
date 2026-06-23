#!/usr/bin/env bash
set -euo pipefail
# SCAIVA Remote Deployment Script
# Run on the Oracle VM after it's created

SERVER_IP="${1:?Usage: $0 <SERVER_PUBLIC_IP>}"
FORCE_TURN_RELAY="${FORCE_TURN_RELAY:-false}"
FASTAPI_WORKERS="${FASTAPI_WORKERS:-2}"
ENABLE_TELEMETRY="${ENABLE_TELEMETRY:-false}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLUE}[$(date +%H:%M:%S)] $*${NC}"; }
ok()   { echo -e "${GREEN}[$(date +%H:%M:%S)] $*${NC}"; }
fail() { echo -e "${RED}[$(date +%H:%M:%S)] Error: $*${NC}" >&2; exit 1; }

info "=== SCAIVA Deployment on Oracle Free Tier ==="
info "Server IP: $SERVER_IP"
info "FastAPI workers: $FASTAPI_WORKERS"
info ""

# ── Step 1: Install Docker + Compose ──
info "[1/6] Installing Docker and Docker Compose..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    sudo usermod -aG docker "$USER"
    newgrp docker <<EOF
    # This won't persist, but verifies the group add
EOF
    ok "Docker installed"
else
    ok "Docker already installed ($(docker --version))"
fi

if ! command -v docker compose &>/dev/null; then
    sudo apt-get update && sudo apt-get install -y docker-compose-v2
    ok "Docker Compose installed"
else
    ok "Docker Compose already installed"
fi

# ── Step 2: Create deployment directory ──
info "[2/6] Setting up deployment directory..."
mkdir -p ~/scaiva
cd ~/scaiva

# ── Step 3: Run setup_remote.sh non-interactively ──
info "[3/6] Running remote setup script..."
TURN_SECRET=$(openssl rand -hex 32)
OSS_JWT_SECRET=$(openssl rand -hex 32)

export SERVER_IP
export TURN_SECRET
export DEPLOY_MODE="prebuilt"
export FORCE_TURN_RELAY
export FASTAPI_WORKERS
export ENABLE_TELEMETRY

curl -fsSL -o setup_remote.sh \
    "https://raw.githubusercontent.com/dograh-hq/dograh/main/scripts/setup_remote.sh"
chmod +x setup_remote.sh
# The script will cd into dograh/ or use existing dir
# We set SCAIVA_SKIP_DOWNLOAD=0 to ensure it downloads the bundle
bash setup_remote.sh
ok "setup_remote.sh completed"

# ── Step 4: Override .env with our generated secrets ──
info "[4/6] Finalizing .env configuration..."
cd ~/scaiva/dograh
cat > .env << ENVEOF
ENVIRONMENT=production
SERVER_IP=$SERVER_IP
PUBLIC_HOST=$SERVER_IP
PUBLIC_BASE_URL=https://$SERVER_IP
BACKEND_API_ENDPOINT=https://$SERVER_IP
MINIO_PUBLIC_ENDPOINT=https://$SERVER_IP
TURN_HOST=$SERVER_IP
TURN_SECRET=$TURN_SECRET
FORCE_TURN_RELAY=$FORCE_TURN_RELAY
OSS_JWT_SECRET=$OSS_JWT_SECRET
ENABLE_TELEMETRY=$ENABLE_TELEMETRY
FASTAPI_WORKERS=$FASTAPI_WORKERS
ENVEOF
ok ".env configured"

# ── Step 5: Preflight check ──
info "[5/6] Running preflight validation..."
bash remote_up.sh --preflight-only
ok "Preflight passed"

# ── Step 6: Start the stack ──
info "[6/6] Starting SCAIVA stack..."
info "This will take 2-3 minutes on first boot (pulling images)..."
bash remote_up.sh
ok "SCAIVA stack started!"
info ""
info "============================================"
info "  SCAIVA is now deploying on your server!"
info ""
info "  URL:   https://$SERVER_IP"
info "  NOTE:  Accept self-signed cert warning"
info ""
info "  Ports: 443 (HTTPS), 3478/5349 (TURN)"
info ""
info "  To check status:"
info "    cd ~/scaiva/dograh && docker compose ps"
info ""
info "  To view logs:"
info "    cd ~/scaiva/dograh && docker compose logs -f api"
info "============================================"

# ── Wait for health check ──
info "Waiting for API to be healthy (up to 120s)..."
for i in $(seq 1 24); do
    if curl -skf "https://$SERVER_IP/api/v1/health" >/dev/null 2>&1; then
        ok "API is healthy!"
        break
    fi
    if [ "$i" -eq 24 ]; then
        fail "API failed to become healthy in time. Check logs."
    fi
    sleep 5
done

info "Checking UI availability..."
for i in $(seq 1 12); do
    if curl -skf "https://$SERVER_IP" >/dev/null 2>&1; then
        ok "UI is responding!"
        break
    fi
    if [ "$i" -eq 12 ]; then
        fail "UI failed to respond. Check logs."
    fi
    sleep 5
done

ok "=== DEPLOYMENT COMPLETE ==="
ok "Open https://$SERVER_IP in your browser"
