"""Exploration tool executor for the csmart shadow loop.

Frozen contract at Wave 0 -- see ``CONTRACTS.md`` section 3.

Exposes two async entrypoints:

* :func:`execute_local_tool` runs a local stand-in for a Claude exploration
  tool (``GlobTool``, ``GrepTool``, ``View``, ``LS``, ``read_file``,
  ``FileRead``) against a *base_dir*-scoped sandbox. Every path read from
  ``tool_input`` is validated through :func:`router.safe_path.resolve_under_base`
  before touching the filesystem (anti path-traversal, QG-03 groundwork).
* :func:`summarize_exploration` optionally condenses large raw tool output via
  Ollama (``qwen2.5-coder:7b`` by default), keeping short outputs untouched.
  Reader-tool output (``View``, ``read_file``, ``FileRead``) is source code and
  passes through verbatim instead of being summarized (see the function's
  docstring).

All filesystem work runs in a worker thread via ``asyncio.to_thread`` so the
caller's event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

import ollama

from router.logger import TOOL_LOCAL_EXEC, TOOL_SUMMARIZE, logger
from router.safe_path import PathTraversalError, resolve_under_base

__all__ = [
    "MAX_OUTPUT_CHARS",
    "SUMMARIZE_THRESHOLD",
    "TOOL_NAMES",
    "execute_local_tool",
    "summarize_exploration",
]

# Tool names this module can shadow (contract: exact tuple).
TOOL_NAMES: tuple[str, ...] = ("GlobTool", "GrepTool", "View", "LS", "read_file", "FileRead")

# Bound any single tool result. Longer output is truncated with a note.
MAX_OUTPUT_CHARS = 20000
# Outputs longer than this go through Ollama summarization.
SUMMARIZE_THRESHOLD = 4000

_TRUNCATION_NOTE = "\n... [output truncated]"
_SUMMARIZE_SYSTEM_PROMPT = (
    "You are a concise codebase exploration summarizer. "
    "Condense the tool output into the key findings in a few short bullet points."
)
_DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"

_READER_TOOLS: frozenset[str] = frozenset(("View", "read_file", "FileRead"))


def _get_path(tool_input: dict, keys: tuple[str, ...] | None = None) -> str | None:
    """Return the first present path-ish value from *tool_input*.

    Key priority defaults to ``("path", "glob", "pattern", "file_path",
    "directory")``. Callers may pass a narrower ``keys`` tuple when a tool
    assigns specific meaning to each key (e.g. readers prefer ``file_path``).
    """
    key_order = keys or ("path", "glob", "pattern", "file_path", "directory")
    for key in key_order:
        value = tool_input.get(key)
        if value is not None:
            return str(value)
    return None


def _bounded(text: str) -> str:
    """Truncate *text* to at most :data:`MAX_OUTPUT_CHARS` chars with a note."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    keep = MAX_OUTPUT_CHARS - len(_TRUNCATION_NOTE)
    return text[:keep] + _TRUNCATION_NOTE


def _truncated(text: str) -> str:
    """Truncate *text* to :data:`SUMMARIZE_THRESHOLD` chars with a note."""
    return text[:SUMMARIZE_THRESHOLD] + _TRUNCATION_NOTE


def _resolve_or_error(path_str: str, base_dir: Path) -> Path | str:
    """Validate *path_str* via ``resolve_under_base``.

    Returns the resolved absolute :class:`Path` on success, or an ``ERROR:``
    message string on failure. Never raises for a traversal attempt.
    """
    try:
        return resolve_under_base(path_str, base_dir)
    except PathTraversalError:
        return f"ERROR: path outside base directory: {path_str}"
    except (OSError, ValueError, RuntimeError) as exc:  # pragma: no cover - defensive
        return f"ERROR: invalid path {path_str}: {exc}"


def _run_view(path_str: str, base_dir: Path) -> str:
    """Read a single file's text content (utf-8, lossy)."""
    resolved = _resolve_or_error(path_str, base_dir)
    if isinstance(resolved, str):
        return resolved
    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"ERROR: cannot read file {path_str}: {exc}"
    return _bounded(content)


