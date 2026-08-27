"""Tests for the local reverse proxy."""

import pytest
from fastapi.testclient import TestClient
from router.proxy import app

client = TestClient(app)


def test_options_cors():
    """Test CORS preflight OPTIONS request."""
    response = client.options("/v1/messages")
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" in response.headers
    assert "Access-Control-Allow-Methods" in response.headers
    assert "Access-Control-Allow-Headers" in response.headers


def test_non_messages_passthrough():
    """Test non-messages requests pass through untouched (we don't mock upstream, just check routing)."""
    # This will fail upstream but we just check routing accepts it
    response = client.get("/v1/models")
    # Should get an error from upstream which means it passed through
    assert response.status_code in (401, 403, 405, 500)  # auth error or method not allowed expected


def test_messages_interception_missing_auth():
    """Test /v1/messages is intercepted, expects JSON."""
    response = client.post("/v1/messages", json={
        "model": "doubao-seed-2.0-lite",
        "messages": [
            {"role": "user", "content": "Hello world"}
        ]
    })
    # Will fail upstream due to auth but routing worked
    assert response.status_code in (401, 403, 500)


def test_inject_context_to_messages():
    """Test that context injection logic works on messages."""
    from router.proxy import inject_context_to_messages

    # Simple case: one user message
    messages = [
        {"role": "user", "content": "Fix the indentation in csmart.py"},
    ]
    result = inject_context_to_messages(messages, ["csmart.py"])

    assert len(result) == 1
    assert "csmart.py" in result[0]["content"]
    assert "PRE-LOADED CONTEXT" in result[0]["content"]
    assert "--- FILE START: csmart.py ---" in result[0]["content"]


def test_inject_context_preserves_system_message():
    """Test context injection preserves existing system message."""
    from router.proxy import inject_context_to_messages

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Fix the indentation"},
    ]
    result = inject_context_to_messages(messages, ["csmart.py"])

    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert "PRE-LOADED CONTEXT" in result[1]["content"]


def test_inject_context_no_selected_files():
    """Test when no files are selected, nothing changes."""
    from router.proxy import inject_context_to_messages

    messages = [
        {"role": "user", "content": "Hello"},
    ]
    result = inject_context_to_messages(messages, [])

    assert result == messages


def test_pyright_ignored_types():
    """Ignore type mismatch on FastAPI Request that pyright complains about - it's just a false positive."""
    # This is just here to keep pytest happy - the issue is that pyright sees
    # fastapi.Request vs httpx.Request type mismatch. It doesn't affect runtime.
    pass
