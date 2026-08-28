"""Hermetic server tests for the csmart proxy engine (``router.dispatcher``).

Drives the FastAPI app with ``httpx.ASGITransport`` and replaces the upstream
gateway with ``httpx.MockTransport`` serving canned SSE responses. AST scanning
and Ollama routing are patched to hermetic fixtures. No live Ollama and no live
upstream: the whole module runs under ``pytest -m "not live"``.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Union

import httpx
import pytest
from fastapi import Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.dispatcher import app, inject_context_to_messages
from router.ollama_scorer import RoutingResult
import router.dispatcher as dispatcher


def _run(coro):
    """Run a coroutine to completion with a fresh event loop."""
    return asyncio.run(coro)


def _asgi_request(req: httpx.Request, *, client=("127.0.0.1", 123)) -> Request:
    """Convert an httpx.Request into a Starlette Request (scope + receive).

    Used for direct unit tests of helpers that take a ``Request`` (header
    whitelist, body cap) without going through the ASGI app.
    """
    scope: Dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": req.method,
        "scheme": req.url.scheme,
        "path": req.url.path,
        "raw_path": req.url.path.encode("ascii"),
        "query_string": req.url.query if isinstance(req.url.query, bytes) else req.url.query.encode("ascii"),
        "root_path": "",
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in req.headers.items()
        ],
        "client": client,
        "server": ("test", 80),
    }
    body = req.content

    async def receive() -> Dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive=receive)


# ---------------------------------------------------------------------------
# SSE fixtures (canned upstream payloads).
# ---------------------------------------------------------------------------


def _sse_text(text: str) -> str:
    return "\n".join([
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"msg_1","role":"assistant","content":[],"model":"mock"}}',
        "",
        "event: content_block_start",
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        "",
        "event: content_block_delta",
        f'data: {{"type":"content_block_delta","index":0,"delta":{{"type":"text_delta","text":"{text}"}}}}',
        "",
        "event: content_block_stop",
        'data: {"type":"content_block_stop","index":0}',
        "",
        "event: message_delta",
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":10}}',
        "",
        "event: message_stop",
        'data: {"type":"message_stop"}',
        "",
    ])


def _sse_tool_use(index: int, name: str, tool_id: str, partial_json: str) -> str:
    """A single content-block SSE fragment (no message envelope)."""
    return "\n".join([
        "event: content_block_start",
        f'data: {{"type":"content_block_start","index":{index},"content_block":{{"type":"tool_use","id":"{tool_id}","name":"{name}","input":{{}}}}}}',
        "",
        "event: content_block_delta",
        f'data: {{"type":"content_block_delta","index":{index},"delta":{{"type":"input_json_delta","partial_json":"{partial_json}"}}}}',
        "",
        "event: content_block_stop",
        f'data: {{"type":"content_block_stop","index":{index}}}',
        "",
    ])


def _sse_tool_use_round(name: str, tool_id: str, partial_json: str) -> str:
    """A full round: message envelope + one tool_use block."""
    return "\n".join([
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"msg_r1","role":"assistant","content":[],"model":"mock"}}',
        "",
        *_sse_tool_use(0, name, tool_id, partial_json).splitlines(),
        "",
        "event: message_delta",
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":3}}',
        "",
        "event: message_stop",
        'data: {"type":"message_stop"}',
        "",
    ])


def _sse_tool_use_empty_input(index: int, name: str, tool_id: str) -> str:
    """A tool_use block that streams NO input_json deltas (input stays {})."""
    return "\n".join([
        "event: content_block_start",
        f'data: {{"type":"content_block_start","index":{index},"content_block":{{"type":"tool_use","id":"{tool_id}","name":"{name}","input":{{}}}}}}',
        "",
        "event: content_block_stop",
        f'data: {{"type":"content_block_stop","index":{index}}}',
        "",
    ])


def _sse_tool_use_empty_round(name: str, tool_id: str) -> str:
    """A full round: message envelope + one tool_use block with empty input."""
    return "\n".join([
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"msg_empty","role":"assistant","content":[],"model":"mock"}}',
        "",
        *_sse_tool_use_empty_input(0, name, tool_id).splitlines(),
        "",
        "event: message_delta",
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":3}}',
        "",
        "event: message_stop",
        'data: {"type":"message_stop"}',
        "",
    ])


def _sse_n_tool_uses(count: int) -> str:
    """A full round with ``count`` consecutive GrepTool tool_use blocks."""
    lines = [
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"msg_m","role":"assistant","content":[],"model":"mock"}}',
        "",
    ]
    for i in range(count):
        partial = '{"pattern": "zzz_no_match_%d"}' % i
        partial_escaped = partial.replace('"', '\\"')
        lines += [
            "event: content_block_start",
            f'data: {{"type":"content_block_start","index":{i},"content_block":{{"type":"tool_use","id":"tu_{i}","name":"GrepTool","input":{{}}}}}}',
            "",
            "event: content_block_delta",
            f'data: {{"type":"content_block_delta","index":{i},"delta":{{"type":"input_json_delta","partial_json":"{partial_escaped}"}}}}',
            "",
            "event: content_block_stop",
            f'data: {{"type":"content_block_stop","index":{i}}}',
            "",
        ]
    lines += [
        "event: message_delta",
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":5}}',
        "",
        "event: message_stop",
        'data: {"type":"message_stop"}',
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """Clear caches + patch routing to hermetic fixtures for every test."""
    from router.routing_cache import LRURoutingCache, TTLRoutingCache
    monkeypatch.setattr(dispatcher, "_AST_CACHE", {})
    # Reset to a fresh instance of the module's cache types.
    monkeypatch.setattr(dispatcher, "_ROUTING_CACHE", LRURoutingCache(max_entries=128))
    # P-0: reset the context-dir TTL routing cache so no test leaks routing state.
    monkeypatch.setattr(dispatcher, "_ROUTING_TTL_CACHE", TTLRoutingCache(max_entries=16, default_ttl_seconds=120.0))
    # Reset the per-IP rate-limit bucket store so no test leaks token state.
    monkeypatch.setattr(dispatcher, "_RATE_BUCKETS", type(dispatcher._RATE_BUCKETS)())
    monkeypatch.setattr(
        "router.ast_extractor.scan_project_codebase",
        lambda root_dir, ignore_dirs: ["// mock.py\n- def mock()\n"],
    )

    def _route(skeleton, prompt):
        return RoutingResult(target_files=[], confidence=0.0, reasoning="hermetic")

    monkeypatch.setattr("router.ollama_scorer.route_target_files", _route)


@pytest.fixture
def mock_upstream(monkeypatch):
    """Install a MockTransport upstream; returns a list recording each request.

    Usage::

        calls = mock_upstream([sse_body_1, sse_body_2, ...])

    Each item is either an SSE body string or an ``Exception`` instance. If the
    last item is an exception it is re-raised on every extra call (so retries
    see a persistent failure); otherwise an extra call fails the test loudly.
    """

    calls: List[httpx.Request] = []

    def _install(responses: List[Union[str, Exception]]) -> List[httpx.Request]:
        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            idx = len(calls) - 1
            if idx < len(responses):
                item = responses[idx]
                if isinstance(item, Exception):
                    raise item
                return httpx.Response(
                    200, text=item, headers={"content-type": "text/event-stream"}
                )
            last = responses[-1] if responses else None
            if isinstance(last, Exception):
                raise last
            raise AssertionError(f"unexpected upstream call #{len(calls)}")

        monkeypatch.setattr(dispatcher, "_UPSTREAM_TRANSPORT", httpx.MockTransport(handler))
        return calls

    return _install


async def _post_messages(body=None, headers=None):
    """POST /v1/messages to the ASGI app and return the response."""
    payload = body or {
        "model": "mock-model",
        "stream": True,
        "messages": [{"role": "user", "content": "hello"}],
    }
    req_headers = {"x-csmart-session": "test-session"}
    if headers:
        req_headers.update(headers)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/v1/messages", headers=req_headers, json=payload)
        return resp


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_text_deltas_streamed_to_client(mock_upstream):
    """QG-04: text content_block_delta events reach the client immediately."""
    calls = mock_upstream([_sse_text("Hello from upstream")])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert "Hello from upstream" in resp.text
    assert '"type": "content_block_delta"' in resp.text
    assert len(calls) == 1


def test_exploration_tool_use_intercepted_and_resubmitted(mock_upstream, tmp_path, monkeypatch):
    """QG-03: an exploration tool_use is held + resolved locally, not forwarded."""
    monkeypatch.setenv("CSMART_CONTEXT_DIR", str(tmp_path))
    partial = '{"pattern": "zzz_no_match_abc"}'
    partial_escaped = partial.replace('"', '\\"')
    round1 = _sse_tool_use_round("GrepTool", "tu_grep", partial_escaped)
    round2 = _sse_text("resolved by shadow")
    calls = mock_upstream([round1, round2])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert "resolved by shadow" in resp.text
    assert "GrepTool" not in resp.text
    assert "tu_grep" not in resp.text
    # Original request + one internal tool_result re-submission.
    assert len(calls) == 2


def test_non_exploration_tool_use_passed_through(mock_upstream):
    """QG-04: Edit/Write tool_use is forwarded immediately, never shadowed."""
    partial = '{"file_path": "x.py", "new_string": "y"}'
    partial_escaped = partial.replace('"', '\\"')
    block = _sse_tool_use(0, "Edit", "tu_edit", partial_escaped)
    calls = mock_upstream([block])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert '"name": "Edit"' in resp.text
    assert "GrepTool" not in resp.text
    # Edit is not shadowed -> exactly one upstream call, no re-submission.
    assert len(calls) == 1


def test_shadow_rounds_bounded_at_three(mock_upstream, tmp_path, monkeypatch):
    """N-4/OD-3: with 5 exploration tool_use, <= 3 are held, the rest pass through."""
    monkeypatch.setenv("CSMART_CONTEXT_DIR", str(tmp_path))
    round1 = _sse_n_tool_uses(5)
    round2 = _sse_text("done")
    calls = mock_upstream([round1, round2])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert len(calls) == 2  # original round + one re-submission
    # 3 held (never forwarded) + 2 passed through -> exactly 2 GrepTool blocks.
    assert resp.text.count('"name": "GrepTool"') == 2
    assert "done" in resp.text


def test_max_tokens_clamped_to_floor(mock_upstream):
    """Issue #1: max_tokens below the floor is raised to the floor upstream."""
    calls = mock_upstream([_sse_text("ok")])
    body = {
        "model": "mock-model",
        "stream": True,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = _run(_post_messages(body=body))

    assert resp.status_code == 200
    up_body = json.loads(calls[0].content)
    assert up_body["max_tokens"] == dispatcher._min_max_tokens()


def test_max_tokens_above_floor_preserved(mock_upstream):
    """Issue #1: max_tokens already at/above the floor is left untouched."""
    calls = mock_upstream([_sse_text("ok")])
    body = {
        "model": "mock-model",
        "stream": True,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = _run(_post_messages(body=body))

    assert resp.status_code == 200
    up_body = json.loads(calls[0].content)
    assert up_body["max_tokens"] == 8192


def test_max_tokens_defaulted_when_missing(mock_upstream):
    """Issue #1: absent max_tokens is defaulted to the floor."""
    calls = mock_upstream([_sse_text("ok")])
    body = {
        "model": "mock-model",
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = _run(_post_messages(body=body))

    assert resp.status_code == 200
    up_body = json.loads(calls[0].content)
    assert up_body["max_tokens"] == dispatcher._min_max_tokens()


def test_empty_tool_input_defensive_error(mock_upstream, tmp_path, monkeypatch):
    """Issue #1: a tool_use with no streamed args yields an actionable error
    (action=empty_input), not the silent 'no path provided' retry error."""
    monkeypatch.setenv("CSMART_CONTEXT_DIR", str(tmp_path))
    round1 = _sse_tool_use_empty_round("read_file", "tu_empty")
    round2 = _sse_text("recovered")
    calls = mock_upstream([round1, round2])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert "recovered" in resp.text
    assert "tu_empty" not in resp.text  # held, never forwarded to client
    assert len(calls) == 2
    followup = json.loads(calls[1].content)
    results = followup["messages"][-1]["content"]
    assert results[0]["type"] == "tool_result"
    assert "empty input" in results[0]["content"]
    assert "no path provided" not in results[0]["content"]


def test_truncated_tool_input_defensive_error(mock_upstream, tmp_path, monkeypatch):
    """Issue #1: partial_json that never parses is flagged truncated_input."""
    monkeypatch.setenv("CSMART_CONTEXT_DIR", str(tmp_path))
    partial = '{"file_path": "router/dis'
    partial_escaped = partial.replace('"', '\\"')
    round1 = _sse_tool_use_round("read_file", "tu_partial", partial_escaped)
    round2 = _sse_text("recovered")
    calls = mock_upstream([round1, round2])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert "recovered" in resp.text
    assert len(calls) == 2
    followup = json.loads(calls[1].content)
    results = followup["messages"][-1]["content"]
    assert results[0]["type"] == "tool_result"
    assert "truncated" in results[0]["content"]


def test_routing_runs_once_per_session(mock_upstream, monkeypatch):
    """P-1/QG-02: two requests in one session route via Ollama only once."""
    calls = mock_upstream([_sse_text("r1"), _sse_text("r2")])
    route_calls: List[str] = []

    def _counting_route(skeleton, prompt):
        route_calls.append(prompt)
        return RoutingResult(target_files=[], confidence=0.0, reasoning="counting")

    monkeypatch.setattr("router.ollama_scorer.route_target_files", _counting_route)

    resp1 = _run(_post_messages(headers={"x-csmart-session": "s1"}))
    resp2 = _run(_post_messages(headers={"x-csmart-session": "s1"}))

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert len(route_calls) == 1
    assert len(calls) == 2


def test_upstream_timeout_emits_graceful_sse_error(mock_upstream):
    """P-3: upstream connect timeout -> clean SSE error, no hang, bounded retries."""
    calls = mock_upstream([httpx.ConnectTimeout(message="upstream down")])

    resp = _run(_post_messages())

    assert resp.status_code == 200
    assert '"type": "error"' in resp.text
    assert "api_error" in resp.text
    # 1 attempt + 2 retries (MAX_UPSTREAM_RETRIES = 2).
    assert len(calls) == 3


def test_inject_skips_path_traversal(cwd_tmp, caplog):
    """F-09: injection skips ../ paths via safe_path, valid files still injected."""
    (cwd_tmp / "good.py").write_text("GOOD_CONTENT")

    messages = [{"role": "user", "content": "do it"}]
    out = inject_context_to_messages(messages, ["../etc/passwd", "good.py"])

    last = out[-1]["content"]
    assert "GOOD_CONTENT" in last
    assert "../etc/passwd" not in last
    assert "root:" not in last
    assert any("path traversal" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Wave 5 Track C hardening tests (S-1 whitelist, S-2 loopback/rate-limit, P-5 body cap).
# ---------------------------------------------------------------------------


def test_non_loopback_client_rejected_403(mock_upstream):
    """S-2: a non-loopback peer is rejected before any routing/upstream call."""
    calls = mock_upstream([_sse_text("should not happen")])

    async def scenario():
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 40000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
            return resp

    resp = _run(scenario())
    assert resp.status_code == 403
    assert "loopback" in resp.text
    assert len(calls) == 0


def test_allow_external_env_bypasses_loopback(mock_upstream, monkeypatch):
    """S-2: CSMART_ALLOW_EXTERNAL=1 lets a non-loopback peer through."""
    monkeypatch.setenv("CSMART_ALLOW_EXTERNAL", "1")
    calls = mock_upstream([_sse_text("external ok")])

    async def scenario():
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 40000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
            return resp

    resp = _run(scenario())
    assert resp.status_code == 200
    assert "external ok" in resp.text
    assert len(calls) == 1


def test_rate_limit_returns_429(mock_upstream, monkeypatch):
    """S-2: 4th request inside the same minute returns 429 + Retry-After.

    Uses a non-loopback peer (loopback peers are now exempt from token
    consumption), so the token bucket is what produces the 429.
    """
    monkeypatch.setenv("CSMART_RATE_LIMIT_PER_MIN", "3")
    monkeypatch.setenv("CSMART_ALLOW_EXTERNAL", "1")
    calls = mock_upstream([_sse_text("r1"), _sse_text("r2"), _sse_text("r3"), _sse_text("r4")])

    async def scenario():
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 40000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            statuses = []
            retry_after = None
            for _ in range(4):
                resp = await client.post(
                    "/v1/messages",
                    headers={"x-csmart-session": "s1"},
                    json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
                )
                statuses.append(resp.status_code)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("retry-after")
            return statuses, retry_after

    statuses, retry_after = _run(scenario())
    assert statuses == [200, 200, 200, 429]
    assert retry_after == "60"
    assert len(calls) == 3


def test_oversized_body_rejected_413(mock_upstream, monkeypatch):
    """P-5: an oversized POST body is rejected with 413 before any upstream call."""
    monkeypatch.setenv("CSMART_MAX_BODY_BYTES", "64")
    calls = mock_upstream([_sse_text("should not happen")])
    big_body = {
        "model": "mock-model",
        "stream": True,
        "messages": [{"role": "user", "content": "x" * 200}],
    }

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json=big_body,
            )
            return resp

    resp = _run(scenario())
    assert resp.status_code == 413
    assert "large" in resp.text.lower()
    assert len(calls) == 0


def test_read_full_body_rejects_oversized(monkeypatch):
    """P-5: read_full_body catches the chunked/no-content-length oversized path."""
    monkeypatch.setenv("CSMART_MAX_BODY_BYTES", "64")
    big_body = {
        "model": "mock",
        "messages": [{"role": "user", "content": "x" * 200}],
    }
    req = httpx.Request("POST", "http://test/v1/messages", json=big_body)
    # Drop content-length so only the read_full_body cap can reject.
    req.headers.pop("content-length", None)

    with pytest.raises(dispatcher.BodyTooLargeError):
        _run(dispatcher.read_full_body(_asgi_request(req)))


def test_upstream_headers_whitelist():
    """S-1: _build_upstream_headers forwards only allowlisted headers."""
    req = httpx.Request(
        "POST",
        "http://test/v1/messages",
        headers={
            "authorization": "Bearer tok",
            "x-api-key": "key-123",
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "cookie": "session=abc",
            "user-agent": "Mozilla/5.0",
            "x-csmart-session": "test-session",
            "sec-ch-ua": '"Not A Brand"',
        },
    )
    headers = dispatcher._build_upstream_headers(_asgi_request(req))
    lower = {k.lower(): v for k, v in headers.items()}
    assert lower["authorization"] == "Bearer tok"
    assert lower["x-api-key"] == "key-123"
    assert lower["content-type"] == "application/json"
    assert lower["anthropic-version"] == "2023-06-01"
    for stripped in ("cookie", "user-agent", "x-csmart-session", "sec-ch-ua"):
        assert stripped not in lower


def test_upstream_headers_whitelist_end_to_end(mock_upstream):
    """S-1: end-to-end, sensitive client headers never reach the upstream call."""
    calls = mock_upstream([_sse_text("ok")])

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                headers={
                    "x-csmart-session": "s1",
                    "authorization": "Bearer tok",
                    "x-api-key": "key-123",
                    "cookie": "session=abc",
                    "user-agent": "Mozilla/5.0",
                    "sec-ch-ua": '"Not A Brand"',
                },
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
            return resp

    resp = _run(scenario())
    assert resp.status_code == 200
    up_headers = {k.lower(): v for k, v in calls[0].headers.items()}
    assert up_headers.get("authorization") == "Bearer tok"
    assert up_headers.get("x-api-key") == "key-123"
    assert up_headers.get("content-type") == "application/json"
    assert "cookie" not in up_headers
    assert "x-csmart-session" not in up_headers
    assert "sec-ch-ua" not in up_headers
    # The client's user-agent must not leak upstream (httpx sets its own default).
    assert up_headers.get("user-agent", "") != "Mozilla/5.0"


def test_read_body_bounded_aborts_early(monkeypatch):
    """P-5 MAJOR: an oversized chunked body aborts early, never full-buffers."""
    monkeypatch.setenv("CSMART_MAX_BODY_BYTES", "64")
    chunk = b"y" * 32
    remaining = [chunk for _ in range(100)]  # 3200 bytes total
    consumed: Dict[str, int] = {"chunks": 0, "bytes": 0}

    async def receive() -> Dict[str, Any]:
        if remaining:
            c = remaining.pop(0)
            consumed["chunks"] += 1
            consumed["bytes"] += len(c)
            return {"type": "http.request", "body": c, "more_body": bool(remaining)}
        return {"type": "http.request", "body": b"", "more_body": False}

    scope: Dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/messages",
        "raw_path": b"/v1/messages",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    req = Request(scope, receive)

    with pytest.raises(dispatcher.BodyTooLargeError):
        _run(dispatcher._read_body_bounded(req))

    # Abort on the 3rd chunk (96 bytes > 64 cap), not after reading all 3200.
    assert consumed["chunks"] <= 3
    assert consumed["bytes"] <= 96


def test_loopback_variants_accepted(mock_upstream):
    """S-2: IPv4-mapped and other 127/8 loopback peers are accepted (no 403)."""
    calls = mock_upstream([_sse_text("ok1"), _sse_text("ok2")])

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("::ffff:127.0.0.1", 40000)),
            base_url="http://test",
        ) as client:
            r1 = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.2", 40001)),
            base_url="http://test",
        ) as client:
            r2 = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
        return r1.status_code, r2.status_code

    s1, s2 = _run(scenario())
    assert s1 == 200
    assert s2 == 200
    assert len(calls) == 2


