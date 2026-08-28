"""Hermetic tests for router.tool_shadow exploration tool executor.

No live Ollama / network: ``ollama.chat`` is patched where the summarize path
is exercised. All filesystem work happens under pytest's ``tmp_path``.
"""

import asyncio
from types import SimpleNamespace

import pytest

from router.tool_shadow import (
    MAX_OUTPUT_CHARS,
    SUMMARIZE_THRESHOLD,
    TOOL_NAMES,
    execute_local_tool,
    summarize_exploration,
)


def _run(coro):
    """Run a coroutine to completion with a fresh event loop."""
    return asyncio.run(coro)


@pytest.fixture
def sample_tree(tmp_path):
    """Build a small project tree: src/a.py, src/pkg/b.py, readme.txt."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    pkg = src / "pkg"
    pkg.mkdir()
    (pkg / "b.py").write_text("class Bar:\n    def baz(self):\n        pass\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("hello world", encoding="utf-8")
    return tmp_path


def test_tool_names_contract():
    """TOOL_NAMES matches the frozen contract exactly."""
    assert TOOL_NAMES == ("GlobTool", "GrepTool", "View", "LS", "read_file", "FileRead")


def test_view_reads_file(sample_tree):
    out = _run(execute_local_tool("View", {"file_path": "src/a.py"}, base_dir=sample_tree))
    assert "def foo" in out
    assert "return 1" in out


def test_alternate_reader_names(sample_tree):
    out1 = _run(execute_local_tool("read_file", {"path": "src/a.py"}, base_dir=sample_tree))
    out2 = _run(execute_local_tool("FileRead", {"file_path": "src/a.py"}, base_dir=sample_tree))
    assert "def foo" in out1
    assert "def foo" in out2


def test_ls_lists_entries(sample_tree):
    out = _run(execute_local_tool("LS", {"path": "src"}, base_dir=sample_tree))
    assert "a.py (file)" in out
    assert "pkg (dir)" in out


def test_ls_lists_root(sample_tree):
    out = _run(execute_local_tool("LS", {"directory": "."}, base_dir=sample_tree))
    assert "src (dir)" in out
    assert "readme.txt (file)" in out


def test_glob_finds_nested_py(sample_tree):
    out = _run(execute_local_tool("GlobTool", {"pattern": "**/*.py"}, base_dir=sample_tree))
    assert "src/a.py" in out
    assert "src/pkg/b.py" in out


def test_glob_with_glob_key(sample_tree):
    out = _run(execute_local_tool("GlobTool", {"glob": "**/*.txt"}, base_dir=sample_tree))
    assert "readme.txt" in out
    assert "a.py" not in out


def test_grep_returns_hits(sample_tree):
    out = _run(execute_local_tool("GrepTool", {"pattern": "def ", "path": "src"}, base_dir=sample_tree))
    assert "src/a.py:1: def foo" in out
    assert "src/pkg/b.py:2:" in out
    assert "def baz" in out


def test_grep_no_match(sample_tree):
    out = _run(execute_local_tool("GrepTool", {"pattern": "zzzz_no_match", "path": "src"}, base_dir=sample_tree))
    assert "no matches" in out


def test_traversal_relative_rejected(tmp_path):
    """'../secret.txt' must not be read; an ERROR string is returned instead."""
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("TOP SECRET SENTINEL", encoding="utf-8")
    out = _run(execute_local_tool("View", {"file_path": "../secret.txt"}, base_dir=tmp_path))
    assert out.startswith("ERROR")
    assert "TOP SECRET SENTINEL" not in out


def test_traversal_absolute_rejected(tmp_path):
    """An absolute path outside base_dir must not be read."""
    out = _run(execute_local_tool("View", {"file_path": "/etc/hosts"}, base_dir=tmp_path))
    assert out.startswith("ERROR")
    assert "127.0.0.1" not in out  # the outside file's content never appears


def test_traversal_rejected_ls(tmp_path):
    out = _run(execute_local_tool("LS", {"path": "../"}, base_dir=tmp_path))
    assert out.startswith("ERROR")


def test_glob_grep_via_symlink_alias_base(tmp_path):
    """base_dir reached through a symlink alias must still yield relative paths.

    Regression: on macOS, ``tempfile.TemporaryDirectory()`` returns an
    unresolved ``/var`` path whose ``resolve()`` is ``/private/var``. Paths
    validated through ``resolve_under_base`` are rooted at the resolved base, so
    a naive ``relative_to(base_dir)`` raised and matches were dropped.
    """
    real = tmp_path / "real"
    real.mkdir()
    (real / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported on this platform")
    out_glob = _run(execute_local_tool("GlobTool", {"pattern": "**/*.py"}, base_dir=alias))
    assert "a.py" in out_glob
    assert out_glob.startswith("/") is False  # relative, not absolute
    out_grep = _run(execute_local_tool("GrepTool", {"pattern": "def ", "path": "."}, base_dir=alias))
    assert "a.py:1: def a" in out_grep


def test_unknown_tool(sample_tree):
    out = _run(execute_local_tool("UnknownTool", {}, base_dir=sample_tree))
    assert "ERROR" in out
    assert "UnknownTool" in out


def test_view_truncates_long_output(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("A" * (MAX_OUTPUT_CHARS + 1000), encoding="utf-8")
    out = _run(execute_local_tool("View", {"file_path": "big.txt"}, base_dir=tmp_path))
    assert len(out) <= MAX_OUTPUT_CHARS
    assert "truncated" in out


def test_grep_truncates_long_output(tmp_path):
    big = tmp_path / "big.py"
    # A single huge matching line forces grep output beyond the bound.
    big.write_text("def " + ("A" * (MAX_OUTPUT_CHARS + 1000)), encoding="utf-8")
    out = _run(execute_local_tool("GrepTool", {"pattern": "def ", "path": "."}, base_dir=tmp_path))
    assert len(out) <= MAX_OUTPUT_CHARS
    assert "truncated" in out


def test_summarize_short_unchanged(monkeypatch):
    """Short output returns unchanged and never touches ollama.chat."""

    def _fail(*_args, **_kwargs):
        raise AssertionError("ollama.chat must not be called for short output")

    monkeypatch.setattr("ollama.chat", _fail)
    short = "x" * SUMMARIZE_THRESHOLD  # exactly the threshold -> unchanged
    out = _run(summarize_exploration("GrepTool", short))
    assert out == short


def test_summarize_long_mocked(monkeypatch):
    """Long output with ollama.chat patched returns the mock summary."""

    def _fake_chat(**kwargs):
        return SimpleNamespace(message=SimpleNamespace(content="mock summary"))

    monkeypatch.setattr("ollama.chat", _fake_chat)
    long_out = "y" * (SUMMARIZE_THRESHOLD + 1)
    out = _run(summarize_exploration("GrepTool", long_out))
    assert out == "mock summary"


def test_summarize_long_dict_response(monkeypatch):
    """Handle an ollama.chat response shaped as a dict too."""

    def _fake_chat(**kwargs):
        return {"message": {"content": "dict summary"}}

    monkeypatch.setattr("ollama.chat", _fake_chat)
    long_out = "q" * (SUMMARIZE_THRESHOLD + 1)
    out = _run(summarize_exploration("GrepTool", long_out))
    assert out == "dict summary"


def test_summarize_long_raising(monkeypatch):
    """ollama.chat raising -> truncated raw output, no exception."""

    def _raise(*_args, **_kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("ollama.chat", _raise)
    long_out = "z" * (SUMMARIZE_THRESHOLD + 1)
    out = _run(summarize_exploration("GrepTool", long_out))
    assert "z" * SUMMARIZE_THRESHOLD in out
    assert "truncated" in out


@pytest.mark.parametrize("tool_name", ["View", "read_file", "FileRead"])
def test_reader_long_passthrough_no_ollama(monkeypatch, tool_name):
    """Reader tool output over the threshold passes through; ollama never runs."""

    def _fail(*_args, **_kwargs):
        raise AssertionError("ollama.chat must not be called for reader tools")

    monkeypatch.setattr("ollama.chat", _fail)
    long_out = "s" * (SUMMARIZE_THRESHOLD + 1)
    out = _run(summarize_exploration(tool_name, long_out))
    assert out == long_out


@pytest.mark.parametrize("tool_name", ["View", "read_file", "FileRead"])
def test_reader_over_max_still_bounded(monkeypatch, tool_name):
    """Reader tool output over MAX_OUTPUT_CHARS is bounded, never summarized."""

    def _fail(*_args, **_kwargs):
        raise AssertionError("ollama.chat must not be called for reader tools")

    monkeypatch.setattr("ollama.chat", _fail)
    huge = "s" * (MAX_OUTPUT_CHARS + 1000)
    out = _run(summarize_exploration(tool_name, huge))
    assert len(out) <= MAX_OUTPUT_CHARS
    assert "truncated" in out


def test_non_reader_long_calls_ollama(monkeypatch):
    """Non-reader tool output over the threshold still calls ollama.chat."""

    calls = {"count": 0}

    def _fake_chat(**kwargs):
        calls["count"] += 1
        return {"message": {"content": "mock summary"}}

    monkeypatch.setattr("ollama.chat", _fake_chat)
    long_out = "g" * (SUMMARIZE_THRESHOLD + 1)
    out = _run(summarize_exploration("GrepTool", long_out))
    assert out == "mock summary"
    assert calls["count"] == 1


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_short_unchanged_any_tool(monkeypatch, tool_name):
    """Short output (<= threshold) passes through unchanged for every tool."""

    def _fail(*_args, **_kwargs):
        raise AssertionError("ollama.chat must not be called for short output")

    monkeypatch.setattr("ollama.chat", _fail)
    short = "c" * SUMMARIZE_THRESHOLD
    out = _run(summarize_exploration(tool_name, short))
    assert out == short


def test_non_reader_raising_falls_back_truncated(monkeypatch):
    """Non-reader: ollama.chat raising -> truncated raw output, never raises."""

    def _raise(*_args, **_kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("ollama.chat", _raise)
    long_out = "t" * (SUMMARIZE_THRESHOLD + 1)
    out = _run(summarize_exploration("GlobTool", long_out))
    assert "t" * SUMMARIZE_THRESHOLD in out
    assert "truncated" in out
