"""Hermetic tests for router/logger.py (StructuredLogger, Track D — CONTRACTS.md §2)."""

import json
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.logger import (
    AST_CACHE_HIT,
    AST_SCANNED,
    CLI_DISPATCH,
    CONTEXT_INJECTED,
    GATE_APPLIED,
    IMPORT_EXPANSION,
    INBOUND_REQUEST,
    MODEL_ROUTED,
    OLLAMA_FALLBACK,
    OLLAMA_HEALTH,
    OLLAMA_TRIAGE,
    PASSTHROUGH,
    ROUTING_CACHE_EXPIRED,
    ROUTING_CACHE_HIT,
    ROUTING_CACHE_MISS,
    ROUTING_CACHE_PUT,
    SERVER_START,
    SERVER_STOP,
    SSE_STREAM_COMPLETE,
    TOOL_LOCAL_EXEC,
    TOOL_SHADOW_INTERCEPT,
    TOOL_SUMMARIZE,
    UPSTREAM_HEALTH,
    UPSTREAM_RETRY,
    StructuredLogger,
)


@pytest.fixture
def logger(tmp_path):
    lg = StructuredLogger(log_dir=tmp_path)
    yield lg
    lg.close()


def _read_records(tmp_path: Path) -> list[dict]:
    (logfile,) = tmp_path.glob("session_*.jsonl")
    return [json.loads(line) for line in logfile.read_text(encoding="utf-8").strip().splitlines()]


def test_event_constants_exact():
    assert INBOUND_REQUEST == "INBOUND_REQUEST"
    assert AST_SCANNED == "AST_SCANNED"
    assert OLLAMA_TRIAGE == "OLLAMA_TRIAGE"
    assert TOOL_SHADOW_INTERCEPT == "TOOL_SHADOW_INTERCEPT"
    assert TOOL_LOCAL_EXEC == "TOOL_LOCAL_EXEC"
    assert SSE_STREAM_COMPLETE == "SSE_STREAM_COMPLETE"


def test_new_event_constants_exact():
    assert AST_CACHE_HIT == "AST_CACHE_HIT"
    assert ROUTING_CACHE_HIT == "ROUTING_CACHE_HIT"
    assert ROUTING_CACHE_MISS == "ROUTING_CACHE_MISS"
    assert ROUTING_CACHE_EXPIRED == "ROUTING_CACHE_EXPIRED"
    assert ROUTING_CACHE_PUT == "ROUTING_CACHE_PUT"
    assert OLLAMA_FALLBACK == "OLLAMA_FALLBACK"
    assert GATE_APPLIED == "GATE_APPLIED"
    assert IMPORT_EXPANSION == "IMPORT_EXPANSION"
    assert CONTEXT_INJECTED == "CONTEXT_INJECTED"
    assert TOOL_SUMMARIZE == "TOOL_SUMMARIZE"
    assert CLI_DISPATCH == "CLI_DISPATCH"
    assert SERVER_START == "SERVER_START"
    assert SERVER_STOP == "SERVER_STOP"
    assert PASSTHROUGH == "PASSTHROUGH"
    assert UPSTREAM_HEALTH == "UPSTREAM_HEALTH"
    assert OLLAMA_HEALTH == "OLLAMA_HEALTH"
    assert UPSTREAM_RETRY == "UPSTREAM_RETRY"
    assert MODEL_ROUTED == "MODEL_ROUTED"


def test_module_singleton():
    from router.logger import logger

    assert isinstance(logger, StructuredLogger)


def test_model_routed_fields_roundtrip(logger, tmp_path):
    logger.log(
        MODEL_ROUTED,
        model="qwen2.5-coder:7b",
        target="ollama",
        upstream="http://127.0.0.1:11434/v1/messages",
    )
    logger.flush()

    (record,) = _read_records(tmp_path)
    assert record["event"] == MODEL_ROUTED
    assert record["model"] == "qwen2.5-coder:7b"
    assert record["target"] == "ollama"
    assert record["upstream"] == "http://127.0.0.1:11434/v1/messages"


def test_jsonl_file_exists_and_parseable(logger, tmp_path):
    logger.log(INBOUND_REQUEST, path="/v1/messages")
    logger.flush()

    files = list(tmp_path.glob("session_*.jsonl"))
    assert len(files) == 1

    (record,) = _read_records(tmp_path)
    assert "ts" in record and "trace_id" in record and "event" in record
    assert record["event"] == INBOUND_REQUEST
    # ts must be a parseable ISO-8601 timestamp
    datetime.fromisoformat(record["ts"])