def test_403_does_not_consume_rate_token(mock_upstream, monkeypatch):
    """S-2: a rejected non-loopback 403 must not consume a rate token."""
    monkeypatch.setenv("CSMART_RATE_LIMIT_PER_MIN", "1")
    monkeypatch.setenv("CSMART_ALLOW_EXTERNAL", "0")
    calls = mock_upstream([_sse_text("ok"), _sse_text("ok2")])

    async def scenario():
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 40000))
        # Loopback-only enforcement rejects before any token consumption.
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r403 = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
        # Now allow external: the single token must still be available.
        monkeypatch.setenv("CSMART_ALLOW_EXTERNAL", "1")
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
            r2 = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
        return r403.status_code, r1.status_code, r2.status_code

    s403, s1, s2 = _run(scenario())
    assert s403 == 403
    assert s1 == 200
    assert s2 == 429
    assert len(calls) == 1


def test_loopback_not_rate_limited(mock_upstream, monkeypatch):
    """S-2: loopback peers are exempt from rate limiting (no spurious 429s)."""
    monkeypatch.setenv("CSMART_RATE_LIMIT_PER_MIN", "1")
    calls = mock_upstream([_sse_text("ok")] * 4)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            statuses = []
            for _ in range(4):
                resp = await client.post(
                    "/v1/messages",
                    headers={"x-csmart-session": "s1"},
                    json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
                )
                statuses.append(resp.status_code)
            return statuses

    statuses = _run(scenario())
    assert statuses == [200, 200, 200, 200]
    assert len(calls) == 4


