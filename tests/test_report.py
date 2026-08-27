"""Hermetic unit tests for report.py (schema, create_report, aggregate).

These tests never start the proxy server and never touch the network or
Ollama: report fixtures are built directly with the pydantic models.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.gate import GateResult  # noqa: E402
from router.ollama_scorer import RoutingResult  # noqa: E402
from router.report import (  # noqa: E402
    CsmartReport,
    GatewayConfig,
    StatsSummary,
    aggregate_reports,
    create_report,
    load_report,
    write_report,
)

DUMMY_BASE_URL = "https://example.invalid"


def _make_report(
    status: str = "ok",
    injected_bytes: int = 100,
    skeleton_bytes: int | None = None,
) -> CsmartReport:
    """Build a minimal CsmartReport fixture via create_report."""
    routing = RoutingResult(
        target_files=["src/a.py"],
        confidence=0.9,
        reasoning="test fixture",
    )
    gate = GateResult(
        status=status,
        selected_files=["src/a.py"],
        selected_bytes=injected_bytes,
        estimated_tokens=injected_bytes // 4,
        dropped_count=0,
        reason="test fixture",
    )
    gateway = GatewayConfig(
        base_url=DUMMY_BASE_URL,
        primary_model="test-model",
        opus_model="test-opus",
        fast_model="test-fast",
        effort_level="low",
    )
    return create_report(
        task="test task",
        ast_scan_ms=10,
        local_routing_ms=20,
        routing_result=routing,
        gate_result=gate,
        injected_bytes=injected_bytes,
        gateway_config=gateway,
        claude_result=None,
        status=status,
        skeleton_bytes=skeleton_bytes,
    )


def test_create_report_estimate_with_skeleton_bytes() -> None:
    """skeleton_bytes drives the real token-saved estimate (tokens ~ bytes / 4)."""
    report = _make_report(status="ok", injected_bytes=200, skeleton_bytes=1000)
    assert report.estimated_tokens_saved == 200  # (1000 - 200) // 4

    # skeleton smaller than injected -> floored at 0 via max(0, ...)
    report_floor = _make_report(status="ok", injected_bytes=200, skeleton_bytes=100)
    assert report_floor.estimated_tokens_saved == 0


def test_create_report_estimate_none_when_skeleton_absent() -> None:
    """Without skeleton_bytes the estimate stays None (no placeholder)."""
    report = _make_report(status="ok", injected_bytes=200, skeleton_bytes=None)
    assert report.estimated_tokens_saved is None


def test_write_load_roundtrip(tmp_path) -> None:
    """write_report then load_report returns an identical report."""
    report = _make_report(status="ok", injected_bytes=100, skeleton_bytes=900)
    path = tmp_path / "report.json"
    write_report(report, str(path))

    loaded = load_report(str(path))
    assert isinstance(loaded, CsmartReport)
    assert loaded.status == report.status == "ok"
    assert loaded.estimated_tokens_saved == report.estimated_tokens_saved == 200


def test_aggregate_reports_totals(tmp_path) -> None:
    """Aggregation sums injected bytes, tokens saved, and groups by status."""
    ok_report = _make_report(status="ok", injected_bytes=100, skeleton_bytes=900)
    blocked_report = _make_report(
        status="gate_blocked", injected_bytes=0, skeleton_bytes=None
    )

    ok_path = tmp_path / "ok.json"
    blocked_path = tmp_path / "blocked.json"
    write_report(ok_report, str(ok_path))
    write_report(blocked_report, str(blocked_path))

    summary = aggregate_reports([str(ok_path), str(blocked_path)])

    assert isinstance(summary, StatsSummary)
    assert summary.report_count == 2
    assert summary.status_counts == {"ok": 1, "gate_blocked": 1}
    assert summary.total_injected_bytes == 100
    assert summary.total_tokens_saved == 200


def test_aggregate_reports_skips_missing_and_invalid(tmp_path) -> None:
    """Missing paths and garbage JSON files are skipped without raising."""
    missing_path = tmp_path / "missing.json"

    garbage_path = tmp_path / "garbage.json"
    garbage_path.write_text("this is not json {", encoding="utf-8")

    valid_report = _make_report(status="ok", injected_bytes=100, skeleton_bytes=900)
    valid_path = tmp_path / "valid.json"
    write_report(valid_report, str(valid_path))

    summary = aggregate_reports(
        [str(missing_path), str(garbage_path), str(valid_path)]
    )

    assert summary.report_count == 1
    assert summary.status_counts == {"ok": 1}
    assert summary.total_injected_bytes == 100
    assert summary.total_tokens_saved == 200


def test_aggregate_reports_empty_list() -> None:
    """Empty input produces an empty summary with no exception."""
    summary = aggregate_reports([])
    assert summary.report_count == 0
    assert summary.status_counts == {}
    assert summary.avg_prepass_ms is None
    assert summary.total_injected_bytes == 0
    assert summary.total_tokens_saved == 0


def test_load_report_propagates_garbage_json(tmp_path) -> None:
    """load_report lets JSONDecodeError propagate (aggregate handles it)."""
    garbage_path = tmp_path / "garbage.json"
    garbage_path.write_text("{ not valid json", encoding="utf-8")
    try:
        load_report(str(garbage_path))
    except json.JSONDecodeError:
        return
    raise AssertionError("expected json.JSONDecodeError to propagate")