def _run_ls(path_str: str, base_dir: Path) -> str:
    """List directory entries as ``name (dir|file)`` lines."""
    resolved = _resolve_or_error(path_str, base_dir)
    if isinstance(resolved, str):
        return resolved
    try:
        entries = sorted(resolved.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        return f"ERROR: cannot list directory {path_str}: {exc}"
    lines = []
    for entry in entries:
        kind = "dir" if entry.is_dir() else "file"
        lines.append(f"{entry.name} ({kind})")
    if not lines:
        return "(empty)"
    return _bounded("\n".join(lines))


def _rel_to_base(path: Path, base_dir: Path) -> str:
    """Return *path* relative to *base_dir*, handling symlink-alias bases.

    ``resolve_under_base`` returns candidates rooted at ``base_dir.resolve()``,
    so when *base_dir* is itself reached through a symlink (e.g. macOS
    ``/var`` -> ``/private/var``) a naive ``relative_to(base_dir)`` would raise.
    Prefer the resolved root, falling back to the raw base and then the
    absolute path only as a last resort.
    """
    for root in (base_dir.resolve(), base_dir):
        try:
            return str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)


def _run_glob(tool_input: dict, base_dir: Path) -> str:
    """Recursively match a glob pattern under a base_dir-scoped root."""
    pattern = tool_input.get("glob") or tool_input.get("pattern") or "**/*"
    pattern = str(pattern)
    if ".." in pattern:
        return "ERROR: glob pattern must not contain '..'"
    # Absolute patterns raise NotImplementedError on Python 3.11+; reject them
    # explicitly so a traversal attempt never surfaces as a 500 (review MAJOR).
    if pattern.startswith("/"):
        return "ERROR: glob pattern must be relative to the project root"
    subdir = str(tool_input.get("path") or tool_input.get("directory") or ".")
    resolved = _resolve_or_error(subdir, base_dir)
    if isinstance(resolved, str):
        return resolved
    try:
        if "/" in pattern or pattern.startswith("**"):
            matches = sorted(resolved.glob(pattern))
        else:
            matches = sorted(resolved.rglob(pattern))
    except (OSError, re.error, NotImplementedError) as exc:
        return f"ERROR: glob failed: {exc}"
    lines = []
    for match in matches:
        if match.is_file():
            lines.append(_rel_to_base(match, base_dir))
    if not lines:
        return "(no matches)"
    return _bounded("\n".join(lines))


def _run_grep(tool_input: dict, base_dir: Path) -> str:
    """Regex-search text files under a base_dir-scoped root.

    Returns ``file:line: content`` hits.
    """
    pattern_str = tool_input.get("pattern") or tool_input.get("glob")
    if not pattern_str:
        return "ERROR: no regex pattern provided for GrepTool"
    try:
        regex = re.compile(str(pattern_str))
    except re.error as exc:
        return f"ERROR: invalid regex pattern {pattern_str!r}: {exc}"
    subdir = str(tool_input.get("path") or tool_input.get("directory") or ".")
    resolved = _resolve_or_error(subdir, base_dir)
    if isinstance(resolved, str):
        return resolved
    try:
        files = sorted(resolved.rglob("*"))
    except OSError as exc:
        return f"ERROR: cannot search directory {subdir}: {exc}"
    hits: list[str] = []
    for file in files:
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                hits.append(f"{_rel_to_base(file, base_dir)}:{lineno}: {line.rstrip()}")
    if not hits:
        return "(no matches)"
    return _bounded("\n".join(hits))


def _normalize_tool_name(tool_name: str) -> str:
    """Strip whitespace and a trailing ``()`` artifact (``View()`` -> ``View``)."""
    return tool_name.strip().removesuffix("()").strip()


