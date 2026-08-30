#!/usr/bin/env bash
# run.sh — entrypoint container sandbox Claude Code.
#
# Tugas:
#   1. Load env dari /secrets/.env (buang komentar & quote).
#   2. Arahkan Claude Code ke proxy lokal 127.0.0.1:8080 + API key dummy.
#   3. Start csmart_proxy.py (background, log ke file), tunggu health sampai up.
#   4. eksekusi `claude "$@"` setelah proxy siap.
#   5. Trap EXIT utk membunuh proxy saat session berakhir.
set -euo pipefail

# ---- 1. Load secrets -------------------------------------------------------
# set -a: export semua var; source file; set +a kembalikan.
# Hanya baris KEY=VALUE yg dimuat; komentar & quote dibuang.
# Secret TIDAK di-echo ke output.
for f in /secrets/.env /secrets/.env.local; do
  if [[ -f "$f" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$f"
    set +a
  fi
done
if [[ ! -f /secrets/.env ]]; then
  echo "WARN: /secrets/.env tidak ditemukan — lanjut tanpa secrets." >&2
fi
# Proxy butuh key asli — simpan ke UPSTREAM_API_KEY sebelum unset untuk Claude nanti
export UPSTREAM_API_KEY="${UPSTREAM_API_KEY:-${ANTHROPIC_AUTH_TOKEN:-}}"

# ---- 2. Arahkan Claude Code ke proxy lokal ---------------------------------
# Proxy jalan DI DALAM container ini di 127.0.0.1:8080.
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:8080}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-dummy}"
export CLAUDE_CODE_SUBPROCESS_ENV_SCRUB="${CLAUDE_CODE_SUBPROCESS_ENV_SCRUB:-1}"

# ---- 3. Proxy — idempotent reuse (autostart adalah source of truth) ---------
# autostart-proxy.sh (postCreate/postStart, hash-aware) adalah pemilik proxy.
# run.sh hanya reuse jika sehat; fallback start hanya jika belum nyala.
# Lokasi target Dockerfile = /opt/csmart/csmart_proxy.py.
# JANGAN balik ke /sandbox/csmart_proxy.py — itu SALAH & tidak konsisten dgn Dockerfile.
PROXY_SCRIPT="${CSMART_PROXY_SCRIPT:-/opt/csmart/csmart_proxy.py}"
PROXY_HOST="${CSMART_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${CSMART_PROXY_PORT:-8080}"
PROXY_LOG="${CSMART_PROXY_LOG:-/tmp/csmart_proxy.log}"
HEALTH_URL="http://${PROXY_HOST}:${PROXY_PORT}"

# trap EXIT hanya kill jika run.sh yang start proxy (PROXY_PID terisi); reuse autostart tidak di-kill
PROXY_PID=""
cleanup() {
  if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" 2>/dev/null; then
    echo "run.sh: mematikan proxy (PID ${PROXY_PID})." >&2
    kill "$PROXY_PID" 2>/dev/null || true
    wait "$PROXY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ---- 4. Health check / fallback start (maks ~45s) ---------------------------
HEALTH_OK=""
if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "run.sh: proxy sudah nyala di ${HEALTH_URL} — reuse (autostart)." >&2
  HEALTH_OK="yes"
else
  if [[ ! -f "$PROXY_SCRIPT" ]]; then
    echo "ERROR: proxy script tidak ada: ${PROXY_SCRIPT}" >&2
    echo "  pastikan Dockerfile menaruh csmart_proxy.py di /opt/csmart/." >&2
    exit 1
  fi
  # fallback: proxy belum nyala — start di sini (mis. docker run manual tanpa postStart)
  pkill -f 'csmart_proxy.py' 2>/dev/null || true
  nohup python3 "$PROXY_SCRIPT" </dev/null >"$PROXY_LOG" 2>&1 &
  PROXY_PID=$!
  TIMEOUT_S="${CSMART_HEALTH_TIMEOUT_S:-45}"
  END=$(( SECONDS + TIMEOUT_S ))
  while (( SECONDS < END )); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      HEALTH_OK="yes"
      break
    fi
    if ! kill -0 "$PROXY_PID" 2>/dev/null; then
      echo "ERROR: csmart_proxy.py mati sebelum Health. Log:" >&2
      tail -n 40 "$PROXY_LOG" >&2
      exit 1
    fi
    sleep 0.5
  done
  if [[ -z "$HEALTH_OK" ]]; then
    echo "ERROR: proxy tidak merespon dalam ${TIMEOUT_S}s. Log:" >&2
    tail -n 40 "$PROXY_LOG" >&2
    exit 1
  fi
fi

# ---- 5. Jalankan Claude Code (pass CLI args) --------------------------------
echo "run.sh: proxy siap di ${HEALTH_URL} — menjalankan claude $*"
# Install deny-rules (G5) ke ~/.claude agar aktif tiap run (tahan rebuild).
mkdir -p "$HOME/.claude"
if [[ -f "$PWD/sandbox/settings.json" ]]; then
  cp "$PWD/sandbox/settings.json" "$HOME/.claude/settings.json"
fi

# unsandboxed: container pakai --cap-drop=ALL jadi bubblewrap tidak bisa jalan.
# Override SCRUB=1 dari devcontainer.json agar claude tidak menuntut bwrap.
export CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0
# Claude vs proxy: proxy sudah dapat UPSTREAM_API_KEY di atas; untuk Claude
# cukup ANTHROPIC_API_KEY=dummy — unset token asli agar tidak bentrok auth.
unset ANTHROPIC_AUTH_TOKEN
export ANTHROPIC_API_KEY=dummy
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080

# Foreground (bukan exec) agar trap EXIT tetap jalan setelah claude keluar
# dan memastikan proxy csmart ikut di-kill (tidak bocor).
claude "$@"