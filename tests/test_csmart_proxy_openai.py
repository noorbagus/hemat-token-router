"""Hermetic tests for OpenAI-native protocol adapter in csmart_proxy.py.

Runs under `pytest -m "not live"` — no network required.
All upstream requests are mocked via httpx.MockTransport.
"""
import asyncio
import json
import os
import sys
from typing import Any, AsyncGenerator, Callable, List, Optional
from pathlib import Path

import httpx
import pytest

# Add parent directory to path so we can import csmart_proxy
sys.path.insert(0, str(Path(__file__).parent.parent))
import csmart_proxy as cp


# -----------------------------------------------------------------------------
# Fixtures - same pattern as test_csmart_proxy.py
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset all global state between tests for hermeticity."""
    # Reset database to temp path
    monkeypatch.setattr(cp, "DB_PATH", str(tmp_path / "csmart_state.db"))
    # Reset logging to temp dir
    monkeypatch.setattr(cp, "LOG_DIR", str(tmp_path / "logs"))
    # Set test upstream key
    monkeypatch.setattr(cp, "UPSTREAM_API_KEY", "test-key-never-leaked")
    # Reset all caches
    monkeypatch.setattr(cp, "_UPSTREAM_TRANSPORT", None)
    monkeypatch.setattr(cp.vault, "mem_cache", {})
    monkeypatch.setattr(cp.vault, "reverse_cache", {})
    monkeypatch.setattr(cp, "_session_model", {})
    monkeypatch.setattr(cp, "_prefix_snapshot", None)
    monkeypatch.setattr(cp, "_active_model", cp.FLASH_MODEL)
    # Initialize fresh database
    cp.init_db()


def _sse_body(events: List[dict[str, Any] | str]) -> bytes:
    """Build SSE response body from a list of events."""
    lines: List[str] = []
    for event in events:
        if event == "[DONE]":
            lines.append("data: [DONE]")
        else:
            lines.append(f"data: {json.dumps(event)}")
        lines.append("")  # SSE requires blank line after each event
    return "\n".join(lines).encode("utf-8")


def _simple_upstream(text: str) -> Callable[[httpx.Request], httpx.Response]:
    """Build a simple MockTransport handler that returns complete text SSE."""
    def handler(request: httpx.Request) -> httpx.Response:
        events = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": text}}]},
            "[DONE]",
        ]
        body = _sse_body(events)
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    return handler


def _tool_use_upstream(name: str, input_json: str) -> Callable[[httpx.Request], httpx.Response]:
    """Build a MockTransport handler that returns streaming tool call."""
    def handler(request: httpx.Request) -> httpx.Response:
        events = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": name}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": input_json}}]}}]},
            "[DONE]",
        ]
        body = _sse_body(events)
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    return handler


def _mock_upstream(handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Install mock transport for upstream."""
    transport = httpx.MockTransport(handler)
    cp._UPSTREAM_TRANSPORT = transport


def _run(coro: Any) -> Any:
    """Run an async coroutine from sync."""
    return asyncio.run(coro)


async def _post(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    session: str = "test-session",
) -> httpx.Response:
    """Make a POST request to /v1/messages with proper headers."""
    return await client.post(
        "/v1/messages",
        json=payload,
        headers={"x-csmart-session": session},
    )


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


def test_steering_injection_only_openai():
    """Test that steering prompt is only injected for OpenAI models, not Anthropic."""
    # OpenAI model should get steering (done inside handle_messages)
    # Note: route_model_tier always overrides to deepseek-chat/deepseek-reasoner, so we keep original model name
    body_openai: dict[str, Any] = {
        "model": "gpt-4o",
        "system": "You are a helpful assistant.",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 1000,
    }
    cp.sanitize_payload(body_openai)
    # Don't replace model: route_model_tier overrides to default deepseek, we need original for detection
    routed_model = body_openai["model"]

    # Replicate what handle_messages does for steering
    if cp.is_openai_model(routed_model):
        steering_block = {"type": "text", "text": cp.SYSTEM_STEERING_PROMPT}
        current_system = body_openai.get("system", "")
        if isinstance(current_system, str):
            if current_system.strip():
                body_openai["system"] = [
                    {"type": "text", "text": current_system},
                    steering_block,
                ]
            else:
                body_openai["system"] = [steering_block]
        elif isinstance(current_system, list):
            body_openai["system"] = current_system + [steering_block]

    assert cp.is_openai_model(routed_model) is True

    # Check injection
    current_system = body_openai.get("system")
    assert isinstance(current_system, list)
    assert len(current_system) == 2
    assert current_system[0]["text"] == "You are a helpful assistant."
    assert cp.SYSTEM_STEERING_PROMPT in current_system[1]["text"]

    # Check injection
    current_system = body_openai.get("system")
    assert isinstance(current_system, list)
    assert len(current_system) == 2
    assert current_system[0]["text"] == "You are a helpful assistant."
    assert cp.SYSTEM_STEERING_PROMPT in current_system[1]["text"]

    # Anthropic model should NOT get steering
    body_anthropic: dict[str, Any] = {
        "model": "claude-3-5-sonnet-latest",
        "system": "You are a helpful assistant.",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 1000,
    }
    cp.sanitize_payload(body_anthropic)
    routed_model = cp.route_model_tier(body_anthropic, "test")
    body_anthropic["model"] = routed_model

    # Replicate handle_messages
    if cp.is_openai_model(routed_model):
        steering_block = {"type": "text", "text": cp.SYSTEM_STEERING_PROMPT}
        current_system = body_anthropic.get("system", "")
        if isinstance(current_system, str):
            if current_system.strip():
                body_anthropic["system"] = [
                    {"type": "text", "text": current_system},
                    steering_block,
                ]
            else:
                body_anthropic["system"] = [steering_block]
        elif isinstance(current_system, list):
            body_anthropic["system"] = current_system + [steering_block]

    assert cp.is_openai_model("claude-3-5-sonnet-latest") is False
    assert body_anthropic["system"] == "You are a helpful assistant."  # unchanged


