#!/usr/bin/env bash
#
# init-firewall.sh — egress DENY-BY-DEFAULT (allowlist) untuk sandbox container.
#
# Konsep: mengikuti pola firewall dev-container Claude Code (anthropics/claude-code)
# tapi kita pakai iptables-based (lebih portabel) dengan fallback nft.
#
# Policy: semua outbound DROP, hanya yang di-allowlist yang boleh keluar:
#   1. Upstream proxy csmart  -> ${UPSTREAM_BASE_URL} (default deepseek:443) & opencode:443 (kedua endpoint terpakai)
#   2. Loopback 127.0.0.0/8   -> agar 127.0.0.1:8080 jalan antar-proses
#   3. (Opsional, default off) git/registry: registry.npmjs.org, github.com, deb.debian.org
#
# Deterministik & idempotent — boleh di-`docker exec` tiap start.
# Exit non-zero + pesan jelas kalau gagal dapat root/permission.
set -euo pipefail

UPSTREAM_BASE_URL="${UPSTREAM_BASE_URL:-https://api.deepseek.com/anthropic}"
# Claude Code preflight reachability check (startup ping) — hardcoded ke api.anthropic.com,
# terpisah dari jalur model (model I/O tetap via proxy 127.0.0.1:8080 -> opencode).
ANTHROPIC_PREFLIGHT_HOST="${ANTHROPIC_PREFLIGHT_HOST:-api.anthropic.com}"

# ---- 1. Wajib root ---------------------------------------------------------
if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: init-firewall.sh harus dijalankan sebagai root." >&2
  echo "  contoh: docker exec -u 0 CONTAINER /opt/csmart/init-firewall.sh" >&2
  exit 1
fi

# ---- 2. Ekstrak host upstream (buang proto & path) ---------------------------
UPSTREAM_HOST="$(printf '%s' "$UPSTREAM_BASE_URL" | sed -E 's#^[a-z][a-z0-9+.-]*://##; s#[/?#].*$##')"
if [[ -z "$UPSTREAM_HOST" ]]; then
  echo "ERROR: UPSTREAM_BASE_URL tidak valid: '${UPSTREAM_BASE_URL}'" >&2
  exit 1
fi
OPENAI_UPSTREAM_URL="${CSMART_OPENAI_BASE_URL:-${OPENAI_BASE_URL:-https://opencode.ai/zen/go/v1}}"
OPENAI_HOST=$(echo "$OPENAI_UPSTREAM_URL" | sed -E 's|https?://||' | cut -d'/' -f1 | cut -d':' -f1)

# ---- 3. (Opsional) allowlist git / registry — default OFF --------------------
# Untuk mengaktifkan, buka comment & isi host yang diizinkan, mis:
#   GIT_ALLOW="registry.npmjs.org github.com deb.debian.org"
GIT_ALLOW="${GIT_ALLOW:-}"

# ---- 4. Pilih engine: iptables (portable), fallback nft ----------------------
FIREWALL_ENGINE="${FIREWALL_ENGINE:-iptables}"
if ! command -v iptables >/dev/null 2>&1; then
  if command -v nft >/dev/null 2>&1; then
    echo "iptables tidak tersedia — fallback ke nft."
    FIREWALL_ENGINE="nft"
  else
    echo "ERROR: tidak ada iptables maupun nft di container ini." >&2
    exit 1
  fi
fi

