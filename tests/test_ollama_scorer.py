"""Hermetic tests for router/ollama_scorer.py (S-6 model env, T-4 heuristic).

These tests never call a real Ollama: ``ollama.chat`` is monkeypatched, and the
keyword fallback is exercised directly on ast_extractor-format skeletons
(``// <path>`` header lines followed by ``- <signature>`` lines).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ollama  # noqa: E402

import router.ollama_scorer as scorer  # noqa: E402
from router.ollama_scorer import (  # noqa: E402
    DEFAULT_TRIAGE_MODEL,
    _keyword_heuristic,
    route_target_files,
    triage_model,
)

JSON_OK = '{"target_files": ["a.py"], "confidence": 0.9, "reasoning": "x"}'


def test_default_triage_model_constant() -> None:
    assert DEFAULT_TRIAGE_MODEL == "qwen2.5-coder:7b"


def test_triage_model_env_override(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_TRIAGE_MODEL", "custom-triage:8b")
    assert triage_model() == "custom-triage:8b"
    monkeypatch.delenv("OLLAMA_TRIAGE_MODEL", raising=False)
    assert triage_model() == DEFAULT_TRIAGE_MODEL


def test_route_target_files_uses_env_model(monkeypatch) -> None:
    """S-6: OLLAMA_TRIAGE_MODEL is honored; ollama.chat gets that model."""
    monkeypatch.setenv("OLLAMA_TRIAGE_MODEL", "custom-triage:8b")
    calls: list[str] = []

    def fake_chat(**kwargs):
        calls.append(kwargs["model"])
        return SimpleNamespace(message=SimpleNamespace(content=JSON_OK))

    monkeypatch.setattr(ollama, "chat", fake_chat)
    result = route_target_files("// a.py\n- def a()\n", "fix a")
    assert result.target_files == ["a.py"]
    assert calls == ["custom-triage:8b"]


def test_route_target_files_default_model_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_TRIAGE_MODEL", raising=False)
    calls: list[str] = []

    def fake_chat(**kwargs):
        calls.append(kwargs["model"])
        return SimpleNamespace(message=SimpleNamespace(content=JSON_OK))

    monkeypatch.setattr(ollama, "chat", fake_chat)
    route_target_files("// a.py\n", "fix a")
    assert calls == [DEFAULT_TRIAGE_MODEL]


def test_route_target_files_keep_alive_and_num_ctx(monkeypatch) -> None:
    """Latency: keep_alive=-1 keeps triage model resident; num_ctx=8192 set."""
    monkeypatch.delenv("OLLAMA_TRIAGE_MODEL", raising=False)
    captured: dict = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=JSON_OK))

    monkeypatch.setattr(ollama, "chat", fake_chat)
    route_target_files("// a.py\n", "fix a")
    assert captured["keep_alive"] == -1
    assert captured["options"]["num_ctx"] == 8192
    assert captured["format"] == "json"
    assert captured["options"]["temperature"] == 0.0


def test_route_target_files_long_reasoning_truncated(monkeypatch) -> None:
    """Long reasoning is truncated to ≤120 chars (decode-latency win)."""
    long_reasoning = "r" * 300
    payload = (
        '{"target_files": ["a.py"], "confidence": 0.9, '
        f'"reasoning": "{long_reasoning}"}}'
    )
    monkeypatch.delenv("OLLAMA_TRIAGE_MODEL", raising=False)

    def fake_chat(**kwargs):
        return SimpleNamespace(message=SimpleNamespace(content=payload))

    monkeypatch.setattr(ollama, "chat", fake_chat)
    result = route_target_files("// a.py\n", "fix a")
    assert len(result.reasoning) <= 120
    assert result.reasoning.endswith("...")
    assert result.reasoning.startswith("r" * 117)


def test_route_target_files_short_reasoning_unchanged(monkeypatch) -> None:
    """Short reasoning stays intact (no over-truncation)."""
    monkeypatch.delenv("OLLAMA_TRIAGE_MODEL", raising=False)

    def fake_chat(**kwargs):
        return SimpleNamespace(message=SimpleNamespace(content=JSON_OK))

    monkeypatch.setattr(ollama, "chat", fake_chat)
    result = route_target_files("// a.py\n", "fix a")
    assert result.reasoning == "x"


def test_keyword_heuristic_path_match_beats_signature_match() -> None:
    """T-4: a keyword hitting the real file's path must outrank the same keyword
    appearing only in another file's signature.

    ``token_router.py`` matches on its path (the strongest signal); ``routes.py``
    only matches via its ``tokenize`` signature. The real file is the top pick.
    """
    skeleton = (
        "// src/token_router.py\n"
        "- def route_request(request)\n"
        "// src/routes.py\n"
        "- def tokenize(text)\n"
    )
    result = _keyword_heuristic(skeleton, "fix the token router", "boom")
    assert result.target_files[0] == "src/token_router.py"
    assert result.confidence > 0.0


def test_keyword_heuristic_never_returns_signature_lines() -> None:
    """Regression: signature-only hits must attribute to the real file, never
    fabricate a pseudo-file entry like ``- def check_health(status)``."""
    skeleton = (
        "// src/token_router.py\n"
        "- def route_request(request)\n"
        "// src/health.py\n"
        "- def check_health(status)\n"
    )
    result = _keyword_heuristic(skeleton, "fix status check", "boom")
    assert result.target_files == ["src/health.py"]
    for f in result.target_files:
        assert not f.startswith("- ")


def test_keyword_heuristic_no_keywords() -> None:
    result = _keyword_heuristic("// a.py\n- def a()\n", "the and for", "boom")
    assert result.target_files == []
    assert result.confidence == 0.0


def test_keyword_heuristic_existing_keywords() -> None:
    """Sanity: the scorer module exposes the fallback without import errors."""
    assert callable(scorer._keyword_heuristic)
