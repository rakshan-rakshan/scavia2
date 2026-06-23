#!/usr/bin/env bash
# One-time droplet bootstrap for Aria. Run as root on a fresh Ubuntu 24.04
# DigitalOcean droplet (Bangalore / BLR1 recommended for India latency):
#
#   bash deploy/setup.sh
#
# Installs Docker + compose plugin and opens the firewall for HTTPS + WebRTC.
set -euo pipefail

echo ">>> Installing Docker..."
apt-get update
apt-get install -y ca-certificates curl ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo ">>> Configuring firewall (ufw)..."
ufw allow OpenSSH
ufw allow 80/tcp          # Caddy HTTP (ACME challenge + redirect)
ufw allow 443/tcp         # Caddy HTTPS (app + WebSocket signaling)
ufw allow 32768:60999/udp # WebRTC media (aiortc ephemeral UDP range)
ufw --force enable

echo ""
echo ">>> Done. Next steps:"
echo "    1. git clone <repo> && cd scavia2"
echo "    2. cp .env.example .env   # fill ANTHROPIC_API_KEY + SARVAM_API_KEY (rotated)"
echo "    3. Ensure aria.vaticanninfra.in A-record points to: $(curl -s -4 ifconfig.me || echo '<this droplet IP>')"
echo "    4. docker compose -f deploy/docker-compose.prod.yml up -d --build"
echo "    5. Open https://aria.vaticanninfra.in  ->  Talk to Aria"
