"""HTTP header helpers for the csmart reverse proxy (S-1 header whitelist).

Pure functions: given a :class:`fastapi.Request`, build the upstream header map
from the allowlist. No I/O, no logging — extracted from ``router/dispatcher.py``
so the proxy engine stays focused on orchestration.

S-1 header whitelist: only allowlisted headers are forwarded upstream.
``x-api-key`` deliberately stays in the default allowlist (deviation from the
original plan, which would have stripped it): the Anthropic SDK can send auth
either as ``Authorization: Bearer`` (``ANTHROPIC_AUTH_TOKEN``) or as
``x-api-key`` (``ANTHROPIC_API_KEY``), and the proxy has no token-injection
mechanism, so it forwards whichever the client sends. Live-verified
2026-08-28: the ``ark.talaga.my.id`` gateway REQUIRES ``authorization`` and
rejects ``x-api-key`` (401), so Claude Code must set ``ANTHROPIC_AUTH_TOKEN``
(Bearer), not ``ANTHROPIC_API_KEY``. The real hardening win is stripping
``cookie``, ``user-agent``, ``sec-*``, ``referer``, ``origin`` and every other
non-allowlisted header (including the internal ``x-csmart-session``, which
stays local). An operator can drop ``x-api-key`` via
``CSMART_HEADER_ALLOWLIST`` if their gateway accepts only ``authorization``.
"""

from __future__ import annotations

import os
from typing import Dict

from fastapi import Request

_DEFAULT_HEADER_ALLOWLIST = frozenset({
    "authorization", "x-api-key", "content-type", "accept",
    "anthropic-version", "anthropic-beta", "x-app",
})


def _header_allowlist() -> frozenset[str]:
    raw = os.environ.get("CSMART_HEADER_ALLOWLIST")
    if not raw:
        return _DEFAULT_HEADER_ALLOWLIST
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _build_upstream_headers(request: Request) -> Dict[str, str]:
    """Copy only allowlisted client headers upstream (S-1 header whitelist).

    ``content-encoding`` is deliberately NOT forwarded (NIT): Claude Code sends
    uncompressed JSON bodies, and forwarding a compressed body without the
    matching header would corrupt the upstream read. If a client ever sends an
    encoded body it is rejected/decoded downstream before it is re-sent.
    """
    allow = _header_allowlist()
    headers: Dict[str, str] = {}
    for name, value in request.headers.items():
        if name.lower() in allow:
            headers[name] = value
    return headers
