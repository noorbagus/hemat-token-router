"""Hermetic tests for csmart v3 standalone proxy (``csmart_proxy.py``).

Drives the FastAPI app with ``httpx.ASGITransport`` and replaces the upstream
with ``httpx.MockTransport`` serving canned SSE bodies (pola
``tests/test_proxy_server.py``). No live upstream, no Ollama: seluruh module
berjalan di bawah ``pytest -m "not live"``.

Fokus: sanitasi key/credential agar tidak bocor ke upstream / disk / log,
reversible CCR + intercept ``csmart_expand_symbol``, prefix alignment, router
heuristic, keepalive snapshot.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import csmart_proxy as cp


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine to completion with a fresh event loop."""
    return asyncio.run(coro)


def _sse_body(events: List[tuple]) -> str:
    """events: [(event_name, payload_dict), ...] -> full SSE body."""
    return (
        "\n\n".join(f"event: {name}\ndata: {json.dumps(payload)}" for name, payload in events)
        + "\n\n"
    )


def _text_delta(text: str) -> tuple:
    return (
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
    )


def _simple_upstream(text: str = "hello") -> str:
    return _sse_body(
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "role": "assistant",
                        "content": [],
                        "model": "mock",
                        "stop_reason": None,
                        "usage": {"input_tokens": 1, "output_tokens": 0},
                    },
                },
            ),
            (
                "content_block_start",
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            ),
            _text_delta(text),
            (
                "message_delta",
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}},
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )


def _tool_use_upstream(tool_name: str, tool_input: Dict[str, Any], tool_id: str = "toolu_1") -> str:
    """SSE body where the model calls one tool (input inline, no deltas)."""
    return _sse_body(
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "role": "assistant",
                        "content": [],
                        "model": "mock",
                        "stop_reason": None,
                        "usage": {"input_tokens": 1, "output_tokens": 0},
                    },
                },
            ),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 5}},
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )


def _mask_id_for(secret: str) -> str:
    return f"__CSMART_SEC_{hashlib.sha256(secret.encode('utf-8')).hexdigest()[:8]}__"


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """Isolate state: DB + log dir di tmp, key fixed, vault/global reset."""
    monkeypatch.setattr(cp, "DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(cp, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(cp, "UPSTREAM_API_KEY", "test-key-abcdef123456")
    monkeypatch.setattr(cp, "_UPSTREAM_TRANSPORT", None)
    monkeypatch.setattr(cp, "_prefix_snapshot", None)
    monkeypatch.setattr(cp, "_active_model", cp.FLASH_MODEL)
    monkeypatch.setattr(cp, "_session_model", {})
    monkeypatch.setattr(cp.vault, "mem_cache", {})
    monkeypatch.setattr(cp.vault, "reverse_cache", {})
    monkeypatch.setattr(cp.vault, "_fernet", None)
    cp.init_db()


@pytest.fixture
def mock_upstream(monkeypatch):
    """Install a MockTransport upstream; returns a list recording each request."""

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
            raise AssertionError(f"unexpected upstream call #{len(calls)}")

        monkeypatch.setattr(cp, "_UPSTREAM_TRANSPORT", httpx.MockTransport(handler))
        return calls

    return _install


def _post(body: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
    """POST /v1/messages to the ASGI app."""
    payload = body or {
        "model": "mock-model",
        "stream": True,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": "hello"}],
    }
    req_headers = {"x-csmart-session": "test-session"}
    if headers:
        req_headers.update(headers)

    async def _run_post():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=cp.app), base_url="http://test"
        ) as client:
            return await client.post("/v1/messages", headers=req_headers, json=payload)

    return _run(_run_post())


def _log_text(tmp_path) -> str:
    logs = list((tmp_path / "logs").glob("session_*.jsonl"))
    if not logs:
        return ""
    return "\n".join(p.read_text("utf-8") for p in logs)


# ---------------------------------------------------------------------------
# 1. DLP & Secret Vault.
# ---------------------------------------------------------------------------

def test_dlp_mask_and_roundtrip():
    secret = "sk-ant-test-1234567890abcdef1234"
    text = f"the api key is {secret}, keep it safe"
    masked = cp.vault.mask_text(text)
    assert secret not in masked
    assert "__CSMART_SEC_" in masked
    assert cp.vault.unmask_text(masked) == text


