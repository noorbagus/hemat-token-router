"""End-to-end tests for the csmart local LLM proxy.

Covers the full request path through the FastAPI app (``cp.app``) for the
Anthropic Messages API <-> OpenAI Responses API translation:

    POST /v1/messages (Anthropic shape)
      -> detect OpenAI model -> transform to Responses API payload
      -> mock upstream (httpx.MockTransport) returns OpenAI Responses SSE/JSON
      -> transform back to Anthropic Messages SSE/JSON
      -> structured JSONL logging into cp.LOG_DIR

All tests are hermetic (``pytest -m "not live"``) — no network. The upstream
transport is mocked via ``httpx.MockTransport`` injected into ``cp._UPSTREAM_TRANSPORT``.
"""
import json
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import httpx
import pytest

# Add parent directory to path so we can import csmart_proxy
sys.path.insert(0, str(Path(__file__).parent.parent))
import csmart_proxy as cp


# -----------------------------------------------------------------------------
# Fixtures - same hermetic pattern as test_csmart_proxy_openai.py
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset all global state between tests for hermeticity."""
    monkeypatch.setattr(cp, "DB_PATH", str(tmp_path / "csmart_state.db"))
    monkeypatch.setattr(cp, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(cp, "UPSTREAM_API_KEY", "test-key-never-leaked")
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-key-never-leaked")
    monkeypatch.setattr(cp, "_UPSTREAM_TRANSPORT", None)
    monkeypatch.setattr(cp.vault, "mem_cache", {})
    monkeypatch.setattr(cp.vault, "reverse_cache", {})
    monkeypatch.setattr(cp, "_session_model", {})
    monkeypatch.setattr(cp, "_prefix_snapshot", None)
    monkeypatch.setattr(cp, "_active_model", cp.FLASH_MODEL)
    cp.init_db()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _responses_sse_body(events: List[Tuple[str, dict]]) -> bytes:
    """Build an OpenAI Responses SSE body with ``event:`` + ``data:`` lines.

    The Responses transform keys on the SSE ``event:`` line (not the ``type``
    field inside the JSON payload), so the mock upstream MUST emit ``event:``
    prefixes. Format:
        event: response.created
        data: {"type": "response.created", ...}

        event: response.output_text.delta
        data: {...}

        ...
    """
    lines: List[str] = []
    for event_name, payload in events:
        lines.append(f"event: {event_name}")
        lines.append(f"data: {json.dumps(payload)}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _mock_upstream(handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Install a mock transport for the upstream."""
    cp._UPSTREAM_TRANSPORT = httpx.MockTransport(handler)