def test_passthrough_content_length_413_json(mock_upstream, monkeypatch):
    """P-5: oversized Content-Length on a passthrough route returns JSON, no upstream."""
    monkeypatch.setenv("CSMART_MAX_BODY_BYTES", "64")
    calls = mock_upstream([_sse_text("should not happen")])

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/v1/models", content=b"x" * 200)
            return resp

    resp = _run(scenario())
    assert resp.status_code == 413
    assert resp.json() == {"error": "request_too_large"}
    assert len(calls) == 0


def test_invalid_json_400(mock_upstream):
    """P-5 fix: an unparseable /v1/messages body returns a JSON 400."""
    calls = mock_upstream([_sse_text("should not happen")])

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1", "content-type": "application/json"},
                content=b"{not json",
            )
            return resp

    resp = _run(scenario())
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"].startswith("invalid json")
    assert len(calls) == 0


def test_check_ollama_health_uses_triage_model(monkeypatch):
    """check_ollama_health probes OLLAMA_TRIAGE_MODEL, not OLLAMA_MODEL."""
    import ollama

    shown: List[str] = []
    monkeypatch.setenv("OLLAMA_TRIAGE_MODEL", "triage-test-model")
    monkeypatch.setenv("OLLAMA_MODEL", "other-model")
    monkeypatch.setattr(ollama, "show", lambda model: shown.append(model))

    assert dispatcher.check_ollama_health() is True
    assert shown == ["triage-test-model"]