# ---- 5. setup via iptables ----------------------------------------------------
setup_iptables() {
  # bersihkan aturan lama dulu -> idempotent
  iptables -F OUTPUT 2>/dev/null || true
  iptables -F FORWARD 2>/dev/null || true

  # default policy: DROP semua outbound & forward
  iptables -P OUTPUT DROP
  iptables -P FORWARD DROP

  # allow reply dari koneksi ESTABLISHED/RELATED (mis. respon upstream)
  iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

  # 1. loopback 127.0.0.0/8 -> proxy 127.0.0.1:8080 antar-proses
  iptables -A OUTPUT -d 127.0.0.0/8 -j ACCEPT

  # 1b. DNS resolver (UDP/TCP 53) — wajib agar host allowlist bisa resolve.
  #     Tradeoff: DNS tunneling kecil; tanpa ini semua egress mati (tak bisa resolve).
  iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
  iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

  # 2. upstream csmart: TCP 443
  iptables -A OUTPUT -p tcp -d "$UPSTREAM_HOST" --dport 443 -j ACCEPT
  if [[ "$OPENAI_HOST" != "$UPSTREAM_HOST" && -n "$OPENAI_HOST" ]]; then
    iptables -A OUTPUT -p tcp -d "$OPENAI_HOST" --dport 443 -j ACCEPT
  fi

  # 2c. Claude Code preflight ping (startup reachability) -> api.anthropic.com
  #     Reachability only; model I/O tetap via proxy 127.0.0.1:8080 -> opencode.
  iptables -A OUTPUT -p tcp -d "$ANTHROPIC_PREFLIGHT_HOST" --dport 443 -j ACCEPT

  # 3. (jika diaktifkan) git / registry
  if [[ -n "$GIT_ALLOW" ]]; then
    for host in $GIT_ALLOW; do
      iptables -A OUTPUT -p tcp -d "$host" --dport 443 -j ACCEPT
      iptables -A OUTPUT -p tcp -d "$host" --dport 80 -j ACCEPT
    done
  fi

  echo "iptables: egress deny-by-default terpasang (policy DROP)."
}

# ---- 6. setup via nft -----------------------------------------------------------
setup_nft() {
  nft flush ruleset 2>/dev/null || true

  nft add table inet csmart_fw
  # chain output hook, policy drop
  nft add chain inet csmart_fw output "{ type filter hook output priority 0; policy drop; }"

  # allow reply established/related
  nft add rule inet csmart_fw output ct state established,related accept

  # 1. loopback
  nft add rule inet csmart_fw output ip daddr 127.0.0.0/8 accept

  # 1b. DNS resolver (UDP/TCP 53) — wajib agar host allowlist bisa resolve
  nft add rule inet csmart_fw output udp dport 53 accept
  nft add rule inet csmart_fw output tcp dport 53 accept

  # 2. upstream TCP 443
  nft add rule inet csmart_fw output ip daddr "$UPSTREAM_HOST" tcp dport 443 accept
  if [[ "$OPENAI_HOST" != "$UPSTREAM_HOST" && -n "$OPENAI_HOST" ]]; then
    nft add rule inet csmart_fw output ip daddr "$OPENAI_HOST" tcp dport 443 accept
  fi

  nft add rule inet csmart_fw output ip daddr "$ANTHROPIC_PREFLIGHT_HOST" tcp dport 443 accept

  # 3. git / registry (opsional)
  if [[ -n "$GIT_ALLOW" ]]; then
    for host in $GIT_ALLOW; do
      nft add rule inet csmart_fw output ip daddr "$host" tcp dport 443 accept
      nft add rule inet csmart_fw output ip daddr "$host" tcp dport 80 accept
    done
  fi

  echo "nft: egress deny-by-default terpasang (chain policy drop)."
}

# ---- 7. Eksekusi -------------------------------------------------------------
if [[ "$FIREWALL_ENGINE" == "iptables" ]]; then
  if ! setup_iptables; then
    echo "ERROR: gagal memasang iptables (permission/modules?). Jalankan via docker exec -u root." >&2
    exit 1
  fi
else
  if ! setup_nft; then
    echo "ERROR: gagal memasang firewall via nft." >&2
    exit 1
  fi
fi

echo "init-firewall.sh: selesai. Egress DENY-BY-DEFAULT aktif."
if [[ "$OPENAI_HOST" != "$UPSTREAM_HOST" && -n "$OPENAI_HOST" ]]; then
  echo "  allow: 127.0.0.0/8 (loopback); TCP 443 -> ${UPSTREAM_HOST}, ${OPENAI_HOST}"
else
  echo "  allow: 127.0.0.0/8 (loopback); TCP 443 -> ${UPSTREAM_HOST}"
fi
echo "  drop : semua outbound lain (git/registry: buka comment GIT_ALLOW)"