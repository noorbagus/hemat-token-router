"""
Budget-aware gate that filters candidate files based on confidence and token budget.
Single responsibility: apply threshold and budget constraints to routing results.
"""

import os
from typing import List
from pydantic import BaseModel

from router.logger import logger, GATE_APPLIED
from .ollama_scorer import RoutingResult


class GateResult(BaseModel):
    """Result of gate application after confidence and budget filtering."""
    status: str  # "pass", "fallback", "blocked"
    selected_files: List[str]
    selected_bytes: int
    estimated_tokens: int
    dropped_count: int
    reason: str


def apply_gate(
    result: RoutingResult,
    threshold: float,
    budget_tokens: int,
    base_dir: str = "",
) -> GateResult:
    """
    Apply confidence threshold and token budget gate to routing result.

    Rules:
    1. Filter files by confidence >= threshold (if above, all pass threshold check)
    2. Sort files by confidence descending (highest first)
    3. Accumulate file sizes, stop when adding next file would exceed budget
    4. Never truncate mid-file - drop whole files that don't fit to preserve syntax

    Token estimation: 1 token ≈ 4 characters/bytes (common LLM approximation)

    Status codes:
    - "pass": All candidate files pass confidence and fit within budget
    - "fallback": Some files failed confidence OR budget exceeded, but some fit
    - "blocked": No files pass confidence OR no files fit in budget

    Args:
        result: RoutingResult from ollama_scorer
        threshold: Minimum confidence to pass
        budget_tokens: Maximum estimated tokens allowed
        base_dir: Optional base directory to resolve relative file paths

    Returns:
        GateResult with status and selected files
    """
    BYTES_PER_TOKEN = 4
    budget_bytes = budget_tokens * BYTES_PER_TOKEN

    gate_result: GateResult

    # Case 1: No candidate files from routing
    if not result.target_files:
        gate_result = GateResult(
            status="blocked",
            selected_files=[],
            selected_bytes=0,
            estimated_tokens=0,
            dropped_count=0,
            reason="No candidate files provided by routing.",
        )
    else:
        # Get file sizes for all candidates, skip any files that don't exist
        file_sizes: List[tuple[str, int, float]] = []
        for file_path in result.target_files:
            # Resolve path relative to base_dir if provided
            if base_dir and not os.path.isabs(file_path):
                full_path = os.path.join(base_dir, file_path)
            else:
                full_path = file_path

            try:
                if os.path.exists(full_path):
                    size = os.path.getsize(full_path)
                    file_sizes.append((file_path, size, result.confidence))
                # Note: ollama_scorer already gives overall confidence, per-file not available
                # So all files in result get same confidence ranking
            except OSError:
                # Skip unreadable files
                continue

        # Filter by confidence threshold
        passing_files = [fs for fs in file_sizes if fs[2] >= threshold]

        if not passing_files:
            gate_result = GateResult(
                status="blocked",
                selected_files=[],
                selected_bytes=0,
                estimated_tokens=0,
                dropped_count=len(result.target_files),
                reason=f"All {len(result.target_files)} candidate files have confidence {result.confidence:.2f} < threshold {threshold:.2f}.",
            )
        else:
            # Sort by confidence descending (already same confidence, but maintain input order if same)
            passing_files.sort(key=lambda x: x[2], reverse=True)

            # Accumulate until budget exceeded, add whole files only
            selected: List[str] = []
            total_bytes = 0

            for path, size, _ in passing_files:
                if total_bytes + size > budget_bytes:
                    # This file doesn't fit, stop (already sorted by confidence, drop the rest)
                    break
                selected.append(path)
                total_bytes += size

            estimated_tokens = total_bytes // BYTES_PER_TOKEN
            dropped = len(passing_files) - len(selected)

            # Determine status
            if len(selected) == len(passing_files):
                # All passing files fit
                if result.confidence >= threshold and dropped == 0:
                    status = "pass"
                    reason = f"All {len(selected)} candidate files pass confidence {result.confidence:.2f} >= {threshold:.2f} and fit within budget ({estimated_tokens} <= {budget_tokens} tokens)."
                else:
                    status = "fallback"
                    reason = f"Some candidate files fit within budget after filtering. Selected {len(selected)} of {len(passing_files)} passing files."
            else:
                # Budget exceeded, some selected
                status = "fallback"
                reason = f"Budget exceeded after selecting {len(selected)} files. Dropped {dropped} higher-confidence files that didn't fit. Estimated {estimated_tokens} tokens vs budget {budget_tokens}."

                # Edge case: nothing selected even first file is too big
                if not selected:
                    status = "blocked"
                    reason = f"Largest candidate file ({total_bytes + passing_files[0][1]} bytes) exceeds budget {budget_bytes} bytes ({budget_tokens} tokens)."

            gate_result = GateResult(
                status=status,
                selected_files=selected,
                selected_bytes=total_bytes,
                estimated_tokens=estimated_tokens,
                dropped_count=dropped + (len(result.target_files) - len(passing_files)),
                reason=reason,
            )

    logger.log(
        GATE_APPLIED,
        status=gate_result.status,
        candidates=len(result.target_files),
        selected_files=gate_result.selected_files,
        selected_count=len(gate_result.selected_files),
        selected_bytes=gate_result.selected_bytes,
        estimated_tokens=gate_result.estimated_tokens,
        dropped_count=gate_result.dropped_count,
        threshold=threshold,
        budget_tokens=budget_tokens,
        confidence=result.confidence,
        reason=gate_result.reason,
    )
    return gate_result


def hook_test_helper() -> int:
    """Test helper to verify graphify post-commit hook rebuilds the graph."""
    return 42