@pytest.fixture
def cwd_tmp(tmp_path):
    """chdir to tmp_path so inject's base '.' == tmp_path; restore afterwards."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Routing input cap tests (P-2 prefill reduction: skeleton + prompt truncation).
# ---------------------------------------------------------------------------


def test_cap_skeleton_under_budget_unchanged():
    """A skeleton already under the cap is returned byte-identical."""
    skeleton = "// a.py\n- def foo()\n- class Bar:\n"
    assert dispatcher._cap_skeleton(skeleton, max_chars=6000) == skeleton


def test_cap_skeleton_preserves_headers_drops_longest_signatures():
    """Over budget: every // header is kept, the longest - signatures go first."""
    skeleton = "\n".join([
        "// a.py",
        "- short",
        "- " + "x" * 50,
        "- " + "y" * 40,
        "// b.py",
        "- " + "z" * 30,
    ])
    capped = dispatcher._cap_skeleton(skeleton, max_chars=60)
    assert "// a.py" in capped
    assert "// b.py" in capped
    assert len(capped) <= 60
    assert ("x" * 50) not in capped  # longest dropped first
    assert ("y" * 40) not in capped
    assert ("z" * 30) in capped       # shortest kept


def test_cap_skeleton_path_only_fits_by_trimming_headers():
    """Even a path-only skeleton over an absurdly small budget keeps the first N."""
    skeleton = "\n".join(f"// file{i}.py" for i in range(10))
    capped = dispatcher._cap_skeleton(skeleton, max_chars=30)
    assert len(capped) <= 30
    assert capped.count("// file") == 2  # only the first 2 headers fit


