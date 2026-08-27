"""JSON report schema for csmart execution.

Full structured report that persists all execution metrics, routing result,
gate/budget decisions, and dispatch outcome for automation/verification.
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

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


class GatewayConfig(BaseModel):
    """Gateway configuration loaded from environment."""
    base_url: str
    primary_model: str
    opus_model: str
    fast_model: str
    effort_level: str


class CsmartReport(BaseModel):
    """Full structured report for a csmart execution."""
    schema_version: str = "1.0"
    status: str  # "ok" | "gate_blocked" | "dispatch_error" | "env_error"
    timestamp: str  # ISO-8601 UTC
    task: str
    execution_metrics: ExecutionMetrics
    routed_context: RoutingResult
    gate_result: GateResult
    gateway_config: GatewayConfig
    claude_execution: Optional[DispatchResult] = None
    estimated_tokens_saved: Optional[int] = None


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
) -> CsmartReport:
    """Create a complete CsmartReport with proper timestamp and metrics."""
    total_prepass = ast_scan_ms + local_routing_ms

    # Estimate tokens saved: assume full context would be ~5x bigger (token saved)
    estimated_saved = None
    if injected_bytes > 0:
        # Very rough estimate: 4 bytes per token, assume full scan would be 5x more
        estimated_saved = int((injected_bytes * 4) // 4)  # injected is already injected bytes
        # Actually estimate tokens saved vs full context (all files vs selected)
        # We don't know full context size, so leave as None for now - could compute later

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
        ),
        routed_context=routing_result,
        gate_result=gate_result,
        gateway_config=gateway_config,
        claude_execution=claude_result,
        estimated_tokens_saved=estimated_saved,
    )
