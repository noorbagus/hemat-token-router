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
if [[ -f /secrets/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' /secrets/.env | sed -E 's/^([^=]+)=["'"'"']?(.*)["'"'"']?$/\1=\2/')
  set +a
else
  echo "WARN: /secrets/.env tidak ditemukan — lanjut tanpa secrets." >&2
fi

# ---- 2. Arahkan Claude Code ke proxy lokal ---------------------------------
# Proxy jalan DI DALAM container ini di 127.0.0.1:8080.
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:8080}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-dummy}"
export CLAUDE_CODE_SUBPROCESS_ENV_SCRUB="${CLAUDE_CODE_SUBPROCESS_ENV_SCRUB:-1}"

# ---- 3. Start proxy ---------------------------------------------------------
# Lokasi target Dockerfile = /opt/csmart/csmart_proxy.py.
# JANGAN balik ke /sandbox/csmart_proxy.py — itu SALAH & tidak konsisten dgn Dockerfile.
PROXY_SCRIPT="${CSMART_PROXY_SCRIPT:-/opt/csmart/csmart_proxy.py}"
PROXY_HOST="${CSMART_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${CSMART_PROXY_PORT:-8080}"
PROXY_LOG="${CSMART_PROXY_LOG:-/tmp/csmart_proxy.log}"
HEALTH_URL="http://${PROXY_HOST}:${PROXY_PORT}"

if [[ ! -f "$PROXY_SCRIPT" ]]; then
  echo "ERROR: proxy script tidak ada: ${PROXY_SCRIPT}" >&2
  echo "  pastikan Dockerfile menaruh csmart_proxy.py di /opt/csmart/." >&2
  exit 1
fi

# bersihkan proxy lama yg mungkin tersisa (idempotent)
pkill -f 'csmart_proxy.py' 2>/dev/null || true

# trap EXIT utk kill proxy saat session berakhir (error path & exit normal non-exec)
PROXY_PID=""
cleanup() {
  if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" 2>/dev/null; then
    echo "run.sh: mematikan proxy (PID ${PROXY_PID})." >&2
    kill "$PROXY_PID" 2>/dev/null || true
    wait "$PROXY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# start proxy (background, log ke file, tidak terhubung stdin)
nohup python3 "$PROXY_SCRIPT" </dev/null >"$PROXY_LOG" 2>&1 &
PROXY_PID=$!

# ---- 4. Poll health (maks ~45s) ---------------------------------------------
HEALTH_OK=""
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

# ---- 5. Jalankan Claude Code (pass CLI args) --------------------------------
echo "run.sh: proxy siap di ${HEALTH_URL} — menjalankan claude $*"
# Foreground (bukan exec) agar trap EXIT di atas tetap jalan setelah claude
# keluar dan memastikan proxy csmart ikut di-kill (tidak bocor).
claude "$@"