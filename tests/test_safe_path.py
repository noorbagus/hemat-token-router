"""Hermetic tests for router/safe_path.py (path-traversal guard)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.safe_path import PathTraversalError, is_within, resolve_under_base


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    return p


def test_relative_within_passes(tmp_path):
    target = _touch(tmp_path / "src" / "a.py")
    assert resolve_under_base("src/a.py", tmp_path) == target
    assert resolve_under_base(Path("src/a.py"), tmp_path) == target


def test_dotdot_normalization_passes(tmp_path):
    target = _touch(tmp_path / "src" / "b.py")
    assert resolve_under_base("./src/../src/b.py", tmp_path) == target


def test_missing_file_under_base_resolves(tmp_path):
    assert resolve_under_base("not-there.py", tmp_path) == (tmp_path / "not-there.py").resolve()
    assert is_within("not-there.py", tmp_path)


def test_absolute_inside_passes(tmp_path):
    target = _touch(tmp_path / "ok.txt")
    assert resolve_under_base(str(target), tmp_path) == target


def test_absolute_outside_raises(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_under_base(str(tmp_path.parent), tmp_path)
    assert not is_within(str(tmp_path.parent), tmp_path)


def test_parent_escape_raises(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_under_base("../secret.txt", tmp_path)
    assert not is_within("../secret.txt", tmp_path)


def test_symlink_pointing_outside_raises(tmp_path):
    link = tmp_path / "escape-link"
    link.symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(PathTraversalError):
        resolve_under_base("escape-link", tmp_path)
    assert not is_within("escape-link", tmp_path)


def test_base_with_trailing_slash(tmp_path):
    target = _touch(tmp_path / "ok.txt")
    assert resolve_under_base("ok.txt", str(tmp_path) + os.sep) == target


def test_is_within_never_raises(tmp_path):
    # empty path resolves to base itself → within, no exception
    assert is_within("", tmp_path) is True
    assert is_within("../escape", tmp_path) is False
