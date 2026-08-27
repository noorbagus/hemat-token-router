"""Path validation helpers for safe file access (anti path-traversal).

Frozen contract at Wave 0 — see ``CONTRACTS.md``. Every path read from
external input (Ollama-selected files, tool_shadow args) MUST be validated
through :func:`resolve_under_base` before touching the filesystem.
"""

from __future__ import annotations

from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a path resolves outside the allowed base directory."""


def resolve_under_base(path: str | Path, base_dir: str | Path = ".") -> Path:
    """Resolve *path* to a real absolute path guaranteed inside *base_dir*.

    Symlink-aware (``Path.resolve``). Rejects ``..`` escapes, absolute paths
    outside *base_dir*, and symlinks that point outside. A missing file whose
    location is inside *base_dir* resolves normally (no error).

    Args:
        path: Raw path as provided (relative or absolute).
        base_dir: Allowed root. Defaults to the current working directory.

    Returns:
        The resolved absolute path, inside *base_dir*.

    Raises:
        PathTraversalError: If the path escapes *base_dir*.
    """
    base = Path(base_dir).resolve()
    raw = Path(path)
    if not raw.is_absolute():
        raw = base / raw
    candidate = raw.resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise PathTraversalError(
            f"path {str(path)!r} resolves outside base dir {str(base)!r}"
        ) from None
    return candidate


def is_within(path: str | Path, base_dir: str | Path = ".") -> bool:
    """Return True if *path* resolves inside *base_dir* (never raises)."""
    try:
        resolve_under_base(path, base_dir)
    except (PathTraversalError, OSError):
        return False
    return True