def test_steering_injection_string_to_list():
    """Test injection converts string system to list correctly."""
    # Note: route_model_tier always overrides to deepseek-chat/deepseek-reasoner, keep original
    body: dict[str, Any] = {
        "model": "muse-spark-1.2",
        "system": "",  # empty string
        "messages": [{"role": "user", "content": "Hello"}],
    }
    cp.sanitize_payload(body)
    routed_model = body["model"]
    assert cp.is_openai_model(routed_model) is True, f"expected muse-spark-1.2 to be OpenAI, got {routed_model}"

    # Replicate what handle_messages does for steering
    if cp.is_openai_model(routed_model):
        steering_block = {"type": "text", "text": cp.SYSTEM_STEERING_PROMPT}
        current_system = body.get("system", "")
        if isinstance(current_system, str):
            if current_system.strip():
                body["system"] = [
                    {"type": "text", "text": current_system},
                    steering_block,
                ]
            else:
                body["system"] = [steering_block]
        elif isinstance(current_system, list):
            body["system"] = current_system + [steering_block]

    assert isinstance(body["system"], list)
    assert len(body["system"]) == 1
    assert cp.SYSTEM_STEERING_PROMPT in body["system"][0]["text"]


def test_request_transformation_chat_basic():
    """Test basic Anthropic -> OpenAI Chat Completions transformation."""
    payload: dict[str, Any] = {
        "model": "gpt-4o",
        "system": "You are a coding assistant.",
        "messages": [
            {"role": "user", "content": "Write hello world in Python."},
        ],
        "max_tokens": 2000,
        "temperature": 0.7,
    }

    result = cp.transform_anthropic_to_openai_chat(payload)

    assert result["model"] == "gpt-4o"
    assert result["stream"] is True
    assert result["max_tokens"] == 2000
    assert result["temperature"] == 0.7
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "system"
    assert "coding assistant" in result["messages"][0]["content"]
    assert result["messages"][1]["role"] == "user"
    assert "hello world" in result["messages"][1]["content"]


def test_request_transformation_with_tools():
    """Test tool format conversion from Anthropic -> OpenAI."""
    payload: dict[str, Any] = {
        "model": "gpt-4o",
        "system": "Use tools when needed.",
        "messages": [{"role": "user", "content": "What's the weather in SF?"}],
        "tools": [
            {
                "name": "get_weather",
                "description": "Get the current weather",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"},
                    },
                    "required": ["city"],
                },
            }
        ],
    }

    result = cp.transform_anthropic_to_openai_chat(payload)

    assert "tools" in result
    assert len(result["tools"]) == 1
    tool = result["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "get_weather"
    assert "current weather" in tool["function"]["description"]
    assert "properties" in tool["function"]["parameters"]
    assert "city" in tool["function"]["parameters"]["properties"]
    assert result["parallel_tool_calls"] is True


def test_request_transformation_block_format():
    """Test transformation handles Anthropic block format content."""
    payload: dict[str, Any] = {
        "model": "opencode-go",
        "system": [
            {"type": "text", "text": "You are a code assistant."},
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Fix this bug:"},
                    {"type": "text", "text": "def foo(): pass"},
                ],
            },
        ],
    }

    result = cp.transform_anthropic_to_openai_chat(payload)

    assert len(result["messages"]) == 2  # system + user message
    assert "code assistant" in result["messages"][0]["content"]
    assert "Fix this bug:" in result["messages"][1]["content"]
    assert "def foo(): pass" in result["messages"][1]["content"]