def _sse_text_response(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


def _parse_anthropic_sse(text: str) -> List[Tuple[str, dict]]:
    """Parse an Anthropic Messages SSE stream into ``(event_name, data)`` tuples."""
    events: List[Tuple[str, dict]] = []
    current_event: str = ""
    data_lines: List[str] = []
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: "):
            data_lines.append(line[len("data: "):])
        elif line == "":
            if data_lines:
                events.append((current_event, json.loads("".join(data_lines))))
                current_event = ""
                data_lines = []
    if data_lines:
        events.append((current_event, json.loads("".join(data_lines))))
    return events


def _read_log_event_names() -> List[str]:
    """Read every JSONL line in cp.LOG_DIR and return the event names, in order."""
    log_dir = Path(cp.LOG_DIR)
    names: List[str] = []
    if not log_dir.exists():
        return names
    for f in sorted(log_dir.glob("session_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                names.append(json.loads(line)["event"])
            except (json.JSONDecodeError, KeyError):
                continue
    return names


def _read_log_raw_lines() -> List[str]:
    """Read every raw JSONL line in cp.LOG_DIR (for secret-leak scans)."""
    log_dir = Path(cp.LOG_DIR)
    lines: List[str] = []
    if not log_dir.exists():
        return lines
    for f in sorted(log_dir.glob("session_*.jsonl")):
        lines.extend(f.read_text(encoding="utf-8").splitlines())
    return lines


async def _post(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    session: str = "test-session",
) -> httpx.Response:
    return await client.post(
        "/v1/messages",
        json=payload,
        headers={"x-csmart-session": session},
    )


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=cp.app), base_url="http://test")


# -----------------------------------------------------------------------------
# 1. Streaming text full sequence
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_responses_stream_text_full_sequence():
    """created -> output_text.delta x2 -> completed must yield a spec-compliant
    Anthropic SSE stream with full message_start / message_delta shape."""
    events = [
        ("response.created", {"type": "response.created", "response": {"id": "resp_1", "model": "muse"}}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "READY"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": " SET"}),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 5, "output_tokens": 7},
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "READY SET"}]}],
                },
            },
        ),
    ]
    _mock_upstream(lambda req: _sse_text_response(_responses_sse_body(events)))

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": "Say ready"}],
        "max_tokens": 100,
    }

    async with _make_client() as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    parsed = _parse_anthropic_sse(resp.text)
    event_types = [t for t, _ in parsed]
    assert event_types == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]

    # X-1 fix: message_start carries id/model/usage.
    ms_data = parsed[0][1]
    assert ms_data["type"] == "message_start"
    assert ms_data["message"]["id"].startswith("msg_")
    assert ms_data["message"]["model"] == "muse"
    assert "usage" in ms_data["message"]

    # X-2 fix: message_delta carries stop_reason + final usage.
    md_data = parsed[-2][1]
    assert md_data["type"] == "message_delta"
    assert md_data["delta"]["stop_reason"] == "end_turn"
    assert md_data["usage"]["output_tokens"] == 7

    # Reconstructed text == the two deltas concatenated.
    text = "".join(
        d["delta"]["text"]
        for _, d in parsed
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert text == "READY SET"


# -----------------------------------------------------------------------------
# 2. Streaming tool-use round-trip
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_responses_stream_tool_use_roundtrip():
    """A tool_use in the assistant turn + tool_result in the next user turn must
    flatten to Responses ``function_call`` / ``function_call_output`` input items
    (never chat-completions ``tool_calls``), and the streamed response must carry
    the tool_use block back to the client."""
    captured: List[dict[str, Any]] = []
    events = [
        ("response.created", {"type": "response.created", "response": {"id": "resp_2", "model": "muse"}}),
        (
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "id": "fc_123",
                    "type": "function_call",
                    "call_id": "call_abc",
                    "name": "Bash",
                    "arguments": "",
                    "status": "in_progress",
                },
            },
        ),
        ("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta", "delta": '{"command": '}),
        ("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta", "delta": '"ls"}'}),
        (
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc_123",
                    "type": "function_call",
                    "call_id": "call_abc",
                    "name": "Bash",
                    "arguments": '{"command": "ls"}',
                    "status": "completed",
                },
            },
        ),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 8, "output_tokens": 12},
                    "output": [{"type": "function_call", "call_id": "call_abc", "name": "Bash", "arguments": '{"command": "ls"}'}],
                },
            },
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode("utf-8")))
        return _sse_text_response(_responses_sse_body(events))

    _mock_upstream(handler)

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "list files"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Saya cek."},
                    {"type": "tool_use", "id": "call_abc", "name": "Bash", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "call_abc", "content": "file1\nfile2"}],
            },
        ],
    }

    async with _make_client() as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    parsed = _parse_anthropic_sse(resp.text)

    # tool_use content_block_start: id/name preserved.
    cbs = [d for _, d in parsed if isinstance(d, dict) and d.get("type") == "content_block_start"]
    assert cbs, "no content_block_start found"
    tool_block = cbs[0]["content_block"]
    assert tool_block["type"] == "tool_use"
    assert tool_block["id"] == "call_abc"
    assert tool_block["name"] == "Bash"

    # partial_json deltas concatenate to the full args JSON.
    json_frag = "".join(
        d["delta"]["partial_json"]
        for _, d in parsed
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert json_frag == '{"command": "ls"}'

    # message_delta stop_reason == tool_use.
    md = [d for _, d in parsed if isinstance(d, dict) and d.get("type") == "message_delta"]
    assert md, "no message_delta found"
    assert md[0]["delta"]["stop_reason"] == "tool_use"

    # Upstream request body: input flattens tool_use -> function_call and
    # tool_result -> function_call_output; no chat-completions tool_calls.
    assert len(captured) == 1
    up_body = captured[0]
    inp = up_body["input"]
    assert isinstance(inp, list)
    assert not any("tool_calls" in item for item in inp)
    fc = [i for i in inp if i.get("type") == "function_call"]
    assert len(fc) == 1
    assert fc[0]["call_id"] == "call_abc"
    assert fc[0]["name"] == "Bash"
    assert fc[0]["arguments"] == "{}"
    fco = [i for i in inp if i.get("type") == "function_call_output"]
    assert len(fco) == 1
    assert fco[0]["call_id"] == "call_abc"
    assert fco[0]["output"] == "file1\nfile2"


# -----------------------------------------------------------------------------
# 3. Non-streaming JSON response
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_responses_non_streaming_json():
    """stream:false must return an Anthropic Messages JSON document (NOT an
    event-stream), with text + tool_use blocks and usage."""
    upstream_json = {
        "id": "resp_1",
        "model": "muse",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "hi"}]},
            {"type": "function_call", "call_id": "c1", "name": "Bash", "arguments": '{"cmd": "ls"}'},
        ],
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=upstream_json)

    _mock_upstream(handler)

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": "run ls"}],
        "max_tokens": 100,
        "stream": False,
    }

    async with _make_client() as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    content = body["content"]
    text_blocks = [b for b in content if b.get("type") == "text"]
    tool_blocks = [b for b in content if b.get("type") == "tool_use"]
    assert text_blocks, "no text block in non-streaming response"
    assert text_blocks[0]["text"] == "hi"
    assert tool_blocks, "no tool_use block in non-streaming response"
    assert tool_blocks[0]["name"] == "Bash"
    assert tool_blocks[0]["id"] == "c1"
    assert tool_blocks[0]["input"] == {"cmd": "ls"}
    assert body["usage"] == {"input_tokens": 3, "output_tokens": 4}