def test_truncate_routing_prompt_keeps_tail():
    """Long prompts are cut to the TAIL (the task statement lives at the end)."""
    prompt = "A" * 100 + "TASK_AT_END"
    truncated = dispatcher._truncate_routing_prompt(prompt, max_chars=20)
    assert truncated == "A" * 9 + "TASK_AT_END"
    assert len(truncated) == 20
    assert truncated.endswith("TASK_AT_END")


def test_truncate_routing_prompt_short_unchanged():
    """A short prompt is returned unchanged."""
    prompt = "short task"
    assert dispatcher._truncate_routing_prompt(prompt, max_chars=4000) == prompt


def test_run_local_routing_passes_capped_skeleton(monkeypatch):
    """run_local_routing hands Ollama a skeleton capped to the env budget."""
    seen: Dict[str, Any] = {}
    monkeypatch.setenv("CSMART_ROUTING_SKELETON_MAX_CHARS", "120")
    big_skeleton = "\n".join(
        f"// file{i}.py\n" + "\n".join(
            f"- def func_{i}_{j}()" for j in range(10)
        )
        for i in range(5)
    )

    def _route(skeleton, prompt):
        seen["skeleton"] = skeleton
        return RoutingResult(target_files=[], confidence=0.0, reasoning="capped")

    monkeypatch.setattr(
        "router.ast_extractor.scan_project_codebase",
        lambda root_dir, ignore_dirs: [big_skeleton],
    )
    monkeypatch.setattr("router.ollama_scorer.route_target_files", _route)

    _run(dispatcher.run_local_routing("task", session_key="cap-session"))

    assert len(seen["skeleton"]) <= 120
    for i in range(5):
        assert ("// file%d.py" % i) in seen["skeleton"]


