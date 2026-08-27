"""Hermetic tests for router/logger.py (StructuredLogger, Track D — CONTRACTS.md §2)."""

import json
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.logger import (
    AST_SCANNED,
    INBOUND_REQUEST,
    OLLAMA_TRIAGE,
    SSE_STREAM_COMPLETE,
    TOOL_LOCAL_EXEC,
    TOOL_SHADOW_INTERCEPT,
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


def test_module_singleton():
    from router.logger import logger

    assert isinstance(logger, StructuredLogger)


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
