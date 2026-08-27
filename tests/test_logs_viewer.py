"""Hermetic tests for the csmart logs viewer (Wave 4 Track B).

No network, no Ollama, no real ~/.csmart filesystem: everything is backed by
``tmp_path`` and ``time.sleep`` is monkeypatched where the follow generator
would otherwise block.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router import logs_viewer
from router.cli_dispatch import DispatchResult
from router.gate import GateResult
from router.ollama_scorer import RoutingResult
from router.report import GatewayConfig, create_report, write_report


def _write_log_file(log_dir: Path, lines: list[dict]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "session_2026-08-28.jsonl"
    path.write_text(
        "".join(json.dumps(rec) + "\n" for rec in lines),
        encoding="utf-8",
    )
    return path


def test_read_log_records_parses_and_tails(tmp_path) -> None:
    lines = [
        {"ts": f"2026-08-28T00:00:0{i}Z", "trace_id": f"t{i}", "event": "AST_SCANNED", "files": i}
        for i in range(5)
    ]
    _write_log_file(tmp_path / "logs", lines)

    records = logs_viewer.read_log_records(str(tmp_path / "logs"), tail=2)

    assert len(records) == 2
    assert [r["files"] for r in records] == [3, 4]
    assert records[0]["ts"] == "2026-08-28T00:00:03Z"
    assert records[1]["ts"] == "2026-08-28T00:00:04Z"


def test_read_log_records_filters_by_event(tmp_path) -> None:
    lines = [
        {"ts": "2026-08-28T00:00:00Z", "trace_id": "a", "event": "INBOUND_REQUEST", "n": 1},
        {"ts": "2026-08-28T00:00:01Z", "trace_id": "a", "event": "OLLAMA_TRIAGE", "n": 2},
        {"ts": "2026-08-28T00:00:02Z", "trace_id": "a", "event": "INBOUND_REQUEST", "n": 3},
    ]
    _write_log_file(tmp_path / "logs", lines)

    records = logs_viewer.read_log_records(str(tmp_path / "logs"), tail=0, event="OLLAMA_TRIAGE")

    assert len(records) == 1
    assert records[0]["event"] == "OLLAMA_TRIAGE"
    assert records[0]["n"] == 2


def test_read_log_records_missing_dir(tmp_path) -> None:
    assert logs_viewer.read_log_records(str(tmp_path / "does-not-exist")) == []


def test_render_records_deterministic() -> None:
    records = [
        {
            "ts": "2026-08-28T00:00:00Z",
            "trace_id": "abc",
            "event": "INBOUND_REQUEST",
            "method": "POST",
            "path": "/v1/messages",
            "model": None,
        },
        {
            "ts": "2026-08-28T00:00:01Z",
            "trace_id": None,
            "event": "OLLAMA_TRIAGE",
            "candidates": 12,
        },
    ]
    expected = (
        "[2026-08-28T00:00:00Z] INBOUND_REQUEST trace_id=abc method=POST path=/v1/messages\n"
        "[2026-08-28T00:00:01Z] OLLAMA_TRIAGE candidates=12\n"
    )
    assert logs_viewer.render_records(records) == expected


def test_follow_yields_append(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(logs_viewer.time, "sleep", lambda s: None)
    log_dir = tmp_path / "logs"
    path = _write_log_file(
        log_dir,
        [{"ts": "2026-08-28T00:00:00Z", "trace_id": "a", "event": "FIRST", "n": 1}],
    )

    gen = logs_viewer.follow_log(str(log_dir))
    first = next(gen)
    assert first["event"] == "FIRST"

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-08-28T00:00:01Z", "trace_id": "b", "event": "SECOND", "n": 2}) + "\n")

    second = next(gen)
    assert second["event"] == "SECOND"
    assert second["n"] == 2


def test_cmd_stats_aggregates_fixture_reports(tmp_path, capsys) -> None:
    # --- fixture reports ---
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    gateway = GatewayConfig(
        base_url="https://ark.talaga.my.id",
        primary_model="doubao-seed-2.0-lite",
        opus_model="glm-5.3",
        fast_model="deepseek-v4-flash",
        effort_level="low",
    )

    ok_gate = GateResult(
        status="pass",
        selected_files=["file.py"],
        selected_bytes=100,
        estimated_tokens=25,
        dropped_count=0,
        reason="pass",
    )
    ok_report = create_report(
        task="ok-task",
        ast_scan_ms=100,
        local_routing_ms=23,
        routing_result=RoutingResult(target_files=["file.py"], confidence=1.0, reasoning="ok"),
        gate_result=ok_gate,
        injected_bytes=100,
        gateway_config=gateway,
        claude_result=DispatchResult(
            exit_code=0,
            duration_ms=10,
            cost_usd=None,
            session_id=None,
            result_excerpt="ok",
            dry_run=False,
        ),
        status="ok",
        skeleton_bytes=900,  # (900 - 100) // 4 = 200 estimated tokens saved
    )
    write_report(ok_report, str(report_dir / "report-ok.json"))

    blocked_gate = GateResult(
        status="blocked",
        selected_files=[],
        selected_bytes=0,
        estimated_tokens=0,
        dropped_count=0,
        reason="blocked",
    )
    blocked_report = create_report(
        task="blocked-task",
        ast_scan_ms=0,
        local_routing_ms=0,
        routing_result=RoutingResult(target_files=[], confidence=0.1, reasoning="none"),
        gate_result=blocked_gate,
        injected_bytes=0,
        gateway_config=gateway,
        claude_result=None,
        status="gate_blocked",
        skeleton_bytes=None,  # no estimate recorded
    )
    write_report(blocked_report, str(report_dir / "report-blocked.json"))

    # --- fixture logs: 1 INBOUND_REQUEST + 1 OLLAMA_TRIAGE ---
    log_dir = tmp_path / "logs"
    _write_log_file(
        log_dir,
        [
            {"ts": "2026-08-28T00:00:00Z", "trace_id": "a", "event": "INBOUND_REQUEST", "path": "/v1/messages"},
            {"ts": "2026-08-28T00:00:01Z", "trace_id": "a", "event": "OLLAMA_TRIAGE", "candidates": 3},
        ],
    )

    logs_viewer.cmd_stats(log_dir=str(log_dir), report_dir=str(report_dir), json_out=True)
    data = json.loads(capsys.readouterr().out)

    assert data["report_count"] == 2
    assert data["status_counts"] == {"ok": 1, "gate_blocked": 1}
    assert data["avg_prepass_ms"] == 61.5  # (123 + 0) / 2
    assert data["total_injected_bytes"] == 100
    assert data["total_tokens_saved"] == 200
    assert data["event_counts"] == {"INBOUND_REQUEST": 1, "OLLAMA_TRIAGE": 1}


def test_cmd_logs_missing_dir_no_crash(capsys) -> None:
    logs_viewer.cmd_logs("/nonexistent/log/dir")
    out, err = capsys.readouterr()
    assert "log directory not found" in err
    assert out == ""