def test_generic_assignment_secret_masked():
    text = 'password = "S3cretV4lue!!-xyz"'
    masked = cp.vault.mask_text(text)
    assert "S3cretV4lue!!-xyz" not in masked
    assert cp.vault.unmask_text(masked) == text


def test_entropy_false_positive_untouched():
    """Kode legit (hash, UUID, ref_, path, camelCase) tidak boleh ter-mask."""
    sample = (
        "commit 8a1f4b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8g "
        "uuid=123e4567-e89b-12d3-a456-426614174000 "
        "ref_12345678 "
        "path=/Volumes/Xugab/LAB/src/main.py "
        "sha256:4bf178939b1d1a6c2a2b4e29d2f9f5d0c2c1f9e6d8c7b4a3e5f6g7h8i9j0k1l2 "
        "myFunctionName some_snake_case_var"
    )
    assert cp.vault.mask_text(sample) == sample


def test_vault_at_rest_real_secret_is_null():
    """Default vault = in-memory only: real_secret TIDAK pernah plaintext di DB."""
    secret = "sk-test-111111111111111111111111"
    cp.vault.mask_text(f"key = {secret}")
    with cp.get_db() as conn:
        rows = conn.execute("SELECT real_secret FROM secret_vault").fetchall()
    assert len(rows) >= 1
    assert all(row["real_secret"] is None for row in rows)


def test_streaming_redactor_split_marker():
    """Marker yang terpotong antar-chunk tetap ter-restore penuh (split-safe)."""
    secret = "sk-live-aaaaaaaaaaaaaaaaaaaaaaaa"
    cp.vault.mask_text(secret)  # register marker->secret mapping di vault
    marker = _mask_id_for(secret)
    red = cp.StreamingRedactor()
    out1 = red.feed("A" * 40 + marker + "B" * 40)  # marker lengkap di tengah chunk
    assert secret not in out1  # belum lengkap di chunk ini -> tidak bocor sebagian
    out2 = red.feed("C" * 40)
    assert out1 + out2 + red.flush() == "A" * 40 + secret + "B" * 40 + "C" * 40
    # marker terpotong di boundary emit/rest dalam satu chunk -> ditahan, tidak rusak
    red2 = cp.StreamingRedactor()
    out = red2.feed("B" * 60 + marker + "C" * 60)
    assert secret not in out
    assert out + red2.flush() == "B" * 60 + secret + "C" * 60


# ---------------------------------------------------------------------------
# 2. Guardrail.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    ["~/.ssh/id_ed25519", ".env", "proj/.env.local", "creds/credentials.csv", "service_account.json", "secret.pem", "x/y/../../.env"],
)
def test_guardrail_blocks_secret_paths(path):
    assert cp.check_security_guardrails("Read", {"file_path": path}) is not None


@pytest.mark.parametrize("cmd", ["env", "printenv", "export -p", "security find-generic-password -w", "cat ~/.env", "grep PASSWORD .env"])
def test_guardrail_blocks_commands(cmd):
    assert cp.check_security_guardrails("bash", {"command": cmd}) is not None


def test_guardrail_allows_normal_files_and_commands():
    assert cp.check_security_guardrails("Read", {"file_path": "src/main.py"}) is None
    assert cp.check_security_guardrails("Edit", {"file_path": "README.md"}) is None
    assert cp.check_security_guardrails("bash", {"command": "ls -la && git status"}) is None
    assert cp.check_security_guardrails("bash", {"command": "python3.14 -m pytest -q"}) is None


def test_guardrail_blocks_nested_view_input():
    """tool_use.input.view.file_path (nested) juga dicegat."""
    assert cp.check_security_guardrails("NotebookEdit", {"view": {"file_path": "~/.aws/credentials"}}) is not None


# ---------------------------------------------------------------------------
# 3. Reversible CCR.
# ---------------------------------------------------------------------------

def test_ccr_store_expand_roundtrip():
    big = "\n".join(f"line {i:04d} - content" for i in range(200))
    ref, stub = cp.store_ccr_payload("tool_result", big)
    assert ref.startswith("ref_")
    assert len(stub) < len(big)  # terpotong (stub), bukan salinan penuh
    assert ref in stub
    assert cp.get_ccr_payload(ref) == big
    assert cp.get_ccr_payload("ref_00000000") is None


