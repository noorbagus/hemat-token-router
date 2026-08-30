# ===========================================================================
# Claude Code sandbox image (arm64, Apple Silicon M1 Pro — no Rosetta)
#
# Base: python:3.14-slim  -> provides Python 3.14 (required by csmart_proxy.py)
# Node: NodeSource arm64 LTS (v22) -> provides Claude Code CLI
#
# Runtime layout:
#   /opt/csmart/csmart_proxy.py  — token-saving proxy (Python 3.14)
#   /secrets/                    — read-only mount target (LANYARD creds, etc.)
#   /workspace                   — VOLUME, overridden via run.sh
#
# Entrypoint: claude  (overridden by run.sh)
# ===========================================================================
FROM --platform=linux/arm64 python:3.14-slim

# ---------------------------------------------------------------------------
# System deps
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
        iptables \
        nftables \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Node.js arm64 (v22 LTS) from NodeSource — Debian's packaged node is too old
# ---------------------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && node --version \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python deps (python:3.14-slim ships pip by default)
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir \
        fastapi \
        httpx \
        uvicorn \
        python-dotenv \
        cryptography

# ---------------------------------------------------------------------------
# Claude Code CLI
# ---------------------------------------------------------------------------
RUN npm install -g @anthropic-ai/claude-code \
    && claude --version

# ---------------------------------------------------------------------------
# App layout: proxy + read-only secrets mount target
# ---------------------------------------------------------------------------
RUN mkdir -p /opt/csmart /secrets /workspace

# Fallback: bind mount in devcontainer.json overrides this for live parity
COPY csmart_proxy.py /opt/csmart/csmart_proxy.py
# Egress firewall deny-by-default (diterapkan via host: docker exec -u 0)
COPY sandbox/init-firewall.sh /opt/csmart/init-firewall.sh
RUN chmod +x /opt/csmart/init-firewall.sh

# ---------------------------------------------------------------------------
# Non-root user
# ---------------------------------------------------------------------------
RUN useradd --create-home --uid 1000 --shell /bin/bash dev \
    && chown -R dev:dev /opt/csmart /secrets /workspace

USER dev
WORKDIR /workspace

# ---------------------------------------------------------------------------
# Ports & entrypoint
# ---------------------------------------------------------------------------
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -fsS http://127.0.0.1:8080/ || exit 1

# Proxy is started separately (via autostart-proxy.sh / devcontainer postStartCommand);
# default command is Claude Code. No ENTRYPOINT — devcontainer forces /bin/sh anyway.
CMD ["claude"]