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
    original_model = body_anthropic["model"]  # claude-3-5-sonnet-latest — gate pakai model asli (L2331)
    routed_model = cp.route_model_tier(body_anthropic, "test")
    body_anthropic["model"] = routed_model

    # Replicate handle_messages: steering gate pakai ORIGINAL model, bukan routed (deepseek-chat kini is_openai)
    if cp.is_openai_model(original_model):
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
async def test_e2e_anthropic_native_passthrough(monkeypatch):
    """minimax/qwen3 are Anthropic-native on OpenCode Go /messages: the client
    model name must be preserved (NOT rewritten to deepseek-chat), routed to
    ``{OPENAI_BASE_URL}/messages`` with the OpenCode key + x-api-key, and the
    Anthropic SSE streamed back verbatim (no protocol transform)."""
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-opencode-key-never-leaked")
    calls: list[httpx.Request] = []
    upstream_text = "Hello from minimax (Anthropic native)!"

    def native_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
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

    _mock_upstream(native_handler)

    payload: dict[str, Any] = {
        "model": "opencode-go/minimax-m3",
        "messages": [{"role": "user", "content": "Say hello"}],
        "max_tokens": 100,
    }

    transport = httpx.ASGITransport(app=cp.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    content = resp.text
    assert "message_start" in content and "message_stop" in content
    assert upstream_text in content

    assert len(calls) == 1
    upstream_req = calls[0]
    # Route to OpenCode Go Anthropic /messages — NOT the DeepSeek upstream.
    assert upstream_req.url.path == f"{cp.OPENAI_MESSAGES_PATH}".lstrip("/") or \
        upstream_req.url.path.endswith(cp.OPENAI_MESSAGES_PATH)
    # Model preserved verbatim (stripped of opencode-go/ prefix), NOT deepseek-chat.
    body_model = json.loads(upstream_req.content).get("model")
    assert body_model == "minimax-m3", f"model not preserved: {body_model}"
    # Anthropic endpoints need x-api-key (K7), using the OpenCode key.
    assert upstream_req.headers.get("x-api-key") == "test-opencode-key-never-leaked"
    assert upstream_req.headers.get("authorization") == "Bearer test-opencode-key-never-leaked"


@pytest.mark.asyncio
async def test_openai_client_key_not_forwarded(monkeypatch):
    """Test that client Authorization header is never forwarded to upstream (same as Anthropic)."""
    # Pin server-side OpenAI key so the test is hermetic (no real key in assertions)
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-key-never-leaked")
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
    # OpenCode models (muse/opencode) use the Responses API
    assert cp.detect_openai_endpoint_type("muse-spark-1.2") == "responses"
    assert cp.detect_openai_endpoint_type("opencode-go/muse-spark-1.2-contributor") == "responses"
    # OpenCode Go table: grok/gpt-5.6 on /responses
    assert cp.detect_openai_endpoint_type("grok-4.6") == "responses"
    assert cp.detect_openai_endpoint_type("opencode-go/gpt-5.6-luna") == "responses"
    # OpenCode Go table: glm/kimi/longcat/mimo/hy on /chat/completions
    assert cp.detect_openai_endpoint_type("glm-5.3-flash") == "chat_completions"
    assert cp.detect_openai_endpoint_type("kimi-k2.5") == "chat_completions"
    assert cp.detect_openai_endpoint_type("deepseek-v4-flash") == "chat_completions"


def test_anthropic_native_detection():
    """minimax/qwen3 are Anthropic-native (OpenCode Go /messages) — NOT OpenAI,
    so they must not be protocol-transformed and must not take the FLASH rewrite.
    NB: ``opencode-go/minimax-m3`` matches BOTH ``opencode-`` (OpenAI pattern)
    and ``minimax-`` (native) — handle_messages resolves via precedence (native
    wins). This is the effective decision, not the raw ``is_openai_model``."""
    for model in ("minimax-m3", "minimax-m2", "opencode-go/minimax-m3", "qwen3.8-flash", "qwen3-8b"):
        assert cp.is_anthropic_native_model(model), f"{model} should be anthropic-native"
        effective_openai = (not cp.is_anthropic_native_model(model)) and cp.is_openai_model(model)
        assert effective_openai is False, f"{model} must not be treated as OpenAI"
    # claude models are neither OpenAI nor OpenCode-native
    assert cp.is_anthropic_native_model("claude-3-5-sonnet-latest") is False
    assert cp.is_anthropic_native_model("muse-spark-1.2-contributor") is False


def test_openai_model_alias():
    """DeepSeek's real API ids aren't served by OpenCode Go — they must map to
    OpenCode Go's v4 ids on the OpenAI path so the documented FLASH/FLAGSHIP
    defaults (deepseek-chat / deepseek-reasoner) keep working."""
    assert cp.OPENAI_MODEL_ALIASES["deepseek-chat"] == "deepseek-v4-flash"
    assert cp.OPENAI_MODEL_ALIASES["deepseek-reasoner"] == "deepseek-v4-pro"
    # Alias applies to the *cleaned* model (after opencode-go/ prefix strip).
    for raw, expected in [
        ("deepseek-chat", "deepseek-v4-flash"),
        ("opencode-go/deepseek-chat", "deepseek-v4-flash"),
        ("deepseek-reasoner", "deepseek-v4-pro"),
    ]:
        cleaned = cp.clean_openai_model_name(raw)
        assert cp.OPENAI_MODEL_ALIASES.get(cleaned, cleaned) == expected
    # Non-aliased models pass through untouched.
    assert cp.OPENAI_MODEL_ALIASES.get("glm-5.3-flash", "glm-5.3-flash") == "glm-5.3-flash"


def test_full_opencode_go_model_table_coverage():
    """Every model id in docs/endpoints-opencode.md must route to the endpoint
    its row declares: /responses, /chat/completions, or Anthropic-native /messages.
    Each id is checked BOTH bare and with the ``opencode-go/`` org prefix — the
    prefix must never change the endpoint (regression: opencode-go/hy3 was
    hijacked to /responses by the old "opencode-" pattern)."""
    responses_models = ["grok-4.6", "gpt-5.6-luna", "muse-spark-1.2-contributor"]
    chat_models = [
        "glm-5.3-flash", "glm-5.3", "glm-5.2", "glm-5.1",
        "kimi-k3", "kimi-k2.7-code", "kimi-k2.6",
        "longcat-2.0",
        "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp",
        "mimo-v2.5", "mimo-v2.5-pro",
        "hy4-preview", "hy3",  # hy3 has no trailing dash — must still match
    ]
    native_models = [
        "minimax-m3", "minimax-m2.7", "minimax-m2.5",
        "qwen3.8-max", "qwen3.8-flash", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
    ]

    def route(model: str) -> str:
        is_native = cp.is_anthropic_native_model(model)
        is_openai = (not is_native) and cp.is_openai_model(model)
        if is_native:
            return "native"
        if is_openai:
            return cp.detect_openai_endpoint_type(model)
        return "unrouted"

    expected = {
        "responses": responses_models,
        "chat_completions": chat_models,
        "native": native_models,
    }
    for target, models in expected.items():
        for m in models:
            for variant in (m, f"opencode-go/{m}"):
                assert route(variant) == target, \
                    f"{variant} -> {route(variant)} (expected {target})"
    assert len(responses_models) + len(chat_models) + len(native_models) == 26


# -----------------------------------------------------------------------------
# Responses API SSE transform (REAL wire format: delta is a string)
# -----------------------------------------------------------------------------


def _collect_sse(events: list[tuple[str | None, dict[str, Any]]]) -> list[tuple[str | None, dict[str, Any]]]:
    """Consume the async transform generator synchronously."""
    async def _run() -> list[tuple[str | None, dict[str, Any]]]:
        async def gen():
            for e in events:
                yield e
        out: list[tuple[str | None, dict[str, Any]]] = []
        async for item in cp.transform_openai_responses_sse_to_anthropic(gen()):
            out.append(item)
        return out
    return asyncio.run(_run())


def test_resolve_reasoning_effort():
    """Anthropic reasoning/thinking config -> Responses API effort (max clamped)."""
    # explicit effort passthrough
    assert cp._resolve_reasoning_effort({"reasoning": {"effort": "low"}}) == "low"
    assert cp._resolve_reasoning_effort({"reasoning": {"effort": "high"}}) == "high"
    # max is rejected by OpenCode gateway -> clamp to high
    assert cp._resolve_reasoning_effort({"reasoning": {"effort": "max"}}) == "high"
    # thinking blocks
    assert cp._resolve_reasoning_effort({"thinking": {"type": "enabled"}}) == "medium"
    # disabled thinking maps to None — upstream rejects the literal "off" string
    assert cp._resolve_reasoning_effort({"thinking": {"type": "disabled"}}) is None
    assert cp._resolve_reasoning_effort({"thinking": {"enabled": False}}) is None
    # unknown effort falls back to low
    assert cp._resolve_reasoning_effort({"reasoning": {"effort": "bogus"}}) == "low"
    # no signal + no env override -> None (provider default)
    assert cp._resolve_reasoning_effort({}) is None


def test_responses_transform_reasoning_passthrough(monkeypatch):
    """transform should carry reasoning.effort into the Responses payload."""
    monkeypatch.setenv("CSMART_REASONING_EFFORT", "")
    payload = {
        "model": "muse-spark-1.2",
        "messages": [{"role": "user", "content": "hi"}],
        "reasoning": {"effort": "max"},
    }
    result = cp.transform_anthropic_to_openai_responses(payload)
    assert result["reasoning"] == {"effort": "high"}


def test_responses_sse_transform_real_delta_string():
    """Real Responses API sends delta as STRING. Regression test for the
    AttributeError: 'str' object has no attribute 'get' crash."""
    raw_events: list[tuple[str | None, dict[str, Any]]] = [
        ("response.created", {"type": "response.created"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "READY"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": " SET"}),
        ("response.completed", {"type": "response.completed"}),
    ]
    result = _collect_sse(raw_events)

    event_types = [t for t, _ in result]
    assert event_types == ["message_start", "content_block_start", "content_block_delta", "content_block_delta", "content_block_stop", "message_delta", "message_stop"]

    # Collect all text fragments
    text = "".join(
        d["delta"]["text"]
        for _, d in result
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert text == "READY SET"


def test_responses_sse_transform_tool_use():
    """Responses API function_call: output_item.added -> content_block_start tool_use,
    function_call_arguments.delta -> input_json, output_item.done -> content_block_stop."""
    raw_events: list[tuple[str | None, dict[str, Any]]] = [
        ("response.created", {"type": "response.created"}),
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
        (
            "response.function_call_arguments.delta",
            {"type": "response.function_call_arguments.delta", "delta": '{"command": '},
        ),
        (
            "response.function_call_arguments.delta",
            {"type": "response.function_call_arguments.delta", "delta": '"ls"}'},
        ),
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
        ("response.completed", {"type": "response.completed"}),
    ]
    result = _collect_sse(raw_events)

    event_types = [t for t, _ in result]
    assert event_types == [
        "message_start",
        "content_block_start",   # tool_use
        "content_block_delta",   # input_json (partial)
        "content_block_delta",   # input_json (partial)
        "content_block_stop",    # tool_use done
        "message_delta",         # X-2: stop_reason + final usage
        "message_stop",
    ]

    # Find the tool_use content block start
    tool_block = next(d for _, d in result if isinstance(d, dict) and d.get("type") == "content_block_start")
    assert tool_block["content_block"]["type"] == "tool_use"
    assert tool_block["content_block"]["name"] == "Bash"
    assert tool_block["content_block"]["id"] == "call_abc"

    # Collect partial input_json fragments
    json_frag = "".join(
        d["delta"]["partial_json"]
        for _, d in result
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert json_frag == '{"command": "ls"}'


def test_responses_sse_transform_tool_args_done_only():
    """A provider that emits ONLY response.function_call_arguments.done (full
    args string in {\"delta\": ...}) with no prior .delta events must still
    deliver the tool_use arguments — not leave input as {}."""
    raw_events: list[tuple[str | None, dict[str, Any]]] = [
        ("response.created", {"type": "response.created"}),
        (
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "id": "fc_456",
                    "type": "function_call",
                    "call_id": "call_xyz",
                    "name": "Bash",
                    "arguments": "",
                    "status": "in_progress",
                },
            },
        ),
        (
            "response.function_call_arguments.done",
            {"type": "response.function_call_arguments.done", "delta": '{"command": "ls"}'},
        ),
        (
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc_456",
                    "type": "function_call",
                    "call_id": "call_xyz",
                    "name": "Bash",
                    "arguments": '{"command": "ls"}',
                    "status": "completed",
                },
            },
        ),
        ("response.completed", {"type": "response.completed"}),
    ]
    result = _collect_sse(raw_events)

    # Concatenated partial_json must equal the full arguments JSON.
    json_frag = "".join(
        d["delta"]["partial_json"]
        for _, d in result
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert json_frag == '{"command": "ls"}'

    # A content_block_delta of type input_json_delta must have been emitted.
    assert any(
        isinstance(d, dict)
        and d.get("type") == "content_block_delta"
        and d["delta"].get("type") == "input_json_delta"
        for _, d in result
    )


def test_responses_sse_transform_parallel_tool_args_in_item_done():
    """C1b regression: with 2 parallel function_calls where ONLY the first
    streams args (function_call_arguments.delta/.done) and the second carries its
    args exclusively in the final output_item.done item.arguments (no delta/.done
    events for it), both tool_use blocks must receive arguments — the second must
    NOT be left with input {} (live signature seen with muse-spark: output_item.
    added:3, function_call_arguments.delta:1, function_call_arguments.done:1)."""
    raw_events: list[tuple[str | None, dict[str, Any]]] = [
        ("response.created", {"type": "response.created"}),
        (
            "response.output_item.added",
            {"type": "response.output_item.added",
             "item": {"id": "msg1", "type": "message", "role": "assistant",
                      "content": [{"type": "output_text", "text": ""}]}},
        ),
        # Tool A: Read — args streamed via delta + done
        (
            "response.output_item.added",
            {"type": "response.output_item.added",
             "item": {"id": "fc_A", "type": "function_call", "call_id": "call_A",
                      "name": "Read", "arguments": "", "status": "in_progress"}},
        ),
        ("response.function_call_arguments.delta",
         {"type": "response.function_call_arguments.delta", "delta": '{"file_path": "'}),
        ("response.function_call_arguments.delta",
         {"type": "response.function_call_arguments.delta", "delta": 'CLAUDE.md"}'}),
        ("response.function_call_arguments.done",
         {"type": "response.function_call_arguments.done",
          "delta": '{"file_path": "CLAUDE.md"}'}),
        # Tool B: Bash — NO delta / NO arguments.done; args ONLY in item.done
        (
            "response.output_item.added",
            {"type": "response.output_item.added",
             "item": {"id": "fc_B", "type": "function_call", "call_id": "call_B",
                      "name": "Bash", "arguments": "", "status": "in_progress"}},
        ),
        (
            "response.output_item.done",
            {"type": "response.output_item.done",
             "item": {"id": "fc_B", "type": "function_call", "call_id": "call_B",
                      "name": "Bash", "arguments": '{"command": "ls"}',
                      "status": "completed"}},
        ),
        (
            "response.output_item.done",
            {"type": "response.output_item.done",
             "item": {"id": "fc_A", "type": "function_call", "call_id": "call_A",
                      "name": "Read", "arguments": '{"file_path": "CLAUDE.md"}',
                      "status": "completed"}},
        ),
        ("response.completed", {"type": "response.completed"}),
    ]
    result = _collect_sse(raw_events)

    # Concatenated partial_json must contain BOTH tools' full args JSON.
    json_frags = "".join(
        d["delta"]["partial_json"]
        for _, d in result
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
        and d.get("delta", {}).get("type") == "input_json_delta"
    )
    assert '{"file_path": "CLAUDE.md"}' in json_frags, json_frags
    assert '{"command": "ls"}' in json_frags, json_frags


def test_responses_sse_transform_output_text_done():
    """A provider that emits ONLY response.output_text.done (final full text)
    with no .delta events must still deliver the text to the client."""
    raw_events: list[tuple[str | None, dict[str, Any]]] = [
        ("response.created", {"type": "response.created"}),
        ("response.output_text.done", {"type": "response.output_text.done", "text": "hello world"}),
        ("response.completed", {"type": "response.completed"}),
    ]
    result = _collect_sse(raw_events)

    event_types = [t for t, _ in result]
    assert "message_start" in event_types
    assert "content_block_start" in event_types
    assert "content_block_delta" in event_types
    assert "content_block_stop" in event_types
    assert "message_stop" in event_types

    text = "".join(
        d["delta"]["text"]
        for _, d in result
        if isinstance(d, dict) and d.get("type") == "content_block_delta"
    )
    assert text == "hello world"


def test_responses_transform_tool_result_dict_to_json():
    """A tool_result whose content is a dict must become valid JSON in the
    Responses function_call_output.output field — NOT a Python repr."""
    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_abc",
                        "content": {"kind": "json", "rows": [1, 2]},
                    }
                ],
            },
        ],
    }
    result = cp.transform_anthropic_to_openai_responses(payload)
    fco = [i for i in result["input"] if i.get("type") == "function_call_output"]
    assert len(fco) == 1
    assert fco[0]["call_id"] == "call_abc"
    # Must be parseable JSON that deep-equals the original dict.
    parsed = json.loads(fco[0]["output"])
    assert parsed == {"kind": "json", "rows": [1, 2]}
    # Must NOT be a Python repr (single-quoted keys).
    assert fco[0]["output"] != "{'kind': 'json', 'rows': [1, 2]}"


