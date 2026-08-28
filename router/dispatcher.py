"""FastAPI reverse-proxy engine for csmart (absorbs ``router/proxy.py``).

Wave 2 (Fase 3): this module replaces ``router/proxy.py`` as the single proxy
engine. It owns the FastAPI app, the inbound interception pipeline
(AST -> Ollama -> gate -> inject), the outbound SSE parser with exploration
tool-use shadowing, and upstream reliability (timeout + bounded retry).

Frozen public API (CONTRACTS.md §4):
    app, handle_messages_request, forward_streaming_request,
    check_ollama_health, check_upstream_health

Absorbed names kept for backward compatibility with the old ``proxy.py``:
    inject_context_to_messages, run_local_routing, passthrough_request,
    proxy_handler

CLI subprocess dispatch moved to ``router/cli_dispatch.py``; the two names are
re-exported here only for the merge window so ``csmart.py`` stays importable
until the orchestrator repoints its imports.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from router import ast_extractor, ollama_scorer
from router.gate import GateResult, apply_gate
from router.logger import (
    AST_SCANNED,
    INBOUND_REQUEST,
    OLLAMA_TRIAGE,
    SSE_STREAM_COMPLETE,
    TOOL_LOCAL_EXEC,
    TOOL_SHADOW_INTERCEPT,
    logger,
)
from router.ollama_scorer import RoutingResult, triage_model
from router.routing_cache import LRURoutingCache, TTLRoutingCache
from router.safe_path import PathTraversalError, resolve_under_base
from router.tool_shadow import (
    TOOL_NAMES,
    execute_local_tool,
    summarize_exploration,
)

# Backward-compat re-exports for the merge window (orchestrator repoints csmart.py).
from router.cli_dispatch import DispatchResult, dispatch_claude, read_file_content

# ---------------------------------------------------------------------------
# Configuration (environment-driven, defaults mirror proxy.py / CLAUDE.md).
# ---------------------------------------------------------------------------

UPSTREAM_BASE_URL = os.environ.get("ANTHROPIC_UPSTREAM_URL", "https://ark.talaga.my.id")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
CONFIDENCE_THRESHOLD = float(os.environ.get("CSMART_THRESHOLD", "0.65"))
DEFAULT_BUDGET_TOKENS = int(os.environ.get("CSMART_BUDGET", "16000"))
DEFAULT_IGNORE_DIRS: set[str] = {
    ".git", "node_modules", "dist", "build", ".next",
    "venv", ".venv", ".dart_tool", "coverage", ".turbo", ".cache",
    "__pycache__", ".pytest_cache",
}

# Upstream reliability (P-3): configurable timeout + bounded retry.
MAX_UPSTREAM_RETRIES = 2
# Shadow loop bound (N-4 / OD-3): at most this many exploration tool_use
# blocks are held and resolved locally per request.
MAX_SHADOW_ROUNDS = 3
# max_tokens floor (issue #1): mirrors the ark Smart Gate clamp
# (gateway/proxy.py). Below the floor the upstream can cut a tool_use stream
# mid-JSON, leaving input={} / a partial argument blob that starves the shadow
# loop into an error-retry loop. Default 4096 (env CSMART_MIN_MAX_TOKENS).
_DEFAULT_MIN_MAX_TOKENS = 4096

# stdlib logger used for caplog-compatible warnings (inject path-safety).
_stdlib_logger = logging.getLogger("csmart.proxy")

# Test/transport hook: when set, every upstream client uses this transport
# (e.g. ``httpx.MockTransport`` in hermetic tests). Defaults to the real net.
_UPSTREAM_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None

# ---------------------------------------------------------------------------
# Caches (P-1): AST cache keyed by context_dir, routing cache keyed by session.
# ---------------------------------------------------------------------------

_AST_CACHE: Dict[str, List[str]] = {}
_AST_CACHE_LOCK = threading.Lock()
# Routing caches delegate to the tested classes in ``router.routing_cache``
# (P-1 session LRU + P-0 context-dir TTL). Global names are kept stable so the
# hermetic test fixtures can reset them per-test. The TTL cache reads the env
# var ``CSMART_ROUTING_TTL`` via its internal env provider (default 120s, cap 16).
_ROUTING_CACHE: LRURoutingCache = LRURoutingCache(max_entries=128)
_ROUTING_TTL_CACHE: TTLRoutingCache = TTLRoutingCache(
    max_entries=16,
    default_ttl_seconds=120.0,
)


class UpstreamError(Exception):
    """Raised when the upstream gateway is unreachable after retries."""


def _upstream_timeout() -> float:
    try:
        return float(os.environ.get("CSMART_UPSTREAM_TIMEOUT", "60"))
    except ValueError:
        return 60.0


def _min_max_tokens() -> int:
    """Floor for ``max_tokens`` (mirrors ark Smart Gate). Env-overridable."""
    try:
        return int(os.environ.get("CSMART_MIN_MAX_TOKENS", str(_DEFAULT_MIN_MAX_TOKENS)))
    except ValueError:
        return _DEFAULT_MIN_MAX_TOKENS


def _clamp_max_tokens(body: Dict[str, Any]) -> None:
    """Force ``body["max_tokens"]`` up to the floor, in place.

    Issue #1 fix: below the floor, upstream models (doubao etc.) can truncate a
    tool_use stream mid-JSON -- ``content_block_start`` carries ``input={}`` and
    the real arguments only arrive via ``partial_json`` deltas, so a truncated
    stream leaves the shadow loop with an empty/partial input and a silent
    error-retry loop. Clamping guarantees adequate budget for tool-calls
    regardless of the configured upstream.
    """
    floor = _min_max_tokens()
    mt = body.get("max_tokens")
    if not isinstance(mt, int) or mt < floor:
        body["max_tokens"] = floor


def _context_dir() -> str:
    """Root directory for AST scan / local tool execution."""
    return os.environ.get("CSMART_CONTEXT_DIR", ".")


# S-1 header whitelist: only allowlisted headers are forwarded upstream.
# ``x-api-key`` deliberately stays in the default allowlist (deviation from the
# original plan, which would have stripped it): the Anthropic SDK can send auth
# either as ``Authorization: Bearer`` (``ANTHROPIC_AUTH_TOKEN``) or as
# ``x-api-key`` (``ANTHROPIC_API_KEY``), and the proxy has no token-injection
# mechanism, so it forwards whichever the client sends. Live-verified
# 2026-08-28: the ``ark.talaga.my.id`` gateway REQUIRES ``authorization`` and
# rejects ``x-api-key`` (401), so Claude Code must set ``ANTHROPIC_AUTH_TOKEN``
# (Bearer), not ``ANTHROPIC_API_KEY``. The real hardening win is stripping
# ``cookie``, ``user-agent``, ``sec-*``, ``referer``, ``origin`` and every other
# non-allowlisted header (including the internal ``x-csmart-session``, which
# stays local). An operator can drop ``x-api-key`` via
# ``CSMART_HEADER_ALLOWLIST`` if their gateway accepts only ``authorization``.
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


# P-5 request body cap: reject oversized bodies before routing/forwarding.
_DEFAULT_MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MiB


def _max_body_bytes() -> int:
    try:
        return int(os.environ.get("CSMART_MAX_BODY_BYTES", str(_DEFAULT_MAX_BODY_BYTES)))
    except ValueError:
        return _DEFAULT_MAX_BODY_BYTES


class BodyTooLargeError(Exception):
    """Raised when a request body exceeds the configured byte cap."""


async def _read_body_bounded(request: Request) -> bytes:
    """Read the request body, aborting early once the configured cap is exceeded.

    Uses ``request.stream()`` so a chunked/oversized body is rejected as soon as
    the accumulated size passes the cap, without ever buffering the whole body
    (P-5 MAJOR: OOM/DoS guard). The middleware's cheap Content-Length pre-check
    still runs first for the declared-size fast path; this helper catches the
    chunked / no-Content-Length case.
    """
    cap = getattr(request.state, "csmart_max_body_bytes", None)
    if cap is None:
        cap = _max_body_bytes()
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:
            raise BodyTooLargeError(f"request body exceeds {cap} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def read_full_body(request: Request) -> Dict[str, Any]:
    """Read and parse the full JSON request body (size-bounded)."""
    body = await _read_body_bounded(request)
    return json.loads(body)


# ---------------------------------------------------------------------------
# Inbound helpers.
# ---------------------------------------------------------------------------


def extract_last_user_prompt(messages: List[Dict[str, Any]]) -> str:
    """Return the last user prompt as plain text.

    Handles both plain-string content and list-of-blocks content (joins the
    ``text`` blocks). Used for routing only — injection keeps its own,
    string-only behavior.
    """
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    return ""


def inject_context_to_messages(
    messages: List[Dict[str, Any]],
    selected_files: List[str],
    base_dir: str = ".",
) -> List[Dict[str, Any]]:
    """Inject pre-loaded file context into the last user message.

    Path-safety (F-09): every path in ``selected_files`` is validated through
    :func:`router.safe_path.resolve_under_base` before being read. Paths that
    escape the base dir (``..``, absolute-outside, symlink-outside) or that do
    not exist are skipped with a warning; only files resolving inside
    *base_dir* are read.
    """
    if not selected_files:
        return messages

    context_blocks: List[str] = []
    for file_path in selected_files:
        try:
            resolved = resolve_under_base(file_path, base_dir)
        except PathTraversalError:
            _stdlib_logger.warning(
                "skipping path traversal attempt in selected file: %r", file_path
            )
            continue
        if not resolved.is_file():
            _stdlib_logger.warning(
                "skipping selected file (missing or not a regular file): %r", file_path
            )
            continue
        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as exc:
            _stdlib_logger.warning(
                "skipping unreadable selected file %r: %s", file_path, exc
            )
            continue
        context_blocks.append(
            f"--- FILE START: {file_path} ---\n{content}\n--- FILE END ---\n"
        )

    if not context_blocks:
        return messages

    injected_context = "\n".join([
        "[PRE-LOADED CONTEXT - The following files contain the relevant source code you need to modify. DO NOT run grep/find/ls tool calls because the full content is already below.]\n\n",
        *context_blocks,
        "\nNow complete the user request above using this pre-loaded context. Modify the files directly.\n",
    ])

    new_messages = messages.copy()
    for i in reversed(range(len(new_messages))):
        if new_messages[i]["role"] == "user":
            original_content = new_messages[i]["content"]
            if isinstance(original_content, str):
                new_content = f"{original_content}\n\n{injected_context}"
                new_messages[i]["content"] = new_content
            break

    return new_messages


# Top-level import statement matcher (column-0 only, so function-local imports
# are never considered). Covers the four shapes that matter for the FIX #3
# import expansion: ``import X``, ``from X import ...``, ``from . import x``,
# ``from .x import ...``. Multiline parenthesized from-imports are only
# partially resolved (their first line); that is acceptable — the helper is a
# safety net that appends modules triage missed, never a full dependency graph.
_IMPORT_STMT_RE = re.compile(
    r"^(?:import\s+(?P<imp>[^#\n]+?)"
    r"|from\s+(?P<from_mod>[.\w]+)\s+import\s+(?P<names>[^#\n]+?))"
    r"(?:\s*#.*)?\s*$",
    re.MULTILINE,
)


def _module_candidates(mod: str, root_dir: str) -> List[str]:
    """Map a dotted module name to absolute candidate paths (may not exist).

    ``mod`` is resolved relative to ``root_dir`` — the repo root for absolute
    imports, the current file's package directory for relative imports: ``a.b``
    becomes ``<root>/a/b.py`` and, for package imports, ``<root>/a/b/__init__.py``.
    Callers must validate existence and path-safety themselves.
    """
    base = os.path.abspath(root_dir)
    rel = mod.replace(".", os.sep)
    return [os.path.join(base, f"{rel}.py"), os.path.join(base, rel, "__init__.py")]


def _split_import_names(names: str) -> List[str]:
    """Split a ``from ... import <names>`` clause into module names.

    Each comma-separated item keeps only its first token so ``x as y`` (and any
    ``x`` with a whitespace alias) still resolves to module ``x``.
    """
    out: List[str] = []
    for item in names.split(","):
        token = item.strip().split()[0] if item.strip() else ""
        if token and token != "*":
            out.append(token)
    return out


def _import_candidates(
    source: str, package_dir: str, base_dir: str
) -> List[str]:
    """Collect local module paths imported at the top level of *source*.

    Absolute imports (``import X`` / ``from X import ...``) resolve against the
    repository root ``base_dir`` (``a.b`` -> ``<base>/a/b.py``); relative
    imports (``from . import x`` / ``from .x import ...``) resolve against the
    current file's package directory ``package_dir``. Returns absolute
    candidate paths (they may not exist on disk — callers filter via
    :func:`router.safe_path.resolve_under_base`).
    """
    out: List[str] = []
    for match in _IMPORT_STMT_RE.finditer(source):
        if match.group("imp"):
            # ``import X`` / ``import X, Y`` / ``import a.b as c``.
            for item in _split_import_names(match.group("imp")):
                out.extend(_module_candidates(item, base_dir))
            continue
        from_mod = match.group("from_mod")
        if from_mod.startswith("."):
            # Relative import: each leading dot walks one package level up from
            # the current file's directory. ``from .x import y`` resolves
            # against package_dir; ``from ..x import y`` against its parent.
            dot_count = len(from_mod) - len(from_mod.lstrip("."))
            base_for_rel = package_dir
            for _ in range(dot_count - 1):
                base_for_rel = os.path.dirname(base_for_rel)
            rel = from_mod.lstrip(".")
            if rel:
                out.extend(_module_candidates(rel, base_for_rel))
            else:
                for name in _split_import_names(match.group("names")):
                    out.extend(_module_candidates(name, base_for_rel))
        else:
            # ``from X import ...`` -> the module to load is ``X``.
            out.extend(_module_candidates(from_mod, base_dir))
    return out


def _sum_selected_bytes(relpaths: List[str], base_dir: str = ".") -> int:
    """Total on-disk bytes of *relpaths* under *base_dir*; missing files count 0.

    Mirrors gate.py's size accounting (1 token ≈ 4 bytes) so budget re-caps and
    report fields stay consistent. Symlink-aware like the rest of the pipeline:
    the base is realpath-resolved so relative paths never leak ``../``.
    """
    base = os.path.realpath(base_dir)
    total = 0
    for rel in relpaths:
        try:
            resolved = resolve_under_base(rel, base)
        except PathTraversalError:
            continue
        if resolved.is_file():
            try:
                total += resolved.stat().st_size
            except OSError:
                pass
    return total


def _expand_selected_with_imports(
    selected_files: List[str],
    base_dir: str = ".",
    budget_tokens: int | None = None,
) -> List[str]:
    """Append top-level-imported local modules to the triage-selected files.

    FIX #3 (A/B S2): triage selects only e.g. ``router/dispatcher.py`` and
    misses ``router/routing_cache.py`` (imported at dispatcher.py module level),
    so the model completes the task without knowing the imported file exists.
    This helper scans each selected ``.py`` file for TOP-LEVEL imports
    (``import X``, ``from X import ...``, ``from . import x``, ``from .x import
    ...``), maps each module name to a local path under *base_dir* (dots →
    slashes + ``.py``, also checking ``<pkg>/__init__.py``), validates it via
    :func:`router.safe_path.resolve_under_base`, and appends existing,
    non-duplicate paths. Order: selected files first, then discovered imports,
    de-duplicated, first-seen order preserved. The path-safety contract of
    :func:`inject_context_to_messages` is unchanged — it still validates every
    path it receives.

    ``budget_tokens`` re-caps the appended imports (gate.py convention: 1 token
    ≈ 4 bytes) because FIX #3 runs AFTER ``apply_gate``: without the cap,
    discovered imports could push the final injection over the budget the gate
    already enforced on the selected files. When omitted (or <= 0) no cap is
    applied. The base is realpath-resolved so ``os.path.relpath`` against
    symlink-rooted base directories stays inside the repo (no ``../`` leaks,
    matching ``_rel_to_base`` in tool_shadow.py).
    """
    base = os.path.realpath(base_dir)
    ordered: List[str] = []
    seen: set[str] = set()

    for rel in selected_files:
        if rel in seen:
            continue
        seen.add(rel)
        ordered.append(rel)

    budget_bytes: int | None = None
    if budget_tokens is not None and budget_tokens > 0:
        budget_bytes = budget_tokens * 4
    total_bytes = (
        _sum_selected_bytes(ordered, base_dir=base) if budget_bytes is not None else 0
    )

    for rel in selected_files:
        try:
            resolved = resolve_under_base(rel, base)
        except PathTraversalError:
            continue
        if not resolved.is_file() or resolved.suffix != ".py":
            continue
        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError:
            continue
        for cand in _import_candidates(source, str(resolved.parent), base):
            try:
                candidate = resolve_under_base(cand, base)
            except PathTraversalError:
                continue
            if not candidate.is_file():
                continue
            # Express the discovered file as a repo-relative path (matching the
            # triage-selected style), then append.
            relpath = os.path.relpath(candidate, base).replace(os.sep, "/")
            if relpath in seen:
                continue
            if budget_bytes is not None:
                try:
                    size = candidate.stat().st_size
                except OSError:
                    size = 0
                if total_bytes + size > budget_bytes:
                    continue  # import doesn't fit the token budget — drop it
                total_bytes += size
            seen.add(relpath)
            ordered.append(relpath)

    return ordered


async def _get_or_scan_ast(context_dir: str) -> List[str]:
    """Scan the project once per context_dir (cached). Non-blocking (P-2)."""
    key = os.path.abspath(context_dir)
    with _AST_CACHE_LOCK:
        cached = _AST_CACHE.get(key)
    if cached is not None:
        return cached
    skeletons = await asyncio.to_thread(
        ast_extractor.scan_project_codebase, context_dir, DEFAULT_IGNORE_DIRS
    )
    with _AST_CACHE_LOCK:
        _AST_CACHE[key] = skeletons
    return skeletons


def _truncate_routing_prompt(prompt: str, max_chars: int | None = None) -> str:
    """Keep the TAIL of a routing prompt so cold prefill stays small (P-2).

    The current task statement sits at the end of the conversation prompt; the
    head is history that Qwen does not need for file scoring. ``max_chars``
    defaults to ``CSMART_ROUTING_PROMPT_MAX_CHARS`` (else 4000).
    """
    if max_chars is None:
        try:
            max_chars = int(os.environ.get("CSMART_ROUTING_PROMPT_MAX_CHARS", "4000"))
        except ValueError:
            max_chars = 4000
    if len(prompt) <= max_chars:
        return prompt
    return prompt[-max_chars:]


def _cap_skeleton(full_skeleton: str, max_chars: int | None = None) -> str:
    """Cap the AST skeleton sent to Ollama while keeping every file header.

    Lines starting with ``// `` are file headers (never removed); lines
    starting with ``- `` are signatures. When over budget the longest signature
    lines are dropped (trimming each file block's tail) so Qwen still sees all
    files exist with a smaller prefill. ``max_chars`` defaults to
    ``CSMART_ROUTING_SKELETON_MAX_CHARS`` (else 6000). Only the joined string is
    capped — the ``_AST_CACHE`` entries are left untouched.
    """
    if max_chars is None:
        try:
            max_chars = int(os.environ.get("CSMART_ROUTING_SKELETON_MAX_CHARS", "6000"))
        except ValueError:
            max_chars = 6000
    if len(full_skeleton) <= max_chars:
        return full_skeleton

    lines = full_skeleton.splitlines()
    while len("\n".join(lines)) > max_chars:
        longest_idx = -1
        longest_len = -1
        for i, line in enumerate(lines):
            if line.startswith("- ") and len(line) > longest_len:
                longest_len = len(line)
                longest_idx = i
        if longest_idx < 0:
            break  # no signature lines left; only // headers remain
        del lines[longest_idx]

    # Path-only skeleton still over budget (not expected at 6000): keep the
    # first N headers that fit.
    if len("\n".join(lines)) > max_chars:
        kept: List[str] = []
        for line in lines:
            if line.startswith("// "):
                if len("\n".join(kept + [line])) <= max_chars:
                    kept.append(line)
        lines = kept

    return "\n".join(lines)


async def run_local_routing(
    prompt: str,
    session_key: str | None = None,
    context_dir: str = ".",
    trace_id: str | None = None,
) -> GateResult:
    """Run local routing: AST scan (cached) -> Ollama scoring -> gate.

    Async and non-blocking (P-2): both the AST scan and the Ollama call run in
    worker threads. Routing is cached per session (P-1): the first
    ``/v1/messages`` for a ``x-csmart-session`` routes via Ollama; later
    same-session requests reuse the result. Session-less requests (production)
    reuse the routing via the context-dir TTL cache (P-0) instead of re-routing
    every message (AST is still cached either way).
    """
    skeletons = await _get_or_scan_ast(context_dir)
    logger.log(
        AST_SCANNED,
        trace_id=trace_id,
        context_dir=context_dir,
        scanned_files_count=len(skeletons),
    )
    full_skeleton = _cap_skeleton("\n".join(skeletons))

    t0 = time.monotonic()
    cache_hit = False
    if session_key:
        routing = _ROUTING_CACHE.get(session_key)  # recency bump inside class
        if routing is None:
            routing = await asyncio.to_thread(
                ollama_scorer.route_target_files, full_skeleton, prompt
            )
            _ROUTING_CACHE.put(session_key, routing)
    else:
        # FIX #2: key the session-less TTL cache by (context_dir, prompt) so a
        # different prompt on the same repo never reuses a stale triage (A/B S2
        # got a 0ms cache HIT with a wrong injection for the second prompt).
        ttl_key = (
            f"{context_dir}|"
            f"{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:16]}"
        )
        routing = _ROUTING_TTL_CACHE.get(ttl_key)  # stale entries evicted
        if routing is None:
            routing = await asyncio.to_thread(
                ollama_scorer.route_target_files, full_skeleton, prompt
            )
            _ROUTING_TTL_CACHE.put(ttl_key, routing)
        else:
            cache_hit = True
    routing_ms = int((time.monotonic() - t0) * 1000)

    # apply_gate takes tokens (it converts to bytes internally); the old `* 4`
    # passed bytes-as-tokens, making the budget 4x too lenient (review MAJOR).
    gate_result = await asyncio.to_thread(
        apply_gate,
        routing,
        CONFIDENCE_THRESHOLD,
        DEFAULT_BUDGET_TOKENS,
        base_dir=context_dir,
    )
    logger.log(
        OLLAMA_TRIAGE,
        trace_id=trace_id,
        session=session_key,
        selected_files=gate_result.selected_files,
        confidence=routing.confidence,
        duration_ms=routing_ms,
        cache_hit=cache_hit,
    )
    return gate_result


# ---------------------------------------------------------------------------
# Upstream client + retry (P-3).
# ---------------------------------------------------------------------------


async def _request_upstream(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_body: Dict[str, Any],
) -> Tuple[httpx.AsyncClient, httpx.Response]:
    """Send a request to upstream with bounded retry; return (client, resp).

    The client is intentionally NOT closed here: the caller streams the
    response and is responsible for closing both. Retries only happen on
    connect/read/timeout transport errors. On terminal failure raises
    :class:`UpstreamError`.
    """
    timeout = _upstream_timeout()
    attempts = 0
    while True:
        client = httpx.AsyncClient(timeout=timeout, transport=_UPSTREAM_TRANSPORT)
        try:
            req = client.build_request(method, url, headers=headers, json=json_body)
            resp = await client.send(req, stream=True)
            return client, resp
        except httpx.TransportError as exc:
            await client.aclose()
            attempts += 1
            if attempts > MAX_UPSTREAM_RETRIES:
                raise UpstreamError(
                    f"upstream request failed after {attempts} attempts: {exc}"
                ) from exc
            await asyncio.sleep(0.25 * attempts)


# ---------------------------------------------------------------------------
# SSE parsing (N-3).
# ---------------------------------------------------------------------------


def _parse_sse_data(data_lines: List[str]) -> Dict[str, Any]:
    """Join ``data:`` lines and JSON-decode them into a payload dict."""
    raw = "\n".join(data_lines)
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
        return {
            "type": "error",
            "error": {"type": "invalid_payload", "message": raw[:200]},
        }
    except json.JSONDecodeError:
        return {
            "type": "error",
            "error": {"type": "invalid_json", "message": raw[:200]},
        }


async def _iter_sse_events(resp: httpx.Response) -> AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None]:
    """Parse an httpx streaming response into ``(event_name, payload)`` tuples."""
    data_lines: List[str] = []
    event_name: Optional[str] = None
    async for raw_line in resp.aiter_lines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                yield event_name, _parse_sse_data(data_lines)
                data_lines = []
                event_name = None
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if data_lines:
        yield event_name, _parse_sse_data(data_lines)


# ---------------------------------------------------------------------------
# Shadow loop (N-4 / QG-03 / QG-04).
# ---------------------------------------------------------------------------


class _ShadowStreamer:
    """Drives the outbound SSE stream with exploration tool-use shadowing.

    For each internal upstream round it forwards text deltas and non-exploration
    tool_use to the client immediately (QG-04), holds exploration tool_use up to
    ``MAX_SHADOW_ROUNDS`` per request (QG-03), executes them locally, then
    re-submits the ``tool_result`` blocks upstream and continues with the new
    round. When no more exploration tool_use is held, the round's closing SSE
    events are flushed and the stream completes.
    """

    def __init__(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        session_key: Optional[str],
        context_dir: str = ".",
        trace_id: str | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        self.session_key = session_key
        self.context_dir = context_dir
        self.trace_id = trace_id or str(uuid4())
        self.round = 1
        self.shadow_used = 0
        self.client_index = 0
        self._pending_held: List[Dict[str, Any]] = []
        self._round_failed = False
        self._start_ts = time.monotonic()

    # -- public driver -------------------------------------------------

    async def run(self) -> AsyncGenerator[bytes, None]:
        """Yield SSE bytes to the client, looping internal shadow rounds."""
        try:
            while True:
                messages = self.body.get("messages", [])
                self._pending_held = []
                async for chunk in self._stream_round(messages):
                    yield chunk
                held = self._pending_held
                if not held:
                    break
                self.body = {
                    **self.body,
                    "messages": self._build_followup(messages, held),
                }
            logger.log(
                SSE_STREAM_COMPLETE,
                trace_id=self.trace_id,
                duration_ms=self._elapsed_ms(),
                # P-4: self.round is incremented at the END of each _stream_round,
                # so a single-round request reads 2 — log the actual upstream
                # call count.
                rounds=self.round - 1,
                shadow_used=self.shadow_used,
                status="error" if self._round_failed else "ok",
            )
        except UpstreamError as exc:
            payload = {
                "type": "error",
                "error": {"type": "api_error", "message": str(exc)},
            }
            yield self._format_event("error", payload)
            logger.log(
                SSE_STREAM_COMPLETE,
                trace_id=self.trace_id,
                status="error",
                error=str(exc),
            )
            return

    # -- per-round processing -------------------------------------------

    async def _stream_round(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[bytes, None]:
        """Stream one upstream round. Sets ``self._pending_held`` on exit."""
        try:
            client, resp = await _request_upstream(
                self.method, self.url, self.headers, {**self.body, "messages": messages}
            )
        except UpstreamError as exc:
            self._round_failed = True
            payload = {
                "type": "error",
                "error": {"type": "api_error", "message": str(exc)},
            }
            yield self._format_event("error", payload)
            return

        if resp.status_code >= 400:
            self._round_failed = True
            body_text = (await resp.aread()).decode("utf-8", errors="replace")
            await resp.aclose()
            await client.aclose()
            payload = {
                "type": "error",
                "error": {
                    "type": "upstream_error",
                    "message": f"upstream returned {resp.status_code}: {body_text[:200]}",
                },
            }
            yield self._format_event("error", payload)
            return

        held_indices: set[int] = set()
        held_by_index: Dict[int, Dict[str, Any]] = {}
        client_index_map: Dict[int, int] = {}
        buffered_end: List[Tuple[Optional[str], Dict[str, Any]]] = []
        round_had_held = False

        try:
            async for event_name, payload in _iter_sse_events(resp):
                etype = payload.get("type", "")

                if etype == "message_start":
                    if self.round == 1:
                        yield self._format_event(event_name, payload)
                    continue

                if etype in ("message_delta", "message_stop"):
                    buffered_end.append((event_name, payload))
                    continue

                if etype == "content_block_start":
                    index = payload.get("index")
                    if not isinstance(index, int):
                        yield self._format_event(event_name, payload)
                        continue
                    cb = payload.get("content_block", {})
                    is_tool_use = cb.get("type") == "tool_use"
                    name = cb.get("name", "")
                    if (
                        isinstance(index, int)
                        and is_tool_use
                        and name in TOOL_NAMES
                        and self.shadow_used < MAX_SHADOW_ROUNDS
                    ):
                        self.shadow_used += 1
                        round_had_held = True
                        held_indices.add(index)
                        base_input = cb.get("input")
                        held_by_index[index] = {
                            "index": index,
                            "id": cb.get("id"),
                            "name": name,
                            "input_parts": (
                                [json.dumps(base_input)] if isinstance(base_input, dict) and base_input else []
                            ),
                        }
                        logger.log(
                            TOOL_SHADOW_INTERCEPT,
                            trace_id=self.trace_id,
                            tool_name=name,
                            action_taken="hold",
                        )
                        continue
                    new_index = self.client_index
                    self.client_index += 1
                    client_index_map[index] = new_index
                    payload = dict(payload)
                    payload["index"] = new_index
                    yield self._format_event(event_name, payload)
                    continue

                if etype == "content_block_delta":
                    index = payload.get("index")
                    if not isinstance(index, int):
                        yield self._format_event(event_name, payload)
                        continue
                    if index in held_indices:
                        delta = payload.get("delta", {})
                        partial = delta.get("partial_json", "") if isinstance(delta, dict) else ""
                        if isinstance(partial, str):
                            held_by_index[index]["input_parts"].append(partial)
                        continue
                    new_index = client_index_map.get(index)
                    if new_index is None:
                        continue
                    payload = dict(payload)
                    payload["index"] = new_index
                    yield self._format_event(event_name, payload)
                    continue

                if etype == "content_block_stop":
                    index = payload.get("index")
                    if not isinstance(index, int):
                        yield self._format_event(event_name, payload)
                        continue
                    if index in held_indices:
                        continue
                    new_index = client_index_map.get(index)
                    if new_index is None:
                        continue
                    payload = dict(payload)
                    payload["index"] = new_index
                    yield self._format_event(event_name, payload)
                    continue

                if etype == "ping":
                    yield self._format_event(event_name, payload)
                    continue

                if etype == "error":
                    # Upstream sent an SSE error; forward and stop the round.
                    self._round_failed = True
                    yield self._format_event(event_name, payload)
                    return

                # Unknown event type: forward untouched.
                yield self._format_event(event_name, payload)
        except httpx.TransportError as exc:
            # Mid-stream transport failure (connection reset, read error): emit
            # a graceful SSE error instead of a truncated client stream (P-3
            # review MAJOR). Marked failed so run() logs status="error".
            self._round_failed = True
            payload = {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"stream interrupted: {exc}",
                },
            }
            yield self._format_event("error", payload)
            return
        finally:
            await resp.aclose()
            await client.aclose()

        self.round += 1

        if held_indices:
            self._pending_held = await self._execute_held(
                [held_by_index[i] for i in sorted(held_indices)]
            )
            return

        # No held blocks this round -> flush the closing SSE events.
        for event_name, payload in buffered_end:
            yield self._format_event(event_name, payload)

    # -- helpers ---------------------------------------------------------

    async def _execute_held(
        self, held_blocks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute each held exploration tool locally (parallel) and summarize.

        Defensive (issue #1): ``content_block_start`` from upstream models
        (doubao/glm/deepseek) always carries ``input={}`` and the real
        arguments arrive only via ``partial_json`` deltas. When those deltas
        are missing or truncated (empty input, or JSON that never parses), the
        block is NOT executed -- instead we log the condition explicitly and
        return an actionable ``tool_result`` so the model can re-issue with
        explicit arguments instead of silently re-feeding a bare "no path
        provided" error into a retry loop.
        """

        async def _exec(block: Dict[str, Any]) -> Dict[str, Any]:
            tool_input = self._join_input(block["input_parts"])
            if not tool_input:
                logger.log(
                    TOOL_SHADOW_INTERCEPT,
                    trace_id=self.trace_id,
                    tool_name=block["name"],
                    action_taken="empty_input",
                )
                return {
                    **block,
                    "input": {},
                    "content": (
                        f"ERROR: tool {block['name']!r} received an empty input "
                        f"(no arguments streamed). Re-issue the call with explicit "
                        f"arguments (e.g. file_path/path/pattern)."
                    ),
                }
            if "_partial_json" in tool_input:
                logger.log(
                    TOOL_SHADOW_INTERCEPT,
                    trace_id=self.trace_id,
                    tool_name=block["name"],
                    action_taken="truncated_input",
                )
                return {
                    **block,
                    "input": {},
                    "content": (
                        f"ERROR: tool {block['name']!r} input was truncated "
                        f"mid-stream (incomplete JSON). Re-issue the call with "
                        f"explicit arguments."
                    ),
                }
            raw = await execute_local_tool(block["name"], tool_input, self.context_dir)
            logger.log(
                TOOL_LOCAL_EXEC,
                trace_id=self.trace_id,
                tool_name=block["name"],
                chars=len(raw),
            )
            summarized = await summarize_exploration(block["name"], raw)
            return {**block, "input": tool_input, "content": summarized}

        return await asyncio.gather(*[_exec(b) for b in held_blocks])

    @staticmethod
    def _join_input(parts: List[str]) -> Dict[str, Any]:
        """Reassemble ``partial_json`` fragments into a tool input dict."""
        raw = "".join(parts)
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"_partial_json": raw}

    def _build_followup(
        self, messages: List[Dict[str, Any]], held: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Append the assistant tool_use + user tool_result turns."""
        assistant_content: List[Dict[str, Any]] = []
        user_results: List[Dict[str, Any]] = []
        for block in held:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "input": block.get("input", {}),
                }
            )
            user_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": block.get("content", ""),
                }
            )
        followup = list(messages)
        if assistant_content:
            followup.append({"role": "assistant", "content": assistant_content})
        followup.append({"role": "user", "content": user_results})
        return followup

    @staticmethod
    def _format_event(event_name: Optional[str], payload: Dict[str, Any]) -> bytes:
        etype = str(payload.get("type") or event_name or "message")
        return f"event: {etype}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start_ts) * 1000)


# ---------------------------------------------------------------------------
# S-2 loopback enforcement + per-IP token-bucket rate limit.
# ---------------------------------------------------------------------------

def _is_loopback(host: str | None) -> bool:
    """True if ``host`` is a loopback IP (``127.0.0.0/8``, ``::1``, IPv4-mapped).

    Uses ``ipaddress`` so it also covers ``127.0.0.2-255``, ``::ffff:127.0.0.1``
    and the hex form ``::ffff:7f00:1`` — not just the literal ``127.0.0.1``.
    Returns False for a None host or a non-IP string (e.g. ``localhost``).
    """
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _origin_loopback(origin: str | None) -> bool:
    """True if the ``Origin`` header's host is a loopback address.

    Used to gate CORS: only loopback-origin browsers get
    ``Access-Control-Allow-Origin``. Claude Code CLI is not a browser and sends
    no Origin, so this is defense-in-depth tightening of the loopback-only auth
    claim, not a feature that any current client relies on.
    """
    if not origin:
        return False
    scheme_sep = origin.find("://")
    rest = origin[scheme_sep + 3:] if scheme_sep != -1 else origin
    if "@" in rest:
        rest = rest.rsplit("@", 1)[1]
    host = rest.split("/", 1)[0]
    if host.startswith("["):  # IPv6 literal: "[::1]:3000" -> "::1"
        host = host[1:host.find("]")]
    else:
        host = host.rsplit(":", 1)[0]  # strip port from IPv4/hostname
    return _is_loopback(host)


def _allow_external() -> bool:
    return os.environ.get("CSMART_ALLOW_EXTERNAL") == "1"


# Per-IP token buckets: ip -> [tokens, last_refill_ts]. Bounded LRU so the map
# never grows unbounded under many distinct peer IPs.
_RATE_BUCKETS: "OrderedDict[str, list[float]]" = OrderedDict()
_RATE_BUCKETS_LOCK = threading.Lock()
_MAX_RATE_BUCKETS = 1000


def _rate_limit_per_min() -> float:
    try:
        return float(os.environ.get("CSMART_RATE_LIMIT_PER_MIN", "120"))
    except ValueError:
        return 120.0


def _consume_token(ip: str, now: float, cap: float | None = None) -> bool:
    """Try to consume one rate-limit token. Returns False -> caller must 429.

    ``cap`` may be passed in by the caller so the env is read at most once per
    request (NIT: ``_rate_limit_per_min()`` no longer re-read per call).
    """
    if cap is None:
        cap = _rate_limit_per_min()
    with _RATE_BUCKETS_LOCK:
        bucket = _RATE_BUCKETS.get(ip)
        if bucket is None:
            _RATE_BUCKETS[ip] = [cap - 1.0, now]
            _RATE_BUCKETS.move_to_end(ip)
            if len(_RATE_BUCKETS) > _MAX_RATE_BUCKETS:
                _RATE_BUCKETS.popitem(last=False)
            return True
        tokens, last = bucket
        elapsed = max(0.0, now - last)
        tokens = min(cap, tokens + elapsed * cap / 60.0)
        if tokens < 1.0:
            bucket[0], bucket[1] = tokens, now
            return False
        bucket[0], bucket[1] = tokens - 1.0, now
        _RATE_BUCKETS.move_to_end(ip)
        return True


# ---------------------------------------------------------------------------
# FastAPI app + routes (absorbed from proxy.py).
# ---------------------------------------------------------------------------

app = FastAPI(title="csmart local reverse proxy", version="1.0")


@app.middleware("http")
async def _security_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Enforce loopback-only access, per-IP rate limit, and the body cap.

    Order matters: loopback 403 first, then rate limit 429, then the cheap
    Content-Length pre-check 413, then pass through to the route handlers. A
    403/429/413 here never triggers routing or an upstream call.
    """
    peer = request.client.host if request.client else None
    is_loopback = _is_loopback(peer)

    if not _allow_external() and not is_loopback:
        return JSONResponse({"error": "loopback_only"}, status_code=403)

    # Loopback peers (Claude Code, editors, health checkers) share one local
    # bucket; charging them tokens causes spurious 429s on busy sessions, so
    # only non-loopback peers consume tokens.
    rate_cap = _rate_limit_per_min()
    if not is_loopback and not _consume_token(peer or "unknown", time.time(), rate_cap):
        return JSONResponse(
            {"error": "rate_limited"},
            status_code=429,
            headers={"Retry-After": "60"},
        )

    # Cheap Content-Length pre-check (P-5): reject oversized bodies for ALL
    # methods without reading the body. The chunked/no-content-length case is
    # caught later in ``_read_body_bounded``. The cap is stashed on the request
    # state so the route handler reuses it instead of re-reading the env.
    max_body = _max_body_bytes()
    request.state.csmart_max_body_bytes = max_body
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > max_body:
            return JSONResponse({"error": "request_too_large"}, status_code=413)

    return await call_next(request)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_handler(request: Request, path: str) -> Response:
    """Wildcard proxy handler — intercepts all requests and forwards."""

    # CORS preflight. Allow-origin is gated on the request's Origin host being
    # loopback: a bare ``*`` would weaken the loopback-only auth claim, and
    # Claude Code CLI is not a browser and needs no CORS.
    if request.method == "OPTIONS":
        headers: Dict[str, str] = {
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
        origin = request.headers.get("origin")
        if origin is not None and _origin_loopback(origin):
            headers["Access-Control-Allow-Origin"] = origin
        return Response(status_code=200, headers=headers)

    # /v1/messages is intercepted and context-injected.
    if "/messages" in path and request.method == "POST":
        return await handle_messages_request(request)

    # Everything else passes through untouched.
    return await passthrough_request(request, path)


async def handle_messages_request(request: Request) -> Response:
    """Intercept /v1/messages: route, inject context, forward with shadowing."""
    try:
        body = await read_full_body(request)
    except BodyTooLargeError:
        return JSONResponse({"error": "request_too_large"}, status_code=413)
    except json.JSONDecodeError as exc:
        return JSONResponse({"error": f"invalid json: {exc}"}, status_code=400)

    # Issue #1: clamp max_tokens to a floor so tool-calls aren't truncated
    # mid-stream (upstream models emit input={} + partial_json deltas).
    _clamp_max_tokens(body)

    trace_id = str(uuid4())
    logger.set_trace_id(trace_id)

    messages = body.get("messages", [])
    prompt = extract_last_user_prompt(messages)
    session_key = request.headers.get("x-csmart-session")
    logger.log(
        INBOUND_REQUEST,
        trace_id=trace_id,
        path=request.url.path,
        session=session_key,
        prompt_len=len(prompt),
    )

    context_dir = _context_dir()
    gate_result = await run_local_routing(
        _truncate_routing_prompt(prompt),
        session_key=session_key,
        context_dir=context_dir,
        trace_id=trace_id,
    )

    # FIX #3: triage can miss modules the selected files import at the top
    # level (A/B S2: dispatcher.py imports routing_cache.py, yet only
    # dispatcher.py was injected). Expand before injecting so the model sees
    # the imported file exists; appended imports are capped at the same token
    # budget apply_gate enforced (they run after it). inject's path-safety
    # contract is unchanged.
    selected_files = _expand_selected_with_imports(
        gate_result.selected_files,
        base_dir=context_dir,
        budget_tokens=DEFAULT_BUDGET_TOKENS,
    )
    if selected_files != gate_result.selected_files:
        # Keep the report's gate result describing what was actually injected
        # (imports appended / dropped by the budget re-cap), not the pre-expansion
        # set — otherwise selected_bytes / estimated_tokens would be stale.
        gate_result.selected_files = selected_files
        gate_result.selected_bytes = _sum_selected_bytes(
            selected_files, base_dir=context_dir
        )
        gate_result.estimated_tokens = gate_result.selected_bytes // 4
    modified_messages = inject_context_to_messages(
        messages, selected_files, base_dir=context_dir
    )
    body["messages"] = modified_messages

    return await forward_streaming_request(
        request, body, trace_id=trace_id, context_dir=context_dir
    )


async def forward_streaming_request(
    request: Request,
    body: Dict[str, Any],
    trace_id: str | None = None,
    context_dir: str = ".",
) -> Response:
    """Forward a streaming request to upstream and stream the SSE response back."""
    if trace_id is None:
        trace_id = str(uuid4())
        logger.set_trace_id(trace_id)

    upstream_path = request.url.path
    upstream_url = f"{UPSTREAM_BASE_URL}{upstream_path}"
    headers = _build_upstream_headers(request)
    session_key = request.headers.get("x-csmart-session")

    streamer = _ShadowStreamer(
        method="POST",
        url=upstream_url,
        headers=headers,
        body=body,
        session_key=session_key,
        context_dir=context_dir,
        trace_id=trace_id,
    )

    async def gen() -> AsyncGenerator[bytes, None]:
        async for chunk in streamer.run():
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def passthrough_request(request: Request, path: str) -> Response:
    """Passthrough request untouched to upstream (buffered).

    Non-``/v1/messages`` endpoints return small JSON bodies, so the upstream
    response is buffered and returned as a plain :class:`Response`. This also
    keeps ``httpx.MockTransport``-based tests hermetic (MockTransport marks a
    ``stream=True`` response as already consumed, which breaks ``aiter_raw``).
    """
    upstream_url = f"{UPSTREAM_BASE_URL}/{path}"
    query_params = dict(request.query_params)

    body: Optional[bytes] = None
    if request.method not in ("GET", "HEAD"):
        try:
            body = await _read_body_bounded(request)
        except BodyTooLargeError:
            return JSONResponse({"error": "request_too_large"}, status_code=413)

    headers = _build_upstream_headers(request)
    timeout = _upstream_timeout()

    try:
        async with httpx.AsyncClient(timeout=timeout, transport=_UPSTREAM_TRANSPORT) as client:
            req = client.build_request(
                method=request.method,
                url=upstream_url,
                params=query_params,
                headers=headers,
                content=body,
            )
            resp = await client.send(req)
            content = resp.content
            status = resp.status_code
            resp_headers = {
                k: v for k, v in resp.headers.items() if k.lower() != "content-length"
            }
            media_type = resp.headers.get("content-type")
    except Exception as exc:  # noqa: BLE001 - surface as 502
        return Response(f"Upstream error: {exc}", status_code=502)

    return Response(
        content=content,
        status_code=status,
        headers=resp_headers,
        media_type=media_type,
    )


# ---------------------------------------------------------------------------
# Health checks (absorbed from proxy.py).
# ---------------------------------------------------------------------------


async def check_upstream_health() -> bool:
    """Check if the upstream gateway is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0, transport=_UPSTREAM_TRANSPORT) as client:
            resp = await client.get(f"{UPSTREAM_BASE_URL}/v1/models")
            return resp.status_code < 500
    except Exception:
        return False


def check_ollama_health() -> bool:
    """Check if Ollama is running and the model is available."""
    import ollama

    try:
        ollama.show(triage_model())
        return True
    except Exception:
        return False
