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
import ipaddress
import json
import logging
import os
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
_ROUTING_CACHE: OrderedDict[str, RoutingResult] = OrderedDict()
_ROUTING_CACHE_LOCK = threading.Lock()
# LRU cap (P-1 review MAJOR): past sessions are cheap to re-route via Ollama,
# so the cache never grows unbounded.
_MAX_ROUTING_CACHE_ENTRIES = 128


class UpstreamError(Exception):
    """Raised when the upstream gateway is unreachable after retries."""


def _upstream_timeout() -> float:
    try:
        return float(os.environ.get("CSMART_UPSTREAM_TIMEOUT", "60"))
    except ValueError:
        return 60.0


def _context_dir() -> str:
    """Root directory for AST scan / local tool execution."""
    return os.environ.get("CSMART_CONTEXT_DIR", ".")


# S-1 header whitelist: only allowlisted headers are forwarded upstream.
# ``x-api-key`` deliberately stays in the default allowlist (deviation from the
# original plan, which would have stripped it): Claude Code's Anthropic SDK
# authenticates to the gateway via ``x-api-key`` by default and the proxy has no
# token-injection mechanism, so it forwards the client's x-api-key as-is. The
# real hardening win is stripping ``cookie``, ``user-agent``, ``sec-*``,
# ``referer``, ``origin`` and every other non-allowlisted header (including the
# internal ``x-csmart-session``, which stays local). An operator can drop
# ``x-api-key`` via ``CSMART_HEADER_ALLOWLIST`` if their gateway accepts
# ``authorization`` instead.
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
    same-session requests reuse the result. No session header -> route every
    request (AST still cached).
    """
    skeletons = await _get_or_scan_ast(context_dir)
    logger.log(
        AST_SCANNED,
        trace_id=trace_id,
        context_dir=context_dir,
        scanned_files_count=len(skeletons),
    )
    full_skeleton = "\n".join(skeletons)

    t0 = time.monotonic()
    if session_key:
        with _ROUTING_CACHE_LOCK:
            routing = _ROUTING_CACHE.get(session_key)
            if routing is not None:
                _ROUTING_CACHE.move_to_end(session_key)  # LRU recency bump
        if routing is None:
            routing = await asyncio.to_thread(
                ollama_scorer.route_target_files, full_skeleton, prompt
            )
            with _ROUTING_CACHE_LOCK:
                _ROUTING_CACHE[session_key] = routing
                _ROUTING_CACHE.move_to_end(session_key)
                if len(_ROUTING_CACHE) > _MAX_ROUTING_CACHE_ENTRIES:
                    _ROUTING_CACHE.popitem(last=False)  # evict oldest
    else:
        routing = await asyncio.to_thread(
            ollama_scorer.route_target_files, full_skeleton, prompt
        )
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
                rounds=self.round,
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
        """Execute each held exploration tool locally (parallel) and summarize."""

        async def _exec(block: Dict[str, Any]) -> Dict[str, Any]:
            tool_input = self._join_input(block["input_parts"])
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
        prompt,
        session_key=session_key,
        context_dir=context_dir,
        trace_id=trace_id,
    )

    modified_messages = inject_context_to_messages(
        messages, gate_result.selected_files, base_dir=context_dir
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