def test_responses_transform_roundtrip_flattens_tool_calls():
    """Round-2 tool round-trip must flatten tool_use/tool_result into separate
    Responses items — NOT a chat-completions ``tool_calls`` field (which the
    /v1/responses endpoint rejects). Regression for the silent empty-200 bug."""
    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "jam berapa sekarang?"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Saya cek."},
                    {"type": "tool_use", "id": "call_abc", "name": "get_time", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "call_abc", "content": "14:30"}],
            },
        ],
    }
    result = cp.transform_anthropic_to_openai_responses(payload)
    inp = result["input"]

    # No item may carry the chat-completions tool_calls field.
    assert not any("tool_calls" in item for item in inp)

    # Order mirrors the Anthropic turns: user msg, assistant msg, function_call, function_call_output.
    assert inp[0] == {"type": "message", "role": "user", "content": "jam berapa sekarang?"}
    assert inp[1] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Saya cek."}],
    }
    fc = [i for i in inp if i.get("type") == "function_call"]
    assert len(fc) == 1
    assert fc[0]["call_id"] == "call_abc"
    assert fc[0]["name"] == "get_time"
    assert fc[0]["arguments"] == "{}"
    fco = [i for i in inp if i.get("type") == "function_call_output"]
    assert len(fco) == 1
    assert fco[0]["call_id"] == "call_abc"
    assert fco[0]["output"] == "14:30"


