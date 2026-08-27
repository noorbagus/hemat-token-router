"""Hermetic unit tests for csmart CLI parser + main_cli routing (Track A).

These tests never start the proxy server and never touch the network or
Ollama: ``cmd_status`` / ``cmd_start`` are monkeypatched to no-ops where
needed, and ``build_parser()`` only builds an argument parser.
"""

import pytest

import csmart
import router.ast_extractor
import router.cli_dispatch
import router.ollama_scorer
from csmart import build_parser
from router.cli_dispatch import DispatchResult
from router.ollama_scorer import RoutingResult


def test_parse_start_sets_command() -> None:
    ns = build_parser().parse_args(["start"])
    assert ns.command == "start"


def test_parse_status_sets_command() -> None:
    ns = build_parser().parse_args(["status"])
    assert ns.command == "status"


def test_parse_bare_prompt() -> None:
    ns = build_parser().parse_args(["hello"])
    assert ns.prompt == "hello"
    assert ns.command is None


def test_parse_json_flag_before_prompt() -> None:
    ns = build_parser().parse_args(["--json", "hello"])
    assert ns.json is True
    assert ns.prompt == "hello"


def test_parse_start_port() -> None:
    ns = build_parser().parse_args(["start", "--port", "9999"])
    assert ns.command == "start"
    assert ns.port == 9999


def test_parse_shared_flag_on_subcommand() -> None:
    """Shared flags must be inherited by subparsers too."""
    ns = build_parser().parse_args(["status", "--json"])
    assert ns.command == "status"
    assert ns.json is True


def test_parse_shared_flags_across_modes() -> None:
    ns = build_parser().parse_args(["--strict", "--dry-run", "fix the bug"])
    assert ns.strict is True
    assert ns.dry_run is True
    assert ns.prompt == "fix the bug"


def test_parse_start_shared_flag() -> None:
    ns = build_parser().parse_args(["start", "--threshold", "0.9"])
    assert ns.command == "start"
    assert ns.threshold == 0.9


def test_unknown_subcommand_raises_systemexit() -> None:
    """An unknown token in subcommand position raises SystemExit.

    Note: a *bare* first token that is not ``start``/``status`` (e.g.
    ``parse_args(["bogus"])``) is intentionally treated as a CLI-mode prompt
    (OD-6: `csmart "your prompt"` must keep working), so the unknown-subcommand
    rejection is exercised here in a genuine subcommand context instead.
    """
    with pytest.raises(SystemExit):
        build_parser().parse_args(["start", "bogus"])


def test_bare_noncommand_token_is_cli_prompt() -> None:
    """A bare non-command token is a CLI prompt (not an error)."""
    ns = build_parser().parse_args(["bogus"])
    assert ns.prompt == "bogus"
    assert ns.command is None


def test_parse_empty_args_defaults() -> None:
    ns = build_parser().parse_args([])
    assert ns.prompt is None
    assert ns.command is None
    assert ns.threshold == 0.65
    assert ns.budget == 16000


def test_main_cli_status_returns_without_blocking(monkeypatch) -> None:
    """`main_cli(["status"])` routes to cmd_status and returns without hanging."""
    called: list[str] = []

    def fake_status() -> None:
        called.append("status")

    monkeypatch.setattr(csmart, "cmd_status", fake_status)
    result = csmart.main_cli(["status"])
    assert result is None
    assert called == ["status"]


def test_main_cli_start_calls_cmd_start(monkeypatch) -> None:
    """`main_cli(["start"])` routes to cmd_start with default host/port."""
    captured: dict[str, object] = {}

    def fake_start(host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(csmart, "cmd_start", fake_start)
    result = csmart.main_cli(["start"])
    assert result is None
    assert captured == {"host": "127.0.0.1", "port": 4000}


def test_main_cli_skips_path_traversal_selected_files(monkeypatch, tmp_path) -> None:
    """Ollama-chosen paths outside context_dir are skipped, never read/dispatched.

    Regression for the Wave-3 review BLOCKER: Step 4 used to raw-``open()``
    whatever ``gate_result.selected_files`` contained, so an adversarial routing
    result pointing at ``../secret`` (or an absolute path outside) was read and
    forwarded to dispatch_claude — and from there to the upstream gateway. Now
    every path is validated through ``resolve_under_base`` first (CONTRACTS.md §6).
    """
    ctx = tmp_path / "project"
    ctx.mkdir()
    ok_file = ctx / "src" / "ok.py"
    ok_file.parent.mkdir()
    ok_file.write_text("def ok():\n    pass\n")

    # Outside the context dir: one relative ``../`` escape, one absolute path.
    secret = tmp_path / "secret.py"
    secret.write_text("SECRET=1")

    def fake_scan(root_dir, ignore_dirs):
        return ["// ok.py\n- def ok()\n"]

    def fake_route(skeleton, prompt):
        return RoutingResult(
            target_files=["../secret.py", str(secret), "src/ok.py"],
            confidence=1.0,
            reasoning="regression",
        )

    dispatched: list[str] = []

    def fake_dispatch(files, prompt, gate_info, dry_run=False, timeout=600.0):
        dispatched.extend(files)
        return DispatchResult(
            exit_code=0,
            duration_ms=1,
            cost_usd=None,
            session_id=None,
            result_excerpt="ok",
            dry_run=False,
        )

    monkeypatch.setattr(router.ast_extractor, "scan_project_codebase", fake_scan)
    monkeypatch.setattr(router.ollama_scorer, "route_target_files", fake_route)
    monkeypatch.setattr(router.cli_dispatch, "dispatch_claude", fake_dispatch)

    report = tmp_path / "report.json"
    with pytest.raises(SystemExit):
        csmart.main_cli(
            [
                "--context-dir",
                str(ctx),
                "--report-path",
                str(report),
                "fix the bug",
            ]
        )

    assert report.exists()
    # Only the in-context file reached dispatch_claude (resolved absolute path).
    assert dispatched == [str(ok_file.resolve())]
    # The traversal candidates must never be read or forwarded.
    assert not any("secret" in p for p in dispatched)
