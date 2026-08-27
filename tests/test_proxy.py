"""Hermetic tests for the csmart reverse-proxy engine (``router.dispatcher``).

No live network, no live Ollama: the ASGI app is driven with
``httpx.ASGITransport`` and the upstream gateway is replaced with
``httpx.MockTransport``. AST scanning and Ollama routing are patched with
hermetic fixtures.

Every test in this module is hermetic, so ``pytest -m "not live"`` runs the
full module without touching the network. (No test here intentionally needs the
real upstream, so none carries a ``pytest.mark.live`` marker.)
"""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.dispatcher import app
from router.ollama_scorer import RoutingResult
import router.dispatcher as dispatcher


def _run(coro):
    """Run a coroutine to completion with a fresh event loop."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """Clear proxy caches + patch routing so no test touches Ollama/AST."""
    monkeypatch.setattr(dispatcher, "_AST_CACHE", {})
    # Reset to a fresh instance of the module's cache type (OrderedDict LRU).
    monkeypatch.setattr(dispatcher, "_ROUTING_CACHE", type(dispatcher._ROUTING_CACHE)())
    # Reset the per-IP rate-limit bucket store so no test leaks token state.
    monkeypatch.setattr(dispatcher, "_RATE_BUCKETS", type(dispatcher._RATE_BUCKETS)())
    monkeypatch.setattr(
        "router.ast_extractor.scan_project_codebase",
        lambda root_dir, ignore_dirs: ["// mock.py\n- def mock()\n"],
    )

    def _route(skeleton, prompt):
        return RoutingResult(target_files=[], confidence=0.0, reasoning="hermetic")

    monkeypatch.setattr("router.ollama_scorer.route_target_files", _route)


def test_options_cors():
    """CORS preflight OPTIONS allows a loopback Origin and echoes it."""

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.options(
                "/v1/messages", headers={"Origin": "http://127.0.0.1:3000"}
            )
            return resp.status_code, dict(resp.headers)

    status, headers = _run(scenario())
    assert status == 200
    assert headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert headers["access-control-allow-methods"] == "*"
    assert headers["access-control-allow-headers"] == "*"


def test_options_cors_non_loopback_origin_omitted():
    """CORS preflight with a non-loopback Origin gets no allow-origin header."""

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.options(
                "/v1/messages", headers={"Origin": "http://evil.example"}
            )
            return resp.status_code, dict(resp.headers)

    status, headers = _run(scenario())
    assert status == 200
    assert "access-control-allow-origin" not in headers
    assert headers["access-control-allow-methods"] == "*"


def test_passthrough_with_mock_upstream(monkeypatch):
    """Non-messages requests pass through untouched via MockTransport."""

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/v1/models")
            return resp.status_code, resp.json()

    monkeypatch.setattr(
        dispatcher,
        "_UPSTREAM_TRANSPORT",
        httpx.MockTransport(
            lambda req: httpx.Response(200, json={"data": [{"id": "mock-model"}]})
        ),
    )

    status, body = _run(scenario())
    assert status == 200
    assert body == {"data": [{"id": "mock-model"}]}


def test_messages_intercepted_and_streamed(monkeypatch):
    """/v1/messages is intercepted and the mocked SSE upstream is streamed back."""

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/messages",
                headers={"x-csmart-session": "s1"},
                json={"model": "mock", "messages": [{"role": "user", "content": "hi"}]},
            )
            return resp.status_code, resp.text

    sse_body = (
        "event: message_start\n"
        'data: {"type":"message_start","message":{"id":"m1","role":"assistant","content":[],"model":"mock"}}\n\n'
        "event: content_block_start\n"
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}\n\n'
    )
    monkeypatch.setattr(
        dispatcher,
        "_UPSTREAM_TRANSPORT",
        httpx.MockTransport(
            lambda req: httpx.Response(
                200, text=sse_body, headers={"content-type": "text/event-stream"}
            )
        ),
    )

    status, text = _run(scenario())
    assert status == 200
    assert '"type": "message_start"' in text
    assert '"type": "content_block_delta"' in text
    assert "hello" in text
