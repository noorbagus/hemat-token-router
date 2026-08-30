#!/usr/bin/env bash
#
# apply-firewall.sh — terapkan egress DENY-BY-DEFAULT ke container devcontainer.
#
# Latar: container tak bisa self-apply firewall (devcontainer force entrypoint
# /bin/sh & postStartCommand jalan sbg user non-root), jadi dipicu dari HOST
# via `docker exec -u 0`. Butuh --cap-add=NET_ADMIN di runArgs (sudah diatur).
#
# Usage:
#   bash sandbox/apply-firewall.sh              # pakai container yg berjalan
#   CONTAINER=<id> bash sandbox/apply-firewall.sh
set -euo pipefail

CONTAINER="${CONTAINER:-}"

if [[ -z "$CONTAINER" ]]; then
  # Temukan container dari image devcontainer hemat-token-router
  CONTAINER=$(docker ps -q --filter 'status=running' --filter 'ancestor=vsc-hemat-token-router*' | head -1 || true)
fi
if [[ -z "$CONTAINER" ]]; then
  echo "ERROR: tidak ada container devcontainer berjalan (atau set CONTAINER=<id>)." >&2
  exit 1
fi

echo "apply-firewall: menerapkan firewall ke container $CONTAINER ..."
docker exec -u 0 "$CONTAINER" /opt/csmart/init-firewall.sh
echo "apply-firewall: selesai."