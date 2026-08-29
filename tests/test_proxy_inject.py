"""Hermetic tests for router/proxy.inject_context_to_messages (F-09 path safety).

Pure-function tests only: no network, no Ollama, no subprocess.
The path-validation base is ``.`` (CWD), so each test chdirs into ``tmp_path``
via the ``cwd_tmp`` fixture and restores the original CWD afterwards.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import router.dispatcher as mod
from router.dispatcher import (
    _expand_selected_with_imports,
    inject_context_to_messages,
)
from router.logger import StructuredLogger


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


def _read_records(tmp_path):
    """Read every JSONL record written to the capture logger's session file."""
    (f,) = tmp_path.glob("session_*.jsonl")
    return [json.loads(l) for l in f.read_text("utf-8").strip().splitlines()]


@pytest.fixture
def capture_logger(tmp_path, monkeypatch):
    """Replace ``router.dispatcher.logger`` with an in-test StructuredLogger."""
    cap = StructuredLogger(log_dir=tmp_path)
    monkeypatch.setattr(mod, "logger", cap)
    yield cap
    cap.close()


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


def test_expand_selected_with_imports_appends_imported_module(cwd_tmp):
    """FIX #3: expanding ['a.py'] (which does `import b`) yields ['a.py', 'b.py'],
    and inject_context_to_messages emits BOTH file blocks."""
    (cwd_tmp / "a.py").write_text("import b\n\ndef a():\n    return b.VALUE\n")
    (cwd_tmp / "b.py").write_text("VALUE = 1\n")

    expanded = _expand_selected_with_imports(["a.py"], base_dir=".")

    assert expanded == ["a.py", "b.py"]

    messages = [_user_message("use a and b")]
    out = inject_context_to_messages(messages, expanded)
    last = _last_user_content(out)
    assert "--- FILE START: a.py ---" in last
    assert "--- FILE START: b.py ---" in last


def test_expand_selected_with_imports_resolves_dotted_and_relative(cwd_tmp):
    """FIX #3: `from . import util` (sibling) and `import pkg.mod` (root-relative)
    both resolve to existing local modules; selected file stays first."""
    pkg = cwd_tmp / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "util.py").write_text("UTIL = 1\n")
    (pkg / "mod.py").write_text("MOD = 2\n")
    (pkg / "a.py").write_text("from . import util\nimport pkg.mod\n")

    expanded = _expand_selected_with_imports(["pkg/a.py"], base_dir=".")

    assert expanded == ["pkg/a.py", "pkg/util.py", "pkg/mod.py"]


def test_expand_selected_with_imports_skips_missing_and_duplicates(cwd_tmp):
    """FIX #3: stdlib/third-party imports that do not exist under base_dir are
    skipped, and already-selected files are not duplicated."""
    (cwd_tmp / "a.py").write_text("import os\nimport sys\nimport b\n")
    (cwd_tmp / "b.py").write_text("B = 1\n")

    expanded = _expand_selected_with_imports(["a.py", "b.py"], base_dir=".")

    # b.py was already selected; os/sys do not exist under base_dir.
    assert expanded == ["a.py", "b.py"]


def test_expand_resolves_multidot_relative_import(cwd_tmp):
    """FIX #3 (review): ``from ..util import y`` walks up one package level, so a
    file in ``pkg/sub/`` resolves ``pkg/util.py``, not ``pkg/sub/util.py``."""
    pkg = cwd_tmp / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "util.py").write_text("UTIL = 1\n")
    (pkg / "sub" / "__init__.py").write_text("")
    (pkg / "sub" / "a.py").write_text("from ..util import y\n")

    expanded = _expand_selected_with_imports(["pkg/sub/a.py"], base_dir=".")

    assert expanded == ["pkg/sub/a.py", "pkg/util.py"]


def test_expand_budget_cap_drops_imports_that_do_not_fit(cwd_tmp):
    """FIX #3 (review): appended imports are capped at budget_tokens (1 token ≈
    4 bytes). A tiny budget that fits only the selected file drops the import;
    without the cap the import would push the injection over budget."""
    (cwd_tmp / "a.py").write_text("import b\n")
    # Selected file: 9 bytes. b.py: 7 bytes. Budget 3 tokens = 12 bytes fits
    # a.py but not a.py + b.py (16 bytes).
    (cwd_tmp / "b.py").write_text("B = 1\n")

    expanded = _expand_selected_with_imports(["a.py"], base_dir=".", budget_tokens=3)

    assert expanded == ["a.py"]


def test_expand_budget_keeps_imports_that_fit(cwd_tmp):
    """FIX #3 (review): imports that fit within budget_tokens are still appended."""
    (cwd_tmp / "a.py").write_text("import b\n")
    (cwd_tmp / "b.py").write_text("B = 1\n")

    # 16 bytes total <= 16 bytes (4 tokens) -> import survives.
    expanded = _expand_selected_with_imports(["a.py"], base_dir=".", budget_tokens=4)

    assert expanded == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# Source-level structured-log emission tests (CONTEXT_INJECTED / IMPORT_EXPANSION).
# ---------------------------------------------------------------------------


def test_context_injected_event_emitted(cwd_tmp, capture_logger):
    """CONTEXT_INJECTED is logged once with the real injection counts."""
    src = cwd_tmp / "a.py"
    src.write_text("def hello():\n    return 1\n")

    messages = [_user_message("fix it")]
    out = mod.inject_context_to_messages(messages, ["a.py"])

    assert out is not messages
    capture_logger.flush()
    records = _read_records(cwd_tmp)
    injected = [r for r in records if r["event"] == "CONTEXT_INJECTED"]
    assert len(injected) == 1, f"expected one CONTEXT_INJECTED, got {len(injected)}"
    rec = injected[0]
    assert rec["files_requested"] == 1
    assert rec["files_injected"] == 1
    assert rec["skipped_count"] == 0
    assert rec["bytes_injected"] == len("def hello():\n    return 1\n")
    assert rec["base_dir"] == "."


def test_import_expansion_event_counts_budget_drops(cwd_tmp, capture_logger):
    """IMPORT_EXPANSION records dropped_by_budget when imports do not fit."""
    (cwd_tmp / "a.py").write_text("import b\n")
    # Selected file is 9 bytes; b.py is 6 bytes. Budget 3 tokens = 12 bytes fits
    # a.py but not a.py + b.py (15 bytes), so the candidate import is dropped.
    (cwd_tmp / "b.py").write_text("B = 1\n")

    expanded = mod._expand_selected_with_imports(
        ["a.py"], base_dir=".", budget_tokens=3
    )

    assert expanded == ["a.py"]
    capture_logger.flush()
    records = _read_records(cwd_tmp)
    imp = [r for r in records if r["event"] == "IMPORT_EXPANSION"]
    assert len(imp) == 1, f"expected one IMPORT_EXPANSION, got {len(imp)}"
    rec = imp[0]
    assert rec["dropped_by_budget"] >= 1
    assert rec["appended_count"] == 0
    assert rec["expanded_count"] == len(expanded) == 1
    assert rec["selected_count"] == 1
    assert rec["budget_tokens"] == 3
    assert rec["total_bytes"] == 9