# ---------------------------------------------------------------------------
# 4. Prefix aligner + router.
# ---------------------------------------------------------------------------

def test_align_prefix_3_region_determinism():
    body = {
        "system": [],
        "tools": [{"name": "B", "input_schema": {}}, {"name": "A", "input_schema": {}}],
        "messages": [{"role": "user", "content": "hi"}],
    }
    a1 = cp.align_prefix_3_region(dict(body))
    a2 = cp.align_prefix_3_region(dict(body))
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)
    names = [t["name"] for t in a1["tools"]]
    assert names == ["A", "B", "csmart_expand_symbol"]  # sorted + expand tool terdaftar
    assert a1["tools"][-1]["cache_control"] == {"type": "ephemeral"}  # marker di akhir
    assert all("cache_control" not in t for t in a1["tools"][:-1])


def test_router_heuristic_flash_vs_flagship():
    flash = cp.route_model_tier({"messages": [{"role": "user", "content": "fix indentation in a.py"}]}, "s1")
    flagship = cp.route_model_tier({"messages": [{"role": "user", "content": "security audit the auth module"}]}, "s2")
    assert flash == cp.FLASH_MODEL
    assert flagship == cp.FLAGSHIP_MODEL


def test_session_model_pinned():
    m1 = cp.route_model_tier({"messages": [{"role": "user", "content": "fix typo"}]}, "same")
    m2 = cp.route_model_tier({"messages": [{"role": "user", "content": "security audit the whole system"}]}, "same")
    assert m1 == m2  # session yang sama: model tidak berubah antar-turn
    m3 = cp.route_model_tier({"messages": [{"role": "user", "content": "security audit the whole system"}]}, "other")
    assert m3 != m1


# ---------------------------------------------------------------------------
# 5. Proxy e2e (ASGITransport + MockTransport).
# ---------------------------------------------------------------------------

def test_text_streamed_to_client(mock_upstream):
    calls = mock_upstream([_simple_upstream("Hello from upstream")])
    resp = _post()
    assert resp.status_code == 200
    assert "Hello from upstream" in resp.text
    assert len(calls) == 1


def test_secret_never_sent_upstream(mock_upstream):
    """DLP: nilai secret asli tidak boleh sampai ke body upstream."""
    secret = "sk-ant-test-1234567890abcdef1234"
    calls = mock_upstream([_simple_upstream("ok")])
    body = {
        "model": "mock-model",
        "stream": True,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": f"the key is {secret}, use it"}],
    }
    _post(body)
    sent = calls[0].content.decode("utf-8")
    assert secret not in sent
    assert "__CSMART_SEC_" in sent


def test_secret_restored_to_client(mock_upstream):
    """Unmask jalur keluar: client menerima nilai asli, bukan marker."""
    secret = "sk-test-222222222222222222222222"
    cp.vault.mask_text(f"the key is {secret}")  # seed mapping (seperti inbound mask)
    marker = _mask_id_for(secret)
    calls = mock_upstream([_simple_upstream(f"stored secret is {marker}")])
    resp = _post()
    assert secret in resp.text
    assert marker not in resp.text
    assert len(calls) == 1


def test_client_auth_header_not_forwarded(mock_upstream):
    """authorization/x-api-key client tidak pernah diteruskan ke upstream."""
    calls = mock_upstream([_simple_upstream("ok")])
    _post(headers={"authorization": "Bearer client-real-key-123", "x-api-key": "client-x-api-456"})
    req_headers = dict(calls[0].headers)
    assert req_headers.get("authorization") == "Bearer test-key-abcdef123456"  # key upstream, bukan client
    assert req_headers.get("x-api-key") is None


def test_max_tokens_clamped_to_floor(mock_upstream):
    calls = mock_upstream([_simple_upstream("ok")])
    _post({"model": "m", "stream": True, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]})
    sent = json.loads(calls[0].content.decode("utf-8"))
    assert sent["max_tokens"] == cp.MAX_TOKENS_FLOOR  # 4096, bukan 1


