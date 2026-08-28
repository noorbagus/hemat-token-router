"""CLI subprocess dispatch for csmart (moved from ``router/dispatcher.py``).

Wave 2 (Fase 3) refactor: the old ``router/dispatcher.py`` combined the CLI
subprocess dispatch with the proxy engine. This module owns the CLI dispatch
side so ``router/dispatcher.py`` can become the pure FastAPI reverse-proxy
engine.

Frozen public API (CONTRACTS.md §5):

    dispatch_claude(files, prompt, gate_info, dry_run=False, timeout=600.0) -> DispatchResult

``gate_info`` is typed as ``router.gate.GateResult`` (NOT a local duplicate).
F-05: ``timeout`` is threaded through to ``subprocess.run`` and a
``TimeoutExpired`` produces a clean error result instead of a hang.
F-06: the duplicate ``GateResult`` class that used to live here is deleted;
      we consume ``GateResult.status`` / ``GateResult.reason`` (never
      ``.message``) and drop the old ``fallback_model`` logic — the model
      comes from the environment (``ANTHROPIC_MODEL`` etc.), not from the gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

from router.gate import GateResult
from router.logger import CLI_DISPATCH, logger

# Hardcoded gateway credentials path (unchanged from the old dispatcher).
GATEWAY_ENV_PATH = "/Volumes/Xugab/LAB/PrivateLink/credentials/.env"
GATEWAY_BASE_URL = "https://ark.talaga.my.id"


class DispatchResult(BaseModel):
    """Result of a Claude CLI dispatch invocation.

    Field names are frozen (CONTRACTS.md §5 + ``router/report.py`` /
    ``csmart.py`` depend on them exactly): ``exit_code``, ``duration_ms``,
    ``cost_usd``, ``session_id``, ``result_excerpt``, ``dry_run``.
    """

    exit_code: int
    duration_ms: int
    cost_usd: Optional[float]
    session_id: Optional[str]
    result_excerpt: Optional[str]
    dry_run: bool


def read_file_content(file_path: str) -> str:
    """Read the full content of a file (utf-8)."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def dispatch_claude(
    files: List[str],
    prompt: str,
    gate_info: GateResult,
    dry_run: bool = False,
    timeout: float = 600.0,
) -> DispatchResult:
    """Dispatch a Claude CLI request with pre-loaded file context.

    Args:
        files: List of file paths to include in the preloaded context.
        prompt: The user's original task prompt.
        gate_info: Gate result from ``router.gate``; only ``status`` and
            ``reason`` are consumed.
        dry_run: If True, compose everything but never spawn a subprocess.
        timeout: Maximum seconds to wait for the Claude subprocess
            (F-05). A ``TimeoutExpired`` returns a clean error result.

    Returns:
        ``DispatchResult`` with execution metadata.
    """
    # Step 1: read all selected files.
    file_contents: List[str] = []
    for file_path in files:
        content = read_file_content(file_path)
        file_contents.append(f"--- FILE: {file_path} ---\n{content}\n")

    context_section = "\n".join(file_contents)

    # Step 2: compose the final prompt.
    prompt_parts: List[str] = [
        f"USER TASK:\n{prompt}\n",
        f"\n--- PRELOADED FILE CONTEXT ---\n{context_section}",
        "\n--- INSTRUCTIONS ---",
        "do NOT execute search tools (grep, find, ls) as full source files are pre-loaded above",
    ]

    if gate_info.status == "fallback":
        prompt_parts.append(
            f"\n\nGATEWAY NOTICE: Falling back. Reason: {gate_info.reason}"
        )
    elif gate_info.status == "blocked":
        prompt_parts.append(
            f"\n\nGATEWAY NOTICE: Request blocked by gateway. Reason: {gate_info.reason}"
        )

    final_prompt = "\n".join(prompt_parts)

    error: Optional[str] = None
    result: DispatchResult

    # Step 3: dry-run exits before any subprocess.
    if dry_run:
        result = DispatchResult(
            exit_code=0,
            duration_ms=0,
            cost_usd=None,
            session_id=None,
            result_excerpt=f"Dry run: composed prompt with {len(files)} files, {len(final_prompt)} chars",
            dry_run=True,
        )
    else:
        # Step 4: load gateway environment + auth token.
        load_dotenv(GATEWAY_ENV_PATH)
        auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
        if not auth_token:
            result = DispatchResult(
                exit_code=1,
                duration_ms=0,
                cost_usd=None,
                session_id=None,
                result_excerpt="Missing ANTHROPIC_AUTH_TOKEN in gateway .env",
                dry_run=False,
            )
            error = "Missing ANTHROPIC_AUTH_TOKEN in gateway .env"
        else:
            cmd = [
                "claude",
                "-p",
                final_prompt,
                "--output-format",
                "json",
                "--max-turns",
                "1",
            ]

            env = os.environ.copy()
            env["ANTHROPIC_AUTH_TOKEN"] = auth_token
            env["ANTHROPIC_BASE_URL"] = GATEWAY_BASE_URL
            # The model comes from the environment (ANTHROPIC_MODEL etc.); the
            # gate no longer carries a fallback_model (F-06).

            # Step 5: execute and measure.
            start_time = time.time()
            try:
                subprocess_result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                duration_ms = int((time.time() - start_time) * 1000)
                result = DispatchResult(
                    exit_code=1,
                    duration_ms=duration_ms,
                    cost_usd=None,
                    session_id=None,
                    result_excerpt=f"Claude dispatch timed out after {timeout}s",
                    dry_run=False,
                )
                error = f"Claude dispatch timed out after {timeout}s"
            except Exception as exc:  # noqa: BLE001 - surface any invocation failure
                duration_ms = int((time.time() - start_time) * 1000)
                result = DispatchResult(
                    exit_code=1,
                    duration_ms=duration_ms,
                    cost_usd=None,
                    session_id=None,
                    result_excerpt=f"Exception invoking Claude: {str(exc)}",
                    dry_run=False,
                )
                error = str(exc)[:200]
            else:
                duration_ms = int((time.time() - start_time) * 1000)

                # Step 6: parse output.
                exit_code = subprocess_result.returncode
                cost_usd: Optional[float] = None
                session_id: Optional[str] = None
                result_excerpt: Optional[str] = None

                if subprocess_result.stdout:
                    try:
                        output_json: dict[str, Any] = json.loads(
                            subprocess_result.stdout
                        )
                        cost_usd = output_json.get("cost_usd")
                        session_id = output_json.get("session_id")
                        content = output_json.get("content", "")
                        if content:
                            content_excerpt = content[:500]
                            if len(content) > 500:
                                content_excerpt += "..."
                            result_excerpt = content_excerpt
                    except json.JSONDecodeError:
                        stdout_excerpt = subprocess_result.stdout[:500]
                        if len(subprocess_result.stdout) > 500:
                            stdout_excerpt += "..."
                        result_excerpt = stdout_excerpt
                elif subprocess_result.stderr:
                    stderr_excerpt = f"stderr: {subprocess_result.stderr[:500]}"
                    if len(subprocess_result.stderr) > 500:
                        stderr_excerpt += "..."
                    result_excerpt = stderr_excerpt

                result = DispatchResult(
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    cost_usd=cost_usd,
                    session_id=session_id,
                    result_excerpt=result_excerpt,
                    dry_run=False,
                )

    logger.log(
        CLI_DISPATCH,
        files_count=len(files),
        prompt_len=len(final_prompt),
        gate_status=gate_info.status,
        dry_run=result.dry_run,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        cost_usd=result.cost_usd,
        session_id=result.session_id,
        error=error,
    )

    return result