def test_event_and_custom_fields_roundtrip(logger, tmp_path):
    logger.log(INBOUND_REQUEST, trace_id="t1", path="/v1/messages")
    logger.flush()

    (record,) = _read_records(tmp_path)
    assert record["event"] == INBOUND_REQUEST
    assert record["trace_id"] == "t1"
    assert record["path"] == "/v1/messages"


def test_redaction_sensitive_keys(logger, tmp_path):
    logger.log(INBOUND_REQUEST, authorization="Bearer secret", api_key="k", path="/x")
    logger.flush()

    (record,) = _read_records(tmp_path)
    assert record["authorization"] == "[REDACTED]"
    assert record["api_key"] == "[REDACTED]"
    assert record["path"] == "/x"


def test_redaction_x_api_key_and_token(logger, tmp_path):
    logger.log(INBOUND_REQUEST, **{"x-api-key": "sekrit", "token": "abc"})
    logger.flush()

    (record,) = _read_records(tmp_path)
    assert record["x-api-key"] == "[REDACTED]"
    assert record["token"] == "[REDACTED]"


def test_redact_method(tmp_path):
    lg = StructuredLogger(log_dir=tmp_path)
    try:
        assert lg.redact("super-secret") == "[REDACTED]"
        assert lg.redact("anything") == "[REDACTED]"
    finally:
        lg.close()


def test_trace_id_propagation(logger, tmp_path):
    logger.set_trace_id("abc")
    logger.log(INBOUND_REQUEST)
    logger.log(AST_SCANNED)
    logger.flush()

    records = _read_records(tmp_path)
    assert len(records) == 2
    assert all(r["trace_id"] == "abc" for r in records)


def test_trace_id_isolated_per_task(tmp_path):
    """Two interleaved tasks must not clobber each other's trace id.

    Deterministic barrier: both tasks set their trace BEFORE either logs, so
    with the old process-global implementation both records would stamp the
    last-set trace; with the contextvars implementation each keeps its own.
    """
    import asyncio

    lg = StructuredLogger(log_dir=tmp_path)
    try:
        async def main() -> None:
            ready_a = asyncio.Event()
            ready_b = asyncio.Event()
            go = asyncio.Event()

            async def worker(trace: str, ready: asyncio.Event) -> None:
                lg.set_trace_id(trace)
                ready.set()
                await go.wait()
                lg.log(INBOUND_REQUEST, task=trace)

            t1 = asyncio.create_task(worker("trace-a", ready_a))
            t2 = asyncio.create_task(worker("trace-b", ready_b))
            await ready_a.wait()
            await ready_b.wait()
            go.set()
            await asyncio.gather(t1, t2)

        asyncio.run(main())
        lg.flush()

        records = _read_records(tmp_path)
        assert len(records) == 2
        assert {r["trace_id"] for r in records} == {"trace-a", "trace-b"}
        assert all(r["trace_id"] == r["task"] for r in records)
    finally:
        lg.close()


def test_trace_id_propagates_to_thread(tmp_path):
    """asyncio.to_thread must carry the trace context into the worker thread —
    this is the mechanism source-level events rely on (route_target_files,
    apply_gate, _execute_local_tool_sync all run via to_thread).
    """
    import asyncio

    lg = StructuredLogger(log_dir=tmp_path)
    try:
        async def main() -> None:
            lg.set_trace_id("trace-thread")
            await asyncio.to_thread(lg.log, AST_SCANNED, thread="yes")

        asyncio.run(main())
        lg.flush()

        (record,) = _read_records(tmp_path)
        assert record["trace_id"] == "trace-thread"
        assert record["thread"] == "yes"
    finally:
        lg.close()


def test_concurrency_no_lost_or_corrupt_writes(tmp_path):
    lg = StructuredLogger(log_dir=tmp_path)
    try:
        def worker() -> None:
            for i in range(50):
                lg.log(INBOUND_REQUEST, idx=i)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lg.flush()

        (logfile,) = tmp_path.glob("session_*.jsonl")
        lines = [ln for ln in logfile.read_text(encoding="utf-8").strip().splitlines() if ln]
        assert len(lines) == 1000
        for line in lines:
            record = json.loads(line)
            assert record["event"] == INBOUND_REQUEST
    finally:
        lg.close()


def test_close_flushes_pending(tmp_path):
    lg = StructuredLogger(log_dir=tmp_path)
    lg.log(INBOUND_REQUEST)
    lg.close()

    records = _read_records(tmp_path)
    assert len(records) == 1
    assert records[0]["event"] == INBOUND_REQUEST


def test_close_idempotent(tmp_path):
    lg = StructuredLogger(log_dir=tmp_path)
    lg.log(INBOUND_REQUEST)
    lg.close()
    lg.close()  # second close must not raise
