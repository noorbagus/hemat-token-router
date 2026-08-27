"""Hermetic server tests for the csmart proxy engine (``router.dispatcher``).

Drives the FastAPI app with ``httpx.ASGITransport`` and replaces the upstream
gateway with ``httpx.MockTransport`` serving canned SSE responses. AST scanning
and Ollama routing are patched to hermetic fixtures. No live Ollama and no live
upstream: the whole module runs under ``pytest -m "not live"``.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Union

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.dispatcher import app, inject_context_to_messages
from router.ollama_scorer import RoutingResult
import router.dispatcher as dispatcher


def _run(coro):
    """Run a coroutine to completion with a fresh event loop."""
    return asyncio.run(coro)


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
    monkeypatch.setattr(dispatcher, "_AST_CACHE", {})
    monkeypatch.setattr(dispatcher, "_ROUTING_CACHE", {})
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


@pytest.fixture
def cwd_tmp(tmp_path):
    """chdir to tmp_path so inject's base '.' == tmp_path; restore afterwards."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old_cwd)
