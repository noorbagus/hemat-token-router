import subprocess
import time
import os
import json
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv


class DispatchResult(BaseModel):
    """Result from Claude dispatch invocation"""
    exit_code: int
    duration_ms: int
    cost_usd: Optional[float]
    session_id: Optional[str]
    result_excerpt: Optional[str]
    dry_run: bool


class GateResult(BaseModel):
    """Simplified gate result from gateway check"""
    status: str  # "allowed", "fallback", "blocked"
    message: str
    fallback_model: Optional[str] = None


def read_file_content(file_path: str) -> str:
    """Read full content of a file"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def dispatch_claude(
    files: List[str],
    prompt: str,
    gate_info: GateResult,
    dry_run: bool = False
) -> DispatchResult:
    """
    Dispatch a Claude CLI request with pre-loaded file context.

    Args:
        files: List of file paths to include in context
        prompt: User's original task prompt
        gate_info: Result from gateway checking
        dry_run: If True, compose everything but don't invoke Claude

    Returns:
        DispatchResult with execution metadata
    """
    # Step 1: Read all selected files
    file_contents = []
    for file_path in files:
        content = read_file_content(file_path)
        file_contents.append(f"--- FILE: {file_path} ---\n{content}\n")

    context_section = "\n".join(file_contents)

    # Step 2: Compose final prompt
    prompt_parts = [
        f"USER TASK:\n{prompt}\n",
        f"\n--- PRELOADED FILE CONTEXT ---\n{context_section}",
        "\n--- INSTRUCTIONS ---",
        "do NOT execute search tools (grep, find, ls) as full source files are pre-loaded above",
    ]

    # Add gate warning if needed
    if gate_info.status == "fallback":
        prompt_parts.append(f"\n\nGATEWAY NOTICE: Falling back to third-party model. Reason: {gate_info.message}")
    elif gate_info.status == "blocked":
        prompt_parts.append(f"\n\nGATEWAY NOTICE: Request blocked by gateway. Reason: {gate_info.message}")

    final_prompt = "\n".join(prompt_parts)

    # Step 3: Dry run exit early
    if dry_run:
        return DispatchResult(
            exit_code=0,
            duration_ms=0,
            cost_usd=None,
            session_id=None,
            result_excerpt=f"Dry run: composed prompt with {len(files)} files, {len(final_prompt)} chars",
            dry_run=True
        )

    # Step 4: Load gateway environment
    gateway_env_path = "/Volumes/Xugab/LAB/PrivateLink/credentials/.env"
    load_dotenv(gateway_env_path)

    # Get auth token and configure third-party model
    auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
    if not auth_token:
        return DispatchResult(
            exit_code=1,
            duration_ms=0,
            cost_usd=None,
            session_id=None,
            result_excerpt="Missing ANTHROPIC_AUTH_TOKEN in gateway .env",
            dry_run=False
        )

    # Build command
    cmd = [
        "claude",
        "-p", final_prompt,
        "--output-format", "json",
        "--max-turns", "1"
    ]

    # Prepare environment with model config for third-party
    env = os.environ.copy()
    env["ANTHROPIC_AUTH_TOKEN"] = auth_token
    env["ANTHROPIC_BASE_URL"] = "https://ark.talaga.my.id"
    # Model selection based on gate info
    if gate_info.status == "fallback" and gate_info.fallback_model:
        env["ANTHROPIC_MODEL"] = gate_info.fallback_model

    # Step 5: Execute and measure
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=False
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return DispatchResult(
            exit_code=1,
            duration_ms=duration_ms,
            cost_usd=None,
            session_id=None,
            result_excerpt=f"Exception invoking Claude: {str(e)}",
            dry_run=False
        )

    duration_ms = int((time.time() - start_time) * 1000)

    # Step 6: Parse output
    exit_code = result.returncode
    cost_usd: Optional[float] = None
    session_id: Optional[str] = None
    result_excerpt: Optional[str] = None

    import json
    if result.stdout:
        try:
            output_json = json.loads(result.stdout)
            cost_usd = output_json.get("cost_usd")
            session_id = output_json.get("session_id")
            # Take first 500 chars as excerpt
            content = output_json.get("content", "")
            if content:
                result_excerpt = content[:500]
                if len(content) > 500 and result_excerpt:
                    result_excerpt += "..."
        except json.JSONDecodeError:
            result_excerpt = result.stdout[:500]
            if len(result.stdout) > 500 and result_excerpt:
                result_excerpt += "..."

    elif result.stderr:
        result_excerpt = f"stderr: {result.stderr[:500]}"
        if len(result.stderr) > 500:
            result_excerpt = (result_excerpt or "") + "..."

    return DispatchResult(
        exit_code=exit_code,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        session_id=session_id,
        result_excerpt=result_excerpt,
        dry_run=False
    )