def test_responses_sse_transform_forwards_upstream_error():
    """An upstream error event must surface to the client, not be swallowed into
    an empty 200 stream (which made the client show no answer)."""
    raw_events: list[tuple[str | None, dict[str, Any]]] = [
        (
            "error",
            {
                "type": "error",
                "error": {"type": "upstream_error", "status_code": 400, "message": "bad tool_calls"},
            },
        ),
    ]
    result = _collect_sse(raw_events)

    assert len(result) == 1
    etype, data = result[0]
    assert etype == "error"
    assert data["type"] == "error"
    assert data["error"]["type"] == "upstream_error"
    assert data["error"]["status_code"] == 400
    assert "bad tool_calls" in data["error"]["message"]


def _reject_upstream(status: int = 400) -> Callable[[httpx.Request], httpx.Response]:
    """MockTransport handler that rejects with an HTTP error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text='{"error": {"message": "upstream rejected"}}')
    return handler


@pytest.mark.asyncio
async def test_e2e_responses_upstream_400_not_swallowed():
    """End-to-end: upstream 4xx on the Responses path must yield an Anthropic
    error SSE event — not an empty HTTP 200 stream."""
    _mock_upstream(_reject_upstream(400))

    payload: dict[str, Any] = {
        "model": "opencode-go/muse-spark-1.2-contributor",
        "messages": [{"role": "user", "content": "halo"}],
        "max_tokens": 100,
    }

    transport = httpx.ASGITransport(app=cp.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _post(client, payload)

    assert resp.status_code == 200
    assert "event: error" in resp.text
    assert "upstream_error" in resp.text
    assert "message_stop" not in resp.text
