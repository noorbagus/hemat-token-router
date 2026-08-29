#!/usr/bin/env bash
# Start liteLLM proxy sebagai pengganti csmart_proxy.py
# Claude Code -> litellm (127.0.0.1:8080) -> opencode-go Responses API (muse-spark)
#
# Usage:
#   scripts/litellm-start.sh            # default port 8080
#   LITELLM_PORT=4000 scripts/litellm-start.sh
set -euo pipefail

ENV_FILE="${ENV_FILE:-/Volumes/Xugab/LAB/PrivateLink/.env.local}"
PORT="${LITELLM_PORT:-8080}"
CONFIG="${LITELLM_CONFIG:-$(cd "$(dirname "$0")/.." && pwd)/litellm.config.yaml}"
LITELLM_BIN="${LITELLM_BIN:-$HOME/.litellm/venv/bin/litellm}"

if [ -f "$ENV_FILE" ]; then
  # Fail-safe: value diambil di dalam subshell, tidak pernah tercetak ke log.
  export OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"')"
fi

# Catatan: JANGAN set DATABASE_URL=sqlite — liteLLM 1.98 menolak (butuh PostgreSQL).
# Proxy dijalankan open-mode (tanpa master_key) sehingga tidak butuh DB.

exec "$LITELLM_BIN" --config "$CONFIG" --port "$PORT"