def _execute_local_tool_sync(tool_name: str, tool_input: dict, base_dir: Path) -> str:
    """Synchronous dispatch; executed in a worker thread by the async wrapper."""
    start = time.monotonic()
    tool_input = tool_input or {}
    name = _normalize_tool_name(tool_name)

    if name in _READER_TOOLS:
        path_str = _get_path(tool_input, ("file_path", "path", "directory"))
        if path_str is None:
            result = f"ERROR: no path provided for {tool_name}"
        else:
            result = _run_view(path_str, base_dir)
    elif name == "LS":
        path_str = _get_path(tool_input, ("path", "directory")) or "."
        result = _run_ls(path_str, base_dir)
    elif name == "GlobTool":
        result = _run_glob(tool_input, base_dir)
    elif name == "GrepTool":
        result = _run_grep(tool_input, base_dir)
    else:
        result = f"ERROR: unsupported tool: {tool_name}"

    logger.log(
        TOOL_LOCAL_EXEC,
        tool_name=name,
        status=("ok" if not result.startswith("ERROR: ") else "error"),
        chars=len(result),
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    return result


async def execute_local_tool(tool_name: str, tool_input: dict, base_dir: str | Path = ".") -> str:
    """Execute a local exploration tool against a base_dir-scoped sandbox.

    Args:
        tool_name: One of :data:`TOOL_NAMES` (``GlobTool``, ``GrepTool``,
            ``View``, ``LS``, ``read_file``, ``FileRead``).
        tool_input: Tool-specific arguments. Common keys: ``path``, ``glob``,
            ``pattern``, ``file_path``, ``directory``.
        base_dir: Allowed root directory; every path is validated to stay inside.

    Returns:
        Text output (file content / glob matches / grep hits / dir listing).
        A path-traversal attempt or an unknown tool returns an ``ERROR: ...``
        string rather than raising or reading outside *base_dir*.
    """
    return await asyncio.to_thread(_execute_local_tool_sync, tool_name, tool_input, Path(base_dir))


def _extract_message_content(response: object) -> str | None:
    """Pull text out of an ``ollama.chat``-shaped response (or a plain string)."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if content is not None:
                return str(content)
        content = response.get("content")
        if isinstance(content, str):
            return content
    message = getattr(response, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if content is not None:
            return str(content)
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    return None


async def summarize_exploration(tool_name: str, raw_output: str) -> str:
    """Summarize large non-reader tool output via Ollama; short output passes through.

    Outputs of length ``<= SUMMARIZE_THRESHOLD`` (4000) are returned unchanged
    without calling Ollama. Longer outputs are summarized with model
    ``OLLAMA_MODEL`` (default ``qwen2.5-coder:7b``) -- but only for non-reader
    tools (``GlobTool``, ``GrepTool``, ``LS``). Reader-tool output (``View``,
    ``read_file``, ``FileRead``) IS source code, so it is passed through
    verbatim (bounded to :data:`MAX_OUTPUT_CHARS`) instead of summarized. If
    Ollama is unavailable or raises, a truncated copy of *raw_output* is
    returned -- this function never raises.
    """
    start = time.monotonic()
    if len(raw_output) <= SUMMARIZE_THRESHOLD:
        result = raw_output
        decision = "passthrough_short"
        model = None
    elif _normalize_tool_name(tool_name) in _READER_TOOLS:
        # Reader output is source code: summarizing it can drop API signatures,
        # and the model fills the gaps with plausible-but-fictional identifiers
        # (e.g. `max_size`/`env_ttl_key` for the real `max_entries`/`ttl_seconds_provider`).
        # Preserve the exact text up to the hard bound -- see docs/ab-test-request-count.md #2.
        result = _bounded(raw_output)
        decision = "passthrough_reader"
        model = None
    else:
        model = os.environ.get("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=model,
                messages=[
                    {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Exploration tool: {tool_name}\n\n{raw_output}"},
                ],
                options={"temperature": 0.0},
            )
            content = _extract_message_content(response)
            if content:
                result = content
                decision = "summarize"
            else:
                result = _truncated(raw_output)
                decision = "fallback_truncated"
        except Exception:  # noqa: BLE001 - never propagate from the shadow loop
            result = _truncated(raw_output)
            decision = "fallback_truncated"

    logger.log(
        TOOL_SUMMARIZE,
        tool_name=_normalize_tool_name(tool_name),
        raw_chars=len(raw_output),
        decision=decision,
        result_chars=len(result),
        model=model,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    return result