def test_routing_ttl_cache_reuses_across_burst(monkeypatch):
    """P-0: session-less requests in one burst route via Ollama only once."""
    route_calls: List[str] = []

    def _counting_route(skeleton, prompt):
        route_calls.append(prompt)
        return RoutingResult(target_files=["a.py"], confidence=0.8, reasoning="ttl")

    monkeypatch.setattr("router.ollama_scorer.route_target_files", _counting_route)
    monkeypatch.setattr(
        "router.ast_extractor.scan_project_codebase",
        lambda root_dir, ignore_dirs: ["// a.py\n- def a()\n"],
    )

    _run(dispatcher.run_local_routing("task one"))
    _run(dispatcher.run_local_routing("task two"))

    assert len(route_calls) == 1


def test_routing_ttl_cache_expires_when_ttl_zero(monkeypatch):
    """P-0: TTL=0 disables reuse — every session-less request re-routes."""
    route_calls: List[str] = []
    monkeypatch.setenv("CSMART_ROUTING_TTL", "0")

    def _counting_route(skeleton, prompt):
        route_calls.append(prompt)
        return RoutingResult(target_files=[], confidence=0.0, reasoning="ttl0")

    monkeypatch.setattr("router.ollama_scorer.route_target_files", _counting_route)

    _run(dispatcher.run_local_routing("one"))
    _run(dispatcher.run_local_routing("two"))

    assert len(route_calls) == 2


