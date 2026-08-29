"""JSON report schema for csmart execution.

Full structured report that persists all execution metrics, routing result,
gate/budget decisions, and dispatch outcome for automation/verification.
"""

import os
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ValidationError

from router.ollama_scorer import RoutingResult
from router.gate import GateResult
from router.cli_dispatch import DispatchResult


class ExecutionMetrics(BaseModel):
    """Timing and size metrics for the entire prepass."""
    ast_scan_ms: int
    local_routing_ms: int
    total_prepass_ms: int
    injected_files_count: int
    injected_bytes: int
    full_codebase_bytes: Optional[int] = None  # baseline: total bytes of all scanned source files


class GatewayConfig(BaseModel):
    """Gateway configuration loaded from environment."""
    base_url: str
    primary_model: str
    opus_model: str
    fast_model: str
    effort_level: str


class CsmartReport(BaseModel):
    """Full structured report for a csmart execution."""
    schema_version: str = "1.1"
    status: str  # "ok" | "gate_blocked" | "dispatch_error" | "env_error"
    timestamp: str  # ISO-8601 UTC
    task: str
    execution_metrics: ExecutionMetrics
    routed_context: RoutingResult
    gate_result: GateResult
    gateway_config: GatewayConfig
    claude_execution: Optional[DispatchResult] = None
    estimated_tokens_saved: Optional[int] = None


class StatsSummary(BaseModel):
    """Aggregated statistics across multiple CsmartReport files."""

    report_count: int
    status_counts: dict[str, int]  # e.g. {"ok": 2, "gate_blocked": 1}
    avg_prepass_ms: float | None
    total_injected_bytes: int
    total_tokens_saved: int


def load_report(path: str) -> CsmartReport:
    """Load a CsmartReport from a JSON file.

    FileNotFoundError and json.JSONDecodeError propagate to the caller.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CsmartReport.model_validate(data)


def aggregate_reports(report_paths: list[str]) -> StatsSummary:
    """Aggregate multiple report files into a StatsSummary.

    Skips any path that is missing, contains invalid JSON, or fails
    pydantic validation; the summary reflects only successfully parsed files.
    """
    reports: list[CsmartReport] = []
    for path in report_paths:
        try:
            reports.append(load_report(path))
        except (OSError, json.JSONDecodeError, ValidationError):
            # OSError covers FileNotFoundError, IsADirectoryError, PermissionError:
            # a broken/missing file in the report dir must not crash `csmart stats`.
            continue

    if not reports:
        return StatsSummary(
            report_count=0,
            status_counts={},
            avg_prepass_ms=None,
            total_injected_bytes=0,
            total_tokens_saved=0,
        )

    total_prepass_ms = sum(r.execution_metrics.total_prepass_ms for r in reports)
    total_injected_bytes = sum(r.execution_metrics.injected_bytes for r in reports)
    total_tokens_saved = sum(r.estimated_tokens_saved or 0 for r in reports)

    return StatsSummary(
        report_count=len(reports),
        status_counts=dict(Counter(r.status for r in reports)),
        avg_prepass_ms=total_prepass_ms / len(reports),
        total_injected_bytes=total_injected_bytes,
        total_tokens_saved=total_tokens_saved,
    )


def write_report(
    report: CsmartReport,
    report_path: str,
) -> None:
    """Write JSON report to file, creating directory if needed."""
    report_dir = os.path.dirname(report_path)
    if report_dir and not os.path.exists(report_dir):
        os.makedirs(report_dir, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)


def create_report(
    task: str,
    ast_scan_ms: int,
    local_routing_ms: int,
    routing_result: RoutingResult,
    gate_result: GateResult,
    injected_bytes: int,
    gateway_config: GatewayConfig,
    claude_result: Optional[DispatchResult],
    status: str,
    *,
    skeleton_bytes: int | None = None,
    full_codebase_bytes: int | None = None,
) -> CsmartReport:
    """Create a complete CsmartReport with proper timestamp and metrics."""
    total_prepass = ast_scan_ms + local_routing_ms

    # Estimate tokens saved vs the full codebase baseline (tokens ≈ bytes / 4).
    # Without csmart, DeepSeek would read the whole codebase; with it, only the
    # injected context is sent. Fall back to the skeleton baseline when the
    # full-codebase byte count is unavailable (e.g. proxy cache path or older
    # callers).
    if full_codebase_bytes is not None:
        estimated_tokens_saved = max(0, (full_codebase_bytes - injected_bytes) // 4)
    elif skeleton_bytes is not None:
        estimated_tokens_saved = max(0, (skeleton_bytes - injected_bytes) // 4)
    else:
        estimated_tokens_saved = None

    return CsmartReport(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        task=task,
        execution_metrics=ExecutionMetrics(
            ast_scan_ms=ast_scan_ms,
            local_routing_ms=local_routing_ms,
            total_prepass_ms=total_prepass,
            injected_files_count=len(gate_result.selected_files),
            injected_bytes=injected_bytes,
            full_codebase_bytes=full_codebase_bytes,
        ),
        routed_context=routing_result,
        gate_result=gate_result,
        gateway_config=gateway_config,
        claude_execution=claude_result,
        estimated_tokens_saved=estimated_tokens_saved,
    )
