#!/usr/bin/env bash
# autostart-proxy.sh — start csmart_proxy otomatis saat container nyala (idempotent)
# Dipanggil via devcontainer postStartCommand. Curl 200 = sudah jalan, skip.
set -euo pipefail
CUR_HASH=$(for f in /secrets/.env /secrets/.env.local; do
  if [[ -f "$f" ]]; then sha256sum "$f" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$f" 2>/dev/null | cut -d' ' -f1; fi
done | sha256sum | cut -d' ' -f1)
[[ -n "$CUR_HASH" ]] || CUR_HASH="no-env"
SAVED_HASH=$(cat /tmp/.csmart_env_hash 2>/dev/null || echo "")
if curl -fsS http://127.0.0.1:8080/ >/dev/null 2>&1; then
  if [[ "$CUR_HASH" == "$SAVED_HASH" ]]; then
    echo "autostart-proxy: proxy sudah jalan — skip (hash match)"
    exit 0
  fi
  for d in /proc/[0-9]*; do tr '\0' ' ' < "$d/cmdline" 2>/dev/null | grep -q csmart_proxy && kill $(basename $d) 2>/dev/null || true; done; sleep 1
fi
for f in /secrets/.env /secrets/.env.local; do
  if [[ -f "$f" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$f"
    set +a
  fi
done
# UPSTREAM_API_KEY fallback ke ANTHROPIC_AUTH_TOKEN (sesuai csmart_proxy.py:36)
export UPSTREAM_API_KEY="${UPSTREAM_API_KEY:-${ANTHROPIC_AUTH_TOKEN:-}}"
# G3: deny-rules — copy settings.json ke ~/.claude agar attach tanpa run.sh tetap DENY
mkdir -p "$HOME/.claude"
if [[ -f "$PWD/sandbox/settings.json" ]]; then
  cp "$PWD/sandbox/settings.json" "$HOME/.claude/settings.json"
elif [[ -f "/workspace/sandbox/settings.json" ]]; then
  cp "/workspace/sandbox/settings.json" "$HOME/.claude/settings.json"
elif [[ -f "$(dirname "$0")/settings.json" ]]; then
  cp "$(dirname "$0")/settings.json" "$HOME/.claude/settings.json"
fi
nohup python3 /opt/csmart/csmart_proxy.py </dev/null >/tmp/csmart_proxy.log 2>&1 &
sleep 2
if curl -fsS http://127.0.0.1:8080/ >/dev/null 2>&1; then
  echo "autostart-proxy: proxy nyala di http://127.0.0.1:8080"
  echo "$CUR_HASH" > /tmp/.csmart_env_hash 2>/dev/null || true
else
  echo "autostart-proxy: gagal start — tail log:" >&2
  tail -n 30 /tmp/csmart_proxy.log >&2
  exit 1
fi
