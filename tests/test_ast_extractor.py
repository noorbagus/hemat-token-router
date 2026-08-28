"""Unit tests for ast_extractor.py"""

import json
import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest

import router.ast_extractor as mod
from router.ast_extractor import (
    extract_ast_skeleton,
    scan_project_codebase,
    EXTENSION_TO_LANG,
)
from router.logger import StructuredLogger


@pytest.fixture
def temp_python_file() -> Generator[Path, None, None]:
    content = """
class MyClass:
    \"\"\"A test class.\"\"\"

    def __init__(self, value: int):
        self.value = value

    def do_something(self, arg: str) -> bool:
        return arg.startswith("test")

def my_function(a: int, b: str) -> None:
    \"\"\"A test function.\"\"\"
    pass

def another_function() -> dict:
    return {}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        path = Path(f.name)
    yield path
    os.unlink(path)


@pytest.fixture
def temp_javascript_file() -> Generator[Path, None, None]:
    content = """
interface User {
    id: number;
    name: string;
}

class MyClass {
    constructor(private value: number) {}

    doSomething(arg: string): boolean {
        return arg.startsWith('test');
    }
}

function myFunction(a: number, b: string): void {
    // do something
}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(content)
        path = Path(f.name)
    yield path
    os.unlink(path)


@pytest.fixture
def capture_logger(tmp_path, monkeypatch) -> Generator[StructuredLogger, None, None]:
    """Replace the module logger with one writing to tmp_path so tests can
    assert on the emitted AST_SCANNED records."""
    lg = StructuredLogger(log_dir=tmp_path)
    monkeypatch.setattr(mod, "logger", lg)
    yield lg


def _read_records(tmp_path: Path) -> list[dict]:
    """Read all JSONL records flushed to tmp_path by the capture logger."""
    (f,) = tmp_path.glob("session_*.jsonl")
    text = f.read_text("utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def test_extract_unsupported_extension() -> None:
    """Unsupported file extensions return empty string."""
    result = extract_ast_skeleton("test.txt")
    assert result == ""


def test_extract_python_file(temp_python_file: Path) -> None:
    """Extract signatures from a Python file."""
    result = extract_ast_skeleton(str(temp_python_file))
    assert temp_python_file.name in result
    assert "class MyClass" in result
    assert "def __init__" in result
    assert "def do_something" in result
    assert "def my_function" in result
    assert "def another_function" in result
    # Count signatures
    lines = [line for line in result.splitlines() if line.startswith("- ")]
    assert len(lines) == 5


def test_extract_javascript_file(temp_javascript_file: Path) -> None:
    """Extract signatures from a JavaScript file."""
    result = extract_ast_skeleton(str(temp_javascript_file))
    assert temp_javascript_file.name in result
    assert "class MyClass" in result
    assert "class MyClass" in result
    assert "constructor" in result
    assert "doSomething" in result
    assert "function myFunction" in result


def test_max_12_signatures() -> None:
    """Should not return more than 12 signatures per file."""
    # Create a file with 20 functions
    content = "\n".join([f"def func_{i}():\n    pass\n" for i in range(20)])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        path = Path(f.name)

    try:
        result = extract_ast_skeleton(str(path))
        lines = [line for line in result.splitlines() if line.startswith("- ")]
        assert len(lines) == 12
    finally:
        os.unlink(path)


def test_scan_project_codebase() -> None:
    """Scan directory collects skeletons from supported files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a supported file
        (Path(tmpdir) / "test.py").write_text("""
class A:
    def method(self): pass
""")
        # Create an unsupported file
        (Path(tmpdir) / "test.txt").write_text("not supported")
        # Create ignored directory
        os.mkdir(Path(tmpdir) / "__pycache__")
        (Path(tmpdir) / "__pycache__" / "ignored.pyc").write_text("binary")

        result = scan_project_codebase(tmpdir, {"__pycache__", ".git"})
        assert len(result) == 1
        assert "test.py" in result[0]
        assert "class A" in result[0]


def test_all_extensions_have_lang_mapping() -> None:
    """Verify all expected extensions are mapped."""
    expected = [".ts", ".tsx", ".js", ".jsx", ".py", ".dart", ".go", ".rs"]
    for ext in expected:
        assert ext in EXTENSION_TO_LANG
        assert len(EXTENSION_TO_LANG[ext]) > 0


def test_scan_emits_ast_scanned(tmp_path: Path, capture_logger: StructuredLogger) -> None:
    """scan_project_codebase emits exactly one AST_SCANNED record with the
    scan metrics (scanned count, files encountered, parse failures, duration)."""
    (tmp_path / "compute.py").write_text("def compute():\n    return 1\n")

    result = scan_project_codebase(str(tmp_path), {"__pycache__"})

    assert result  # the .py file yields a skeleton
    capture_logger.flush()
    scanned = [r for r in _read_records(tmp_path) if r["event"] == "AST_SCANNED"]
    assert len(scanned) == 1
    rec = scanned[0]
    assert rec["root_dir"] == str(tmp_path)
    assert rec["scanned_files_count"] >= 1
    assert rec["files_encountered"] >= 1
    assert "parse_failures" in rec
    assert rec["parse_failures"] == 0
    assert rec["duration_ms"] >= 0


def test_scan_counts_only_supported_extensions(
    tmp_path: Path, capture_logger: StructuredLogger
) -> None:
    """A .txt file is seen but not counted: files_encountered reflects only
    supported-extension files."""
    (tmp_path / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "b.txt").write_text("not supported")

    result = scan_project_codebase(str(tmp_path), set())

    assert len(result) == 1
    capture_logger.flush()
    (rec,) = [r for r in _read_records(tmp_path) if r["event"] == "AST_SCANNED"]
    assert rec["files_encountered"] == 1
    assert rec["scanned_files_count"] == 1


def test_scan_empty_py_yields_skeleton_not_parse_failure(
    tmp_path: Path, capture_logger: StructuredLogger
) -> None:
    """An empty .py file is NOT a parse failure: extract_ast_skeleton returns
    '// <path>\\n' even with no signatures, so it still yields a skeleton and
    parse_failures stays 0."""
    (tmp_path / "empty.py").write_text("")

    result = scan_project_codebase(str(tmp_path), set())

    assert len(result) == 1
    assert "empty.py" in result[0]
    capture_logger.flush()
    (rec,) = [r for r in _read_records(tmp_path) if r["event"] == "AST_SCANNED"]
    assert rec["files_encountered"] == 1
    assert rec["scanned_files_count"] == 1
    assert rec["parse_failures"] == 0


def test_scan_counts_parse_failure(
    tmp_path: Path, capture_logger: StructuredLogger
) -> None:
    """A supported-extension file whose skeleton extraction fails (here a
    dangling symlink raises on open, so extract_ast_skeleton returns '')
    is counted as a parse failure and yields no skeleton."""
    os.symlink(str(tmp_path / "does-not-exist.py"), tmp_path / "broken.py")

    result = scan_project_codebase(str(tmp_path), set())

    assert result == []
    capture_logger.flush()
    (rec,) = [r for r in _read_records(tmp_path) if r["event"] == "AST_SCANNED"]
    assert rec["files_encountered"] == 1
    assert rec["scanned_files_count"] == 0
    assert rec["parse_failures"] == 1