# ---------------------------------------------------------------------------
# Unit tests for the extracted routing_cache module.
# ---------------------------------------------------------------------------


def test_lru_cache_bounded_evicts_oldest():
    """LRU cache respects max capacity and evicts least recently used."""
    from router.routing_cache import LRURoutingCache
    cache = LRURoutingCache(max_entries=3)

    r1 = RoutingResult(target_files=["a.py"], confidence=1.0, reasoning="r1")
    r2 = RoutingResult(target_files=["b.py"], confidence=1.0, reasoning="r2")
    r3 = RoutingResult(target_files=["c.py"], confidence=1.0, reasoning="r3")
    r4 = RoutingResult(target_files=["d.py"], confidence=1.0, reasoning="r4")

    cache.put("k1", r1)
    cache.put("k2", r2)
    cache.put("k3", r3)
    assert len(cache) == 3

    # Access k1 to bump recency
    assert cache.get("k1") == r1
    # Add k4 - should evict k2 (oldest now)
    cache.put("k4", r4)
    assert len(cache) == 3

    assert cache.get("k2") is None  # evicted
    assert cache.get("k1") == r1   # still here (recently accessed)
    assert cache.get("k3") == r3  # still here
    assert cache.get("k4") == r4  # added


def test_lru_cache_get_bumps_recency():
    """Get on an existing entry moves it to the end of the LRU order."""
    from router.routing_cache import LRURoutingCache
    cache = LRURoutingCache(max_entries=3)

    r1 = RoutingResult(target_files=["a.py"], confidence=1.0, reasoning="r1")
    r2 = RoutingResult(target_files=["b.py"], confidence=1.0, reasoning="r2")
    r3 = RoutingResult(target_files=["c.py"], confidence=1.0, reasoning="r3")
    r4 = RoutingResult(target_files=["d.py"], confidence=1.0, reasoning="r4")

    cache.put("k1", r1)
    cache.put("k2", r2)
    cache.put("k3", r3)

    # Get k1 - now it's the most recent
    assert cache.get("k1") == r1
    # Add k4 should evict k2 (the new oldest) not k1
    cache.put("k4", r4)
    assert cache.get("k1") == r1
    assert cache.get("k2") is None