# -----------------------------------------------------------------------------
# 4. Upstream 4xx must surface, not become a silent empty 200
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_upstream_400_surfaces_error():
    """A 4xx from upstream must reach the client as an HTTP error or an SSE
    error event — never a silent empty HTTP 200 stream."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error": {"message": "bad"}}')

    _mock_upstream(handler)

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": "halo"}],
        "max_tokens": 100,
    }

    async with _make_client() as client:
        resp = await _post(client, payload)

    assert resp.status_code >= 400 or "event: error" in resp.text
    if resp.status_code == 200:
        assert "upstream_error" in resp.text
        assert "message_stop" not in resp.text


# -----------------------------------------------------------------------------
# 5. Structured logging emits the expected events
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_structured_logging_emits_events():
    """The pipeline must write OPENAI_DETECTION / INBOUND_REQUEST /
    OPENAI_REQUEST_TRANSFORM / OPENAI_RESPONSES_SSE_TRANSFORM for a streaming
    request, and NON_STREAMING_REQUEST / NON_STREAMING_RESPONSE for stream:false."""
    sse_events = [
        ("response.created", {"type": "response.created", "response": {"id": "resp_1", "model": "muse"}}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "hi"}),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {"status": "completed", "usage": {"input_tokens": 1, "output_tokens": 2}, "output": []},
            },
        ),
    ]
    _mock_upstream(lambda req: _sse_text_response(_responses_sse_body(sse_events)))

    stream_payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 100,
    }
    async with _make_client() as client:
        resp = await _post(client, stream_payload)
    assert resp.status_code == 200
    assert resp.text  # consume the stream so the transform's _log calls fire

    non_stream_json = {
        "id": "resp_1",
        "model": "muse",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "hi"}]}],
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    _mock_upstream(lambda req: httpx.Response(200, json=non_stream_json))

    non_stream_payload = dict(stream_payload, stream=False)
    async with _make_client() as client:
        resp2 = await _post(client, non_stream_payload)
    assert resp2.status_code == 200
    assert resp2.json()["type"] == "message"

    events_logged = _read_log_event_names()
    for expected in [
        "OPENAI_DETECTION",
        "INBOUND_REQUEST",
        "OPENAI_REQUEST_TRANSFORM",
        "OPENAI_RESPONSES_SSE_TRANSFORM",
        "NON_STREAMING_REQUEST",
        "NON_STREAMING_RESPONSE",
    ]:
        assert expected in events_logged, f"missing {expected} in events_logged={events_logged}"


# -----------------------------------------------------------------------------
# 6. DLP masking + logging redaction end-to-end
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_logging_and_upstream_redact_secrets():
    """A sk-ant secret in a user message must be DLP-masked upstream
    (__CSMART_SEC_* marker, never the raw value) and never written to logs."""
    secret = "sk-ant-test1234567890123456789012345678"
    captured: List[str] = []
    sse_events = [
        ("response.created", {"type": "response.created", "response": {"id": "resp_1", "model": "muse"}}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "ok"}),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {"status": "completed", "usage": {"input_tokens": 1, "output_tokens": 1}, "output": []},
            },
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content.decode("utf-8"))
        return _sse_text_response(_responses_sse_body(sse_events))

    _mock_upstream(handler)

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": f"config: {secret}"}],
        "max_tokens": 100,
    }

    async with _make_client() as client:
        resp = await _post(client, payload)
    assert resp.status_code == 200
    assert resp.text  # consume the stream

    # Upstream body: masked, never raw.
    assert len(captured) == 1
    assert secret not in captured[0], "raw secret leaked to upstream"
    assert "__CSMART_SEC_" in captured[0], "DLP mask marker not present upstream"

    # Logs: no raw secret anywhere.
    raw_lines = _read_log_raw_lines()
    assert raw_lines, "no log lines written"
    for line in raw_lines:
        assert secret not in line, f"raw secret leaked into logs: {line[:200]}"


# -----------------------------------------------------------------------------
# 7. Tool args delivered via function_call_arguments.done only (C1 gap)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_gap_tool_args_via_done_xfail():
    """A provider emitting ONLY function_call_arguments.done (no .delta events)
    must still deliver the full tool args to the client. Was an XFAIL gap
    (issue #4, C1); now PASSes since the .done handler was added."""
    events = [
        ("response.created", {"type": "response.created", "response": {"id": "resp_7", "model": "muse"}}),
        (
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "id": "fc_7",
                    "type": "function_call",
                    "call_id": "call_7",
                    "name": "Bash",
                    "arguments": "",
                    "status": "in_progress",
                },
            },
        ),
        ("response.function_call_arguments.done", {"type": "response.function_call_arguments.done", "delta": '{"command": "ls"}'}),
        (
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc_7",
                    "type": "function_call",
                    "call_id": "call_7",
                    "name": "Bash",
                    "arguments": '{"command": "ls"}',
                    "status": "completed",
                },
            },
        ),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 2, "output_tokens": 3},
                    "output": [{"type": "function_call", "call_id": "call_7", "name": "Bash"}],
                },
            },
        ),
    ]
    _mock_upstream(lambda req: _sse_text_response(_responses_sse_body(events)))

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": "ls"}],
        "max_tokens": 100,
    }

    async with _make_client() as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    parsed = _parse_anthropic_sse(resp.text)
    json_frag = "".join(
        d["delta"]["partial_json"]
        for _, d in parsed
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert json_frag == '{"command": "ls"}'
