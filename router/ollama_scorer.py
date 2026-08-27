import json
import os
import re
from typing import List, Optional
from pydantic import BaseModel
import ollama

DEFAULT_TRIAGE_MODEL = "qwen2.5-coder:7b"


def triage_model() -> str:
    """Ollama triage model, overridable via ``OLLAMA_TRIAGE_MODEL``."""
    return os.environ.get("OLLAMA_TRIAGE_MODEL", DEFAULT_TRIAGE_MODEL)


class RoutingResult(BaseModel):
    target_files: List[str]
    confidence: float
    reasoning: str


def route_target_files(skeleton: str, user_prompt: str) -> RoutingResult:
    """
    Identify target files to modify based on user prompt using Ollama JSON output.
    Falls back to keyword heuristic if Ollama/JSON parsing fails.

    Args:
        skeleton: Text representation of codebase AST signatures (file paths + function/type signatures)
        user_prompt: User's change request

    Returns:
        RoutingResult with target_files, confidence, and reasoning
    """
    system_prompt = """
You are a code routing expert. Given a codebase skeleton with file paths and AST signatures,
and a user's change request, identify 1-3 target files that **must** be modified to implement the request.

Rules:
- Return ONLY valid JSON with the following schema:
  {
    "target_files": list[str] (1-3 file paths, relative paths matching the skeleton),
    "confidence": float (0.0 to 1.0 indicating confidence in the selection),
    "reasoning": string (short explanation why these files were selected)
  }
- Select at most 3 files, prefer 1-2 when obvious.
- Only include files that are explicitly relevant to the change.
- If multiple files are closely related, you may include them.
- If no obvious files found, return an empty list with low confidence.
"""

    user_message = f"""
Codebase skeleton:
{skeleton}

User change request:
{user_prompt}

Respond with JSON only.
"""

    try:
        response = ollama.chat(
            model=triage_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            format="json",
            options={
                "temperature": 0.0,
            },
        )

        raw_content = response.message.content
        content = raw_content.strip() if raw_content else "{}"
        parsed = json.loads(content)

        target_files = parsed.get("target_files", [])
        confidence = parsed.get("confidence", 0.5)
        reasoning = parsed.get("reasoning", "Parsed from Ollama JSON output.")

        # Validate constraints
        if not isinstance(target_files, list):
            target_files = []
        if len(target_files) > 3:
            target_files = target_files[:3]
        if not isinstance(confidence, float) or confidence < 0.0 or confidence > 1.0:
            confidence = 0.5
        if not isinstance(reasoning, str):
            reasoning = "Ollama returned invalid reasoning type."

        return RoutingResult(
            target_files=target_files,
            confidence=confidence,
            reasoning=reasoning,
        )

    except Exception as e:
        # Fallback to simple heuristic keyword matching
        return _keyword_heuristic(skeleton, user_prompt, str(e))


def _keyword_heuristic(skeleton: str, user_prompt: str, error: str) -> RoutingResult:
    """
    Simple fallback heuristic: count keyword matches per file from the skeleton.

    Expects each line in skeleton to start with file path.
    """
    # Extract keywords from user prompt: lowercase, remove punctuation
    keywords = set(re.findall(r"[a-zA-Z0-9_]+", user_prompt.lower()))
    # Filter out common stop words
    stop_words = {"the", "and", "for", "that", "with", "this", "change", "modify", "add", "remove", "file", "please", "want", "need"}
    keywords = keywords - stop_words

    if not keywords:
        return RoutingResult(
            target_files=[],
            confidence=0.0,
            reasoning=f"Ollama failed ({error}). No keywords extracted from prompt.",
        )

    # Parse skeleton into file blocks, count matches
    file_counts: dict[str, int] = {}
    current_file: Optional[str] = None

    for line in skeleton.splitlines():
        line = line.strip()
        if not line:
            continue
        # ast_extractor emits a "// <path>" header per file, then "- <signature>"
        # lines. Only header lines start a new file block; signature-line hits
        # are attributed to the current file so they can never fabricate a
        # pseudo-file entry (e.g. "- def tokenize()") in the selection.
        if line.startswith("//"):
            current_file = line[2:].strip()
            if current_file not in file_counts:
                file_counts[current_file] = 0
        elif current_file is None:
            continue
        # Count keyword matches in the line (path lines count too: a keyword
        # matching the file path is the strongest routing signal).
        line_lower = line.lower()
        for keyword in keywords:
            if keyword in line_lower:
                file_counts[current_file] += 1

    # Sort by count descending
    sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
    # Take top 3 with count > 0
    top_files = [f for f, cnt in sorted_files if cnt > 0][:3]

    if not top_files:
        return RoutingResult(
            target_files=[],
            confidence=0.0,
            reasoning=f"Ollama failed ({error}). No files matched any keywords.",
        )

    max_count = sorted_files[0][1]
    confidence = min(1.0, (max_count / (max(len(keywords), 1)))) * 0.8  # 0.8 max for heuristic
    reasoning = f"Fallback heuristic: Ollama failed ({error}). Ranked by keyword match count."

    return RoutingResult(
        target_files=top_files,
        confidence=confidence,
        reasoning=reasoning,
    )
