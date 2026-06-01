#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SCAIVA_INIT_WORKSPACE_DIR:-/workspace}"
OUTPUT_ROOT="${SCAIVA_INIT_OUTPUT_ROOT:-/generated}"
NGINX_OUTPUT_DIR="$OUTPUT_ROOT/nginx"
COTURN_OUTPUT_DIR="$OUTPUT_ROOT/coturn"
CERTS_DIR="${SCAIVA_INIT_CERTS_DIR:-/certs}"

# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/setup_common.sh"

SCAIVA_DEPLOY_PROJECT_DIR="$WORKSPACE_DIR"

mkdir -p "$NGINX_OUTPUT_DIR" "$COTURN_OUTPUT_DIR"

if [[ "${ENVIRONMENT:-local}" == "production" ]]; then
    scaiva_validate_remote_runtime_env
    [[ -f "$CERTS_DIR/local.crt" ]] || scaiva_fail "certs/local.crt not found"
    [[ -f "$CERTS_DIR/local.key" ]] || scaiva_fail "certs/local.key not found"

    export TURN_EXTERNAL_IP="$SERVER_IP"
    scaiva_render_remote_nginx_conf "$WORKSPACE_DIR" "$NGINX_OUTPUT_DIR/default.conf"
    scaiva_render_remote_turn_conf "$WORKSPACE_DIR" "$COTURN_OUTPUT_DIR/turnserver.conf"
    scaiva_success "✓ dograh-init rendered remote nginx and coturn config"
    exit 0
fi

if [[ -n "${TURN_SECRET:-}" && -n "${TURN_HOST:-}" ]]; then
    export TURN_EXTERNAL_IP="$TURN_HOST"
    scaiva_render_remote_turn_conf "$WORKSPACE_DIR" "$COTURN_OUTPUT_DIR/turnserver.conf"
    scaiva_success "✓ dograh-init rendered local TURN config"
    exit 0
fi

scaiva_success "✓ dograh-init no-op for current profile"
