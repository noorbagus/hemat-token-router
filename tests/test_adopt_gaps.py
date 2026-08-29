"""Hermetic tests for the 7 gap fixes implemented in csmart_proxy.py.

Covers:
- K1  : chat history tool_use preserved through ``_convert_anthropic_message_to_openai``
- K2a : chat SSE ``delta.reasoning_content`` -> Anthropic ``thinking`` blocks
- K2b : Responses SSE ``reasoning_summary_text`` -> Anthropic ``thinking`` blocks
        + request-side thinking round-trip (chat + responses)
- K3  : ``cache_read_input_tokens`` emitted from ``prompt_tokens_details.cached_tokens``

Runs under ``pytest -m "not live"`` — no network, no Ollama. Pure transform
unit tests; no ASGI/MockTransport required.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import csmart_proxy as cp


# ---------------------------------------------------------------------------
# Fixtures - same hermetic pattern as test_csmart_proxy_openai.py.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset global state between tests so transforms are hermetic."""
    monkeypatch.setattr(cp, "DB_PATH", str(tmp_path / "csmart_state.db"))
    monkeypatch.setattr(cp, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(cp, "UPSTREAM_API_KEY", "test-key-never-leaked")
    monkeypatch.setattr(cp, "_UPSTREAM_TRANSPORT", None)
    monkeypatch.setattr(cp.vault, "mem_cache", {})
    monkeypatch.setattr(cp.vault, "reverse_cache", {})
    monkeypatch.setattr(cp, "_session_model", {})
    monkeypatch.setattr(cp, "_prefix_snapshot", None)
    monkeypatch.setattr(cp, "_active_model", cp.FLASH_MODEL)
    cp.init_db()


# ---------------------------------------------------------------------------
# Helpers - consume the async SSE transforms synchronously.
# ---------------------------------------------------------------------------

Event = Tuple[str | None, dict[str, Any]]


def _collect_chat_sse(chunks: List[dict[str, Any]]) -> List[Event]:
    """Consume ``transform_openai_sse_to_anthropic`` synchronously.

    OpenAI chat-completions SSE carries no event name on the wire, so we yield
    ``(None, chunk)`` tuples — the transform's contract is ``(event_name, payload)``
    exactly like the Responses variant.
    """
    async def _run() -> List[Event]:
        async def gen() -> AsyncGenerator[Event, None]:
            for chunk in chunks:
                yield None, chunk
        out: List[Event] = []
        async for item in cp.transform_openai_sse_to_anthropic(gen()):
            out.append(item)
        return out
    return asyncio.run(_run())


def _collect_responses_sse(events: List[Event]) -> List[Event]:
    """Consume ``transform_openai_responses_sse_to_anthropic`` synchronously.

    Responses API SSE is event-named, so we feed ``(event_name, payload)``
    tuples exactly like test_csmart_proxy_openai.py::_collect_sse.
    """
    async def _run() -> List[Event]:
        async def gen():
            for e in events:
                yield e
        out: List[Event] = []
        async for item in cp.transform_openai_responses_sse_to_anthropic(gen()):
            out.append(item)
        return out
    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# K1 - chat history tool_use preserved.
# ---------------------------------------------------------------------------


def test_chat_history_tool_use_preserved():
    """Anthropic tool_use/tool_result turns must survive the OpenAI request
    transform: assistant carries ``tool_calls``, the tool_result becomes a
    ``role: tool`` message, and no empty user stub is left behind."""
    messages = [
        {"role": "user", "content": "hitung 1+1"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "hasil:"},
                {"type": "tool_use", "id": "call_1", "name": "calculator", "input": {"a": 1, "b": 1}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": [{"type": "text", "text": "2"}]}
            ],
        },
    ]

    converted: List[dict[str, Any]] = []
    for msg in messages:
        result = cp._convert_anthropic_message_to_openai(msg)
        # Per-message result is a List of OpenAI messages (not a dict).
        assert isinstance(result, list), f"expected List, got {type(result).__name__}"
        converted.extend(result)

    # No empty user stub (the tool_result turn must not emit an empty user msg).
    assert not any(
        m.get("role") == "user" and not m.get("content") for m in converted
    ), f"empty user stub emitted: {converted}"

    # tool role message carrying the tool_result payload.
    tool_msgs = [m for m in converted if m.get("role") == "tool"]
    assert len(tool_msgs) == 1, f"expected 1 tool message, got {converted}"
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert "2" in tool_msgs[0]["content"]

    # assistant message carrying tool_calls (name + JSON-parseable arguments).
    assistant_msgs = [m for m in converted if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(assistant_msgs) == 1, f"expected 1 assistant tool_calls msg, got {converted}"
    tc = assistant_msgs[0]["tool_calls"]
    assert isinstance(tc, list) and tc, "tool_calls must be a non-empty list"
    assert tc[0]["function"]["name"] == "calculator"
    args = json.loads(tc[0]["function"]["arguments"])
    assert args == {"a": 1, "b": 1}


# ---------------------------------------------------------------------------
# K2a - chat SSE reasoning_content -> Anthropic thinking blocks.
# ---------------------------------------------------------------------------


def test_chat_sse_reasoning_to_thinking():
    """A chat chunk carrying both ``reasoning_content`` and ``content`` must
    yield Anthropic thinking + text blocks, thinking first (index 0)."""
    chunks = [
        {"choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"reasoning_content": "thinking...", "content": "hello"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    events = _collect_chat_sse(chunks)

    # message_start carries id/model/usage.
    starts = [p for t, p in events if t == "message_start"]
    assert starts, f"no message_start in {events}"
    msg = starts[0]["message"]
    assert "id" in msg and "model" in msg and "usage" in msg

    # content_block_start: both thinking and text blocks.
    cbs = [p for t, p in events if t == "content_block_start"]
    types = [cb["content_block"]["type"] for cb in cbs]
    assert "thinking" in types, f"no thinking block start: {cbs}"
    assert "text" in types, f"no text block start: {cbs}"

    # content_block_delta: both thinking_delta and text_delta.
    deltas = [p for t, p in events if t == "content_block_delta"]
    delta_types = [d["delta"]["type"] for d in deltas]
    assert "thinking_delta" in delta_types, f"no thinking_delta: {deltas}"
    assert "text_delta" in delta_types, f"no text_delta: {deltas}"

    # reasoning text preserved in the thinking deltas.
    thinking_text = "".join(
        d["delta"].get("thinking", "")
        for d in deltas
        if d["delta"].get("type") == "thinking_delta"
    )
    assert "thinking..." in thinking_text, f"reasoning text lost: {deltas}"

    # Thinking block precedes the text block (index 0 < index 1).
    thinking_idx = next(cb["index"] for cb in cbs if cb["content_block"]["type"] == "thinking")
    text_idx = next(cb["index"] for cb in cbs if cb["content_block"]["type"] == "text")
    assert thinking_idx < text_idx

    # message_delta arrives before message_stop.
    etypes = [t for t, _ in events]
    assert "message_delta" in etypes and "message_stop" in etypes
    assert etypes.index("message_delta") < etypes.index("message_stop")


# ---------------------------------------------------------------------------
# K2b - Responses SSE reasoning_summary -> Anthropic thinking blocks.
# ---------------------------------------------------------------------------


def test_responses_sse_reasoning_to_thinking():
    """Responses API reasoning_summary_text deltas must become Anthropic
    thinking blocks, emitted before the text block."""
    events: List[Event] = [
        (
            "response.created",
            {"type": "response.created", "response": {"id": "resp_1", "model": "deepseek-reasoner"}},
        ),
        (
            "response.reasoning_summary_text.delta",
            {"type": "response.reasoning_summary_text.delta", "delta": "thinking..."},
        ),
        ("response.reasoning_summary_text.done", {"type": "response.reasoning_summary_text.done"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "hello"}),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
        ),
    ]
    result = _collect_responses_sse(events)

    # A thinking content block must be started.
    cbs = [p for t, p in result if t == "content_block_start"]
    types = [cb["content_block"]["type"] for cb in cbs]
    assert "thinking" in types, f"no thinking block start: {cbs}"

    # thinking_delta deltas must be emitted.
    deltas = [p for t, p in result if t == "content_block_delta"]
    delta_types = [d["delta"]["type"] for d in deltas]
    assert "thinking_delta" in delta_types, f"no thinking_delta: {deltas}"

    # Reasoning text preserved in thinking deltas.
    thinking_text = "".join(
        d["delta"].get("thinking", "")
        for d in deltas
        if d["delta"].get("type") == "thinking_delta"
    )
    assert "thinking..." in thinking_text, f"reasoning text lost: {deltas}"

    # Thinking block uses a distinct anti-collision index (1000) and must be
    # *opened* before the text block in stream order (not numerically lower).
    thinking_idx = next(cb["index"] for cb in cbs if cb["content_block"]["type"] == "thinking")
    text_idx = next(cb["index"] for cb in cbs if cb["content_block"]["type"] == "text")
    assert thinking_idx != text_idx, "thinking and text must use distinct indices"
    assert cbs.index(next(cb for cb in cbs if cb["content_block"]["type"] == "thinking")) < \
        cbs.index(next(cb for cb in cbs if cb["content_block"]["type"] == "text")), \
        "thinking block must be opened before the text block"


# ---------------------------------------------------------------------------
# K2b request side - thinking block round-trip into OpenAI request payloads.
# ---------------------------------------------------------------------------


def test_thinking_block_roundtrip():
    """An assistant ``thinking`` block must survive the request transform on
    both the chat-completions and responses paths."""
    msg = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "jawab"},
            {"type": "thinking", "thinking": "langkah2"},
        ],
    }

    # Chat-completions request side: DeepSeek-style ``reasoning_content``.
    chat_msgs = cp._convert_anthropic_message_to_openai(msg)
    assert isinstance(chat_msgs, list) and chat_msgs
    chat_assistant = chat_msgs[0]
    assert chat_assistant["role"] == "assistant"
    assert "langkah2" in str(chat_assistant.get("reasoning_content", ""))

    # Responses request side: a ``reasoning`` item (or reasoning_content field).
    resp_items = cp._convert_anthropic_message_to_openai_responses(msg)
    if isinstance(resp_items, dict):
        resp_items = [resp_items]
    assert isinstance(resp_items, list) and resp_items
    reasoning_found = False
    for item in resp_items:
        if item.get("type") == "reasoning" and "langkah2" in json.dumps(item):
            reasoning_found = True
            break
        if "reasoning_content" in item and "langkah2" in str(item.get("reasoning_content", "")):
            reasoning_found = True
            break
    assert reasoning_found, f"thinking content lost in Responses round-trip: {resp_items}"