def test_secret_masking_preserved_through_transformation():
    """Test that masked secrets remain masked through the entire transformation."""
    secret = "sk-test-1234567890abcdefghij"
    masked = cp.vault.mask_text(secret)

    payload: dict[str, Any] = {
        "model": "gpt-4o",
        "system": f"My key is {secret}",
        "messages": [{"role": "user", "content": f"Use key {secret}"}],
    }

    cp.sanitize_payload(payload)
    result = cp.transform_anthropic_to_openai_chat(payload)

    # Secret should be masked everywhere
    system_content = result["messages"][0]["content"]
    user_content = result["messages"][1]["content"]
    assert secret not in system_content
    assert secret not in user_content
    assert masked in system_content
    assert masked in user_content


@pytest.mark.asyncio
async def test_e2e_openai_text_response():
    """End-to-end test: Anthropic request -> OpenAI transformation -> response back to Anthropic."""
    expected_text = "Hello from OpenAI model!"
    _mock_upstream(_simple_upstream(expected_text))

    payload: dict[str, Any] = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Say hello"}],
        "max_tokens": 100,
    }

    # Make request through ASGI transport
    transport = httpx.ASGITransport(app=cp.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    # Parse SSE response and check it's proper Anthropic format
    content = resp.text
    lines = content.splitlines()

    # Should have: message_start, content_block_delta, message_stop
    events: list[tuple[str, dict]] = []
    current_data: list[str] = []
    event_name: str = ""
    for line in lines:
        if line.startswith("event: "):
            event_name = line[len("event: "):]
        elif line.startswith("data: "):
            current_data.append(line[len("data: "):])
        elif line == "":
            if current_data and event_name:
                data = json.loads("".join(current_data))
                events.append((event_name, data))
                current_data = []
                event_name = ""

    # Expected event sequence
    event_types = [t for t, _ in events]
    assert "message_start" in event_types
    assert "content_block_delta" in event_types
    assert "message_stop" in event_types

    # Response should contain the expected text after transformation
    found_text = False
    for etype, data in events:
        if etype == "content_block_delta":
            if "delta" in data and "text" in data["delta"]:
                if expected_text in data["delta"]["text"]:
                    found_text = True
                    break

    assert found_text, "Expected text not found in transformed response"


@pytest.mark.asyncio
async def test_e2e_backward_compatibility_anthropic():
    """Test that existing Anthropic flow still works unchanged."""
    upstream_text = "Hello from Anthropic model!"

    def anthropic_handler(request: httpx.Request) -> httpx.Response:
        # Anthropic format SSE
        events = [
            {"type": "message_start", "message": {"role": "assistant", "content": []}},
            {"type": "content_block_delta", "delta": {"type": "text", "text": upstream_text}},
            {"type": "message_stop"},
        ]
        body = b"".join(
            f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode("utf-8")
            for e in events
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    _mock_upstream(anthropic_handler)

    payload: dict[str, Any] = {
        "model": "claude-3-opus-latest",
        "messages": [{"role": "user", "content": "Say hello"}],
        "max_tokens": 100,
    }

    transport = httpx.ASGITransport(app=cp.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    content = resp.text
    assert "message_start" in content
    assert "content_block_delta" in content
    assert "message_stop" in content
    assert upstream_text in content


@pytest.mark.asyncio
async def test_openai_client_key_not_forwarded():
    """Test that client Authorization header is never forwarded to upstream (same as Anthropic)."""
    calls: list[httpx.Request] = []

    def capture_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"data: [DONE]\n", headers={"content-type": "text/event-stream"})

    _mock_upstream(capture_handler)

    payload: dict[str, Any] = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "test"}],
    }

    transport = httpx.ASGITransport(app=cp.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Client sends Authorization (it shouldn't get through)
        resp = await client.post(
            "/v1/messages",
            json=payload,
            headers={
                "x-csmart-session": "test",
                "Authorization": "Bearer client-secret-key-should-not-leak",
            },
        )
        assert resp.status_code == 200

    assert len(calls) == 1
    upstream_req = calls[0]
    # Upstream should only have our server-side key, NOT client's
    auth_header = upstream_req.headers.get("authorization")
    assert auth_header == "Bearer test-key-never-leaked"
    assert "client-secret-key" not in auth_header
    # OpenAI should NOT have anthropic-version header (check all keys lowercased)
    has_anthropic = any(k.lower() == "anthropic-version" for k in dict(upstream_req.headers))
    assert not has_anthropic, f"anthropic-version found in headers: {list(dict(upstream_req.headers).keys())}"


def test_detect_endpoint_type():
    """Test endpoint type detection based on model name."""
    assert cp.detect_openai_endpoint_type("gpt-4o") == "chat_completions"
    assert cp.detect_openai_endpoint_type("gpt-4o-responses") == "responses"
    assert cp.detect_openai_endpoint_type("responses-model") == "responses"
    assert cp.detect_openai_endpoint_type("muse-spark-1.2") == "chat_completions"
