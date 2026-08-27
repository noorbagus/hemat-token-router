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
    "reasoning": string, short, ≤10 words (brief explanation why these files were selected)
  }
- Select at most 3 files, prefer 1-2 when obvious.
- Only include files that are explicitly relevant to the change.
- If multiple files are closely related, you may include them.
- If no obvious files found, return an empty list with low confidence.
- Output minified single-line JSON — no newlines, no indentation, no extra whitespace.
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
            keep_alive=-1,
            options={
                "temperature": 0.0,
                "num_ctx": 8192,
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
        # Cap reasoning to keep routed JSON small (decode-latency win).
        elif len(reasoning) > 120:
            reasoning = reasoning[:117] + "..."

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
    Robust fallback heuristic: weighted keyword matching per file from the skeleton.

    Expects each line in skeleton to start with file path (// path) followed by
    signature lines (- signature). Weighting:
    - Match on file path: 3 points
    - Match on function/class name: 2 points
    - Match on signature content: 1 point
    - Splits camel_case/snake_case identifiers into sub-keywords for better matching
    """
    # Expanded stop words - common English/development words that don't help routing
    stop_words = {
        "the", "and", "for", "that", "with", "this", "change", "modify", "add", "remove",
        "file", "please", "want", "need", "fix", "bug", "error", "issue", "problem",
        "refactor", "improve", "update", "new", "function", "class", "method", "code",
        "implement", "feature", "make", "should", "can", "will", "would", "could",
        "has", "have", "been", "done", "get", "set", "put", "let", "one", "two",
        "into", "out", "up", "down", "over", "under", "from", "to", "a", "an",
        "in", "on", "at", "by", "of", "it", "is", "are", "was", "were", "be",
        "being", "been", "do", "does", "so", "not", "no", "yes", "but", "or",
        "if", "then", "else", "when", "what", "where", "why", "how", "all",
        "any", "some", "more", "most", "less", "many", "much", "few", "little"
    }

    # Extract all tokens from prompt, split camel_case/snake_case into sub-keywords
    def split_identifier(token: str) -> list[str]:
        """Split camelCase/snake_case into individual keywords."""
        # Split snake_case
        parts = token.split("_")
        # Split camelCase
        result = []
        for part in parts:
            if len(part) <= 2:
                result.append(part)
                continue
            # Split on capital letters
            matches = re.findall(r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))', part)
            if matches:
                result.extend([m.lower() for m in matches])
            else:
                result.append(part.lower())
        return result

    # Extract all tokens from prompt
    raw_tokens = set(re.findall(r"[a-zA-Z0-9_]+", user_prompt.lower()))
    # Expand into keywords by splitting identifiers
    keywords = set()
    for token in raw_tokens:
        if len(token) <= 2 or token.lower() in stop_words:
            continue
        keywords.add(token.lower())
        for sub in split_identifier(token):
            if len(sub) > 2 and sub.lower() not in stop_words:
                keywords.add(sub.lower())

    keywords = sorted(keywords)  # noqa

    if not keywords:
        return RoutingResult(
            target_files=[],
            confidence=0.0,
            reasoning=f"Ollama failed ({error}). No keywords extracted from prompt.",
        )

    # Parse skeleton into file blocks, count weighted matches
    file_weights: dict[str, int] = {}
    current_file: Optional[str] = None

    for line in skeleton.splitlines():
        line = line.strip()
        if not line:
            continue

        # ast_extractor emits a "// <path>" header per file
        if line.startswith("//"):
            current_file = line[2:].strip()
            if current_file not in file_weights:
                file_weights[current_file] = 0
            # File path matches get higher weight (3x)
            line_lower = line.lower()
            for keyword in keywords:
                if keyword in line_lower:
                    file_weights[current_file] += 3
            continue

        if current_file is None:
            continue

        # Signature lines start with "- " - function/class names get 2x, rest 1x
        line_lower = line.lower()
        is_signature = line.startswith("- ")
        weight = 2 if is_signature else 1
        for keyword in keywords:
            if keyword in line_lower:
                file_weights[current_file] += weight

    # Sort by total weight descending
    sorted_files = sorted(file_weights.items(), key=lambda x: x[1], reverse=True)
    # Take top 3 with weight > 0
    top_files = [f for f, w in sorted_files if w > 0][:3]

    if not top_files:
        return RoutingResult(
            target_files=[],
            confidence=0.0,
            reasoning=f"Ollama failed ({error}). No files matched any keywords.",
        )

    # Improved confidence calculation:
    # - Normalize by total possible points (3 points per keyword)
    # - Cap at 0.8 to reflect heuristic uncertainty
    # - Never exceed 1.0
    max_weight = sorted_files[0][1]
    total_possible = 3 * len(keywords)
    confidence = min(0.8, max_weight / total_possible if total_possible > 0 else 0.0)

    # Ensure confidence is within valid bounds
    confidence = max(0.0, min(0.8, confidence))

    reasoning = (
        f"Fallback heuristic: Ollama failed ({error}). "
        f"Ranked by weighted keyword matching (file path = 3x, signature = 2x)."
    )

    return RoutingResult(
        target_files=top_files,
        confidence=confidence,
        reasoning=reasoning,
    )
