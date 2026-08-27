"""Hermetic tests for router/proxy.inject_context_to_messages (F-09 path safety).

Pure-function tests only: no network, no Ollama, no subprocess.
The path-validation base is ``.`` (CWD), so each test chdirs into ``tmp_path``
via the ``cwd_tmp`` fixture and restores the original CWD afterwards.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router.dispatcher import inject_context_to_messages


@pytest.fixture
def cwd_tmp(tmp_path):
    """chdir to tmp_path (so base '.' == tmp_path), restore after the test."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old_cwd)


def _user_message(content: str) -> dict:
    return {"role": "user", "content": content}


def _last_user_content(messages):
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            return msg["content"]
    return None


def _warned_about(caplog, needle: str) -> bool:
    return any(needle in r.getMessage() for r in caplog.records)


def test_relative_file_injected_into_last_user_message(cwd_tmp):
    src = cwd_tmp / "src"
    src.mkdir()
    (src / "a.py").write_text("def hello():\n    return 1\n")

    messages = [_user_message("fix the bug")]
    out = inject_context_to_messages(messages, ["src/a.py"])

    assert out is not messages
    last = _last_user_content(out)
    assert last is not None
    assert "def hello():" in last
    assert "--- FILE START: src/a.py ---" in last
    # original prompt is preserved before the injected block
    assert last.startswith("fix the bug")


def test_traversal_skipped_but_valid_files_injected(cwd_tmp, caplog):
    (cwd_tmp / "good.py").write_text("GOOD_CONTENT")

    messages = [_user_message("do it")]
    out = inject_context_to_messages(messages, ["../etc/passwd", "good.py"])

    last = _last_user_content(out)
    assert "GOOD_CONTENT" in last
    # the traversal path must NOT be read nor appear as a marker
    assert "../etc/passwd" not in last
    assert "root:" not in last
    assert _warned_about(caplog, "path traversal")


def test_absolute_path_outside_base_skipped(cwd_tmp, caplog):
    (cwd_tmp / "inside.txt").write_text("INSIDE")
    outside = cwd_tmp.parent / "outside-secret.txt"
    outside.write_text("OUTSIDE_SECRET")

    messages = [_user_message("go")]
    out = inject_context_to_messages(messages, [str(outside), "inside.txt"])

    last = _last_user_content(out)
    assert "INSIDE" in last
    assert "OUTSIDE_SECRET" not in last
    assert str(outside) not in last
    assert _warned_about(caplog, "path traversal")


def test_empty_selected_files_returns_messages_unchanged(cwd_tmp):
    messages = [_user_message("hello"), {"role": "assistant", "content": "ok"}]
    out = inject_context_to_messages(messages, [])
    assert out is messages
    assert out == messages


def test_no_last_user_message_unchanged(cwd_tmp):
    (cwd_tmp / "a.txt").write_text("AAA")

    # No user message at all.
    messages = [{"role": "assistant", "content": "hi"}]
    out = inject_context_to_messages(messages, ["a.txt"])
    assert out == messages

    # Last user message has non-string content (list) -> not modified.
    messages2 = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
    out2 = inject_context_to_messages(messages2, ["a.txt"])
    assert out2 == messages2
    assert _last_user_content(out2) is None


def test_content_structure_has_file_start_markers(cwd_tmp):
    (cwd_tmp / "mod.py").write_text("print('x')")

    messages = [_user_message("update it")]
    out = inject_context_to_messages(messages, ["mod.py"])

    last = _last_user_content(out)
    assert "--- FILE START: mod.py ---" in last
    assert "--- FILE END ---" in last
    assert "PRE-LOADED CONTEXT" in last
    assert "print('x')" in last