def test_ttl_cache_bounded_evicts_oldest():
    """TTL cache respects max capacity and evicts oldest entry by timestamp."""
    from router.routing_cache import TTLRoutingCache
    # Fixed TTL provider that always returns 100s (enough for this test)
    cache = TTLRoutingCache(
        max_entries=3,
        default_ttl_seconds=100.0,
        ttl_seconds_provider=lambda: 100.0,
    )

    r1 = RoutingResult(target_files=["a.py"], confidence=1.0, reasoning="r1")
    r2 = RoutingResult(target_files=["b.py"], confidence=1.0, reasoning="r2")
    r3 = RoutingResult(target_files=["c.py"], confidence=1.0, reasoning="r3")
    r4 = RoutingResult(target_files=["d.py"], confidence=1.0, reasoning="r4")

    cache.put("k1", r1)
    # We need to ensure different timestamps, so sleep a tiny bit
    import time
    time.sleep(0.001)
    cache.put("k2", r2)
    time.sleep(0.001)
    cache.put("k3", r3)
    assert len(cache) == 3

    time.sleep(0.001)
    cache.put("k4", r4)
    assert len(cache) == 3

    # Oldest (k1) should be evicted
    assert cache.get("k1") is None
    assert cache.get("k2") == r2
    assert cache.get("k3") == r3
    assert cache.get("k4") == r4


def test_ttl_cache_expires_stale_entries():
    """Expired entries are evicted on lookup and None is returned."""
    from router.routing_cache import TTLRoutingCache
    # TTL = 0 means everything is immediately stale
    cache = TTLRoutingCache(
        max_entries=3,
        default_ttl_seconds=0.0,
        ttl_seconds_provider=lambda: 0.0,
    )
    r1 = RoutingResult(target_files=["a.py"], confidence=1.0, reasoning="r1")
    cache.put("k1", r1)
    assert len(cache) == 1
    # Lookup should expire it
    assert cache.get("k1") is None
    assert len(cache) == 0


def test_ttl_cache_reads_env_ttl():
    """TTL cache reads CSMART_ROUTING_TTL from environment when using default provider."""
    import os
    from router.routing_cache import TTLRoutingCache
    # Save original env
    orig = os.environ.get("CSMART_ROUTING_TTL")
    try:
        os.environ["CSMART_ROUTING_TTL"] = "60"
        cache = TTLRoutingCache(max_entries=16, default_ttl_seconds=120.0)
        assert cache.ttl_seconds() == 60.0

        os.environ["CSMART_ROUTING_TTL"] = "invalid"
        cache = TTLRoutingCache(max_entries=16, default_ttl_seconds=120.0)
        assert cache.ttl_seconds() == 120.0  # fall back to default

        os.environ.pop("CSMART_ROUTING_TTL", None)
        cache = TTLRoutingCache(max_entries=16, default_ttl_seconds=120.0)
        assert cache.ttl_seconds() == 120.0
    finally:
        # Restore original env
        if orig is None:
            os.environ.pop("CSMART_ROUTING_TTL", None)
        else:
            os.environ["CSMART_ROUTING_TTL"] = orig
