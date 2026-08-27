"""
Unit tests for gate.py budget-aware filtering.
"""

import os
import tempfile
from router.gate import apply_gate, GateResult
from router.ollama_scorer import RoutingResult


def test_empty_routing_result():
    """Test gate when routing returns no files."""
    result = RoutingResult(target_files=[], confidence=0.5, reasoning="No match")
    gate_result = apply_gate(result, threshold=0.5, budget_tokens=1000)

    assert gate_result.status == "blocked"
    assert len(gate_result.selected_files) == 0
    assert gate_result.dropped_count == 0


def test_all_below_threshold():
    """Test gate when all candidates are below confidence threshold."""
    result = RoutingResult(target_files=["a.py", "b.py"], confidence=0.4, reasoning="Low confidence")
    gate_result = apply_gate(result, threshold=0.5, budget_tokens=1000)

    assert gate_result.status == "blocked"
    assert len(gate_result.selected_files) == 0
    assert gate_result.dropped_count == 2


def test_all_pass_and_fit():
    """Test gate when all pass confidence and fit in budget."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        with open(os.path.join(tmpdir, "a.py"), "w") as f:
            f.write("x\n" * 100)  # ~200 bytes
        with open(os.path.join(tmpdir, "b.py"), "w") as f:
            f.write("y\n" * 100)  # ~200 bytes

        result = RoutingResult(target_files=["a.py", "b.py"], confidence=0.8, reasoning="Good match")
        gate_result = apply_gate(result, threshold=0.5, budget_tokens=1000, base_dir=tmpdir)

        assert gate_result.status == "pass"
        assert len(gate_result.selected_files) == 2
        assert gate_result.dropped_count == 0
        assert gate_result.estimated_tokens == (400 // 4) == 100


def test_budget_exceeded_some_selected():
    """Test gate when budget is exceeded after some files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Three files, total size exceeds budget
        with open(os.path.join(tmpdir, "a.py"), "w") as f:
            f.write("a" * 400)  # 400 bytes = 100 tokens
        with open(os.path.join(tmpdir, "b.py"), "w") as f:
            f.write("b" * 400)  # another 100 tokens
        with open(os.path.join(tmpdir, "c.py"), "w") as f:
            f.write("c" * 400)  # another 100 tokens

        # Budget 150 tokens = 600 bytes: a + b = 800 > 600, so only a fits
        result = RoutingResult(target_files=["a.py", "b.py", "c.py"], confidence=0.8, reasoning="All good")
        gate_result = apply_gate(result, threshold=0.5, budget_tokens=150, base_dir=tmpdir)

        assert gate_result.status == "fallback"
        assert len(gate_result.selected_files) == 1
        assert gate_result.selected_files == ["a.py"]
        assert gate_result.dropped_count == 2
        assert gate_result.estimated_tokens == 100  # 400 / 4


def test_first_file_too_big():
    """Test when even the first file exceeds budget."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "big.py"), "w") as f:
            f.write("x" * 5000)  # 5000 bytes = 1250 tokens

        result = RoutingResult(target_files=["big.py"], confidence=0.8, reasoning="Big file")
        gate_result = apply_gate(result, threshold=0.5, budget_tokens=1000, base_dir=tmpdir)

        # 1250 tokens > 1000 budget, so blocked
        assert gate_result.status == "blocked"
        assert len(gate_result.selected_files) == 0
        assert gate_result.dropped_count == 1


def test_missing_files_skipped():
    """Test that missing files are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "exists.py"), "w") as f:
            f.write("test content")

        # One exists, one doesn't
        result = RoutingResult(target_files=["exists.py", "missing.py"], confidence=0.8, reasoning="Two candidates")
        gate_result = apply_gate(result, threshold=0.5, budget_tokens=1000, base_dir=tmpdir)

        assert gate_result.status == "pass"
        assert len(gate_result.selected_files) == 1
        assert "exists.py" in gate_result.selected_files
        # missing.py is counted as dropped because it couldn't be read
        assert gate_result.dropped_count == 1


def test_confidence_exact_threshold_match():
    """Test that confidence exactly equal to threshold passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "file.py"), "w") as f:
            f.write("test")

        result = RoutingResult(target_files=["file.py"], confidence=0.5, reasoning="Exact match")
        gate_result = apply_gate(result, threshold=0.5, budget_tokens=100, base_dir=tmpdir)

        assert gate_result.status == "pass"
        assert len(gate_result.selected_files) == 1


def test_fallback_confidence_below_but_some_above():
    """Test fallback when overall confidence below but some files pass? Actually all files get same confidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "a.py"), "w") as f:
            f.write("a")

        result = RoutingResult(target_files=["a.py"], confidence=0.5, reasoning="OK")
        gate_result = apply_gate(result, threshold=0.6, budget_tokens=100, base_dir=tmpdir)

        assert gate_result.status == "blocked"