def test_models_passthrough(mock_upstream):
    mock_upstream([json.dumps({"data": [{"id": "deepseek-chat"}]})])
    resp = _run(
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=cp.app), base_url="http://test"
        ).get("/v1/models")
    )
    assert resp.status_code == 200
    assert "deepseek-chat" in resp.text


def test_expand_intercept_e2e(mock_upstream):
    """Intercept csmart_expand_symbol: tool_use di-hold, tool_result di-resubmit,
    round-2 stream ke client — tool_use asli TIDAK pernah diteruskan."""
    big = "\n".join(f"content line {i}" for i in range(120))
    ref, _ = cp.store_ccr_payload("tool_result", big)
    calls = mock_upstream([_tool_use_upstream("csmart_expand_symbol", {"ref_id": ref}), _simple_upstream("expanded!")])
    resp = _post()
    assert len(calls) == 2  # round 1 (expand) + round 2 (lanjutan)
    assert "expanded!" in resp.text
    assert "csmart_expand_symbol" not in resp.text  # tool_use tidak bocor ke client
    # round-2 request membawa tool_result hasil expand
    followup = json.loads(calls[1].content.decode("utf-8"))
    tool_results = [b for b in followup["messages"][-1]["content"] if b.get("type") == "tool_result"]
    assert tool_results and big in tool_results[0]["content"]


def test_guardrail_intercept_e2e(mock_upstream):
    """tool_use berbahaya di-hold, hasil 'BLOCKED' di-resubmit, tool_use tidak ke client."""
    calls = mock_upstream([_tool_use_upstream("Read", {"file_path": "~/.ssh/id_ed25519"}), _simple_upstream("proceed")])
    resp = _post()
    assert len(calls) == 2
    assert "proceed" in resp.text
    followup = json.loads(calls[1].content.decode("utf-8"))
    tool_results = [b for b in followup["messages"][-1]["content"] if b.get("type") == "tool_result"]
    assert tool_results and "CSMART SECURITY BLOCKED" in tool_results[0]["content"]


def test_expand_missing_ref_error(mock_upstream):
    """csmart_expand_symbol tanpa ref_id -> pesan error (bukan crash)."""
    calls = mock_upstream([_tool_use_upstream("csmart_expand_symbol", {}), _simple_upstream("retry please")])
    resp = _post()
    assert resp.status_code == 200
    followup = json.loads(calls[1].content.decode("utf-8"))
    tool_results = [b for b in followup["messages"][-1]["content"] if b.get("type") == "tool_result"]
    assert tool_results and "ERROR" in tool_results[0]["content"]


def test_system_prompt_secret_masked(mock_upstream):
    """Secret di system prompt (bukan hanya messages) juga di-mask."""
    secret = "sk-ant-test-3333333333333333333333"
    calls = mock_upstream([_simple_upstream("ok")])
    body = {
        "model": "m",
        "stream": True,
        "max_tokens": 4096,
        "system": [{"type": "text", "text": f"internal cred = {secret}"}],
        "messages": [{"role": "user", "content": "go"}],
    }
    _post(body)
    sent = calls[0].content.decode("utf-8")
    assert secret not in sent
    assert "__CSMART_SEC_" in sent


def test_key_not_in_logs(mock_upstream, tmp_path):
    """Log JSONL tidak boleh mengandung nilai secret maupun upstream key."""
    secret = "sk-ant-test-4444444444444444444444"
    mock_upstream([_simple_upstream("ok")])
    body = {
        "model": "m",
        "stream": True,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": f"key = {secret}"}],
    }
    _post(body)
    logs = _log_text(tmp_path)
    assert "INBOUND_REQUEST" in logs  # event tercatat
    assert secret not in logs
    assert "test-key-abcdef123456" not in logs


# ---------------------------------------------------------------------------
# 6. Sanitizer.
# ---------------------------------------------------------------------------

def test_sanitize_strips_ansi_and_truncates():
    text = "\x1b[31mred\x1b[0m normal"
    assert cp.sanitize_raw_logs(text) == "red normal"
    big = "\n".join(f"line {i} " + "y" * 20 for i in range(100))  # ~2900 bytes > threshold
    out = cp.sanitize_raw_logs(big)
    assert len(out.encode("utf-8")) <= cp.SANITIZE_TRUNCATE_BYTES + 400
    assert "SNIPPED" in out
    assert "line 99" in out  # tail dipertahankan