# ---------------------------------------------------------------------------
# K3 - cache_read_input_tokens emitted from cached_tokens.
# ---------------------------------------------------------------------------


def test_cache_read_emitted_chat_sse():
    """Final chat chunk with ``usage.prompt_tokens_details.cached_tokens`` must
    surface ``cache_read_input_tokens > 0`` in an emitted event payload."""
    chunks = [
        {"choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"content": "hello"}}]},
        {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "prompt_tokens_details": {"cached_tokens": 50},
            },
        },
    ]
    events = _collect_chat_sse(chunks)

    cache_reads = [
        payload["usage"]["cache_read_input_tokens"]
        for _, payload in events
        if isinstance(payload, dict)
        and payload.get("usage", {}).get("cache_read_input_tokens", 0) > 0
    ]
    assert cache_reads, f"no cache_read_input_tokens > 0 in {events}"
    assert all(v > 0 for v in cache_reads)


def test_cache_read_emitted_nonstream_chat():
    """Non-stream chat completion with cached_tokens=50 must map to
    usage.cache_read_input_tokens == 50."""
    body = {
        "id": "chatcmpl_1",
        "object": "chat.completion",
        "model": "deepseek-chat",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 5,
            "total_tokens": 105,
            "prompt_tokens_details": {"cached_tokens": 50},
        },
    }
    result = cp.transform_openai_chat_to_anthropic_json(body)
    assert result["usage"]["cache_read_input_tokens"] == 50


def test_cache_read_emitted_nonstream_responses():
    """Non-stream Responses completion with input_tokens_details.cached_tokens=50
    must map to usage.cache_read_input_tokens == 50."""
    body = {
        "id": "resp_1",
        "object": "response",
        "model": "deepseek-reasoner",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi"}],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 5,
            "total_tokens": 105,
            "input_tokens_details": {"cached_tokens": 50},
        },
    }
    result = cp.transform_openai_responses_to_anthropic_json(body)
    assert result["usage"]["cache_read_input_tokens"] == 50
