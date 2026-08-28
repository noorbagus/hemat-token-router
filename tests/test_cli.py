"""Hermetic unit tests for csmart CLI parser + main_cli routing (Track A).

These tests never start the proxy server and never touch the network or
Ollama: ``cmd_status`` / ``cmd_start`` are monkeypatched to no-ops where
needed, and ``build_parser()`` only builds an argument parser.
"""

import json

import pytest

import csmart
import router.ast_extractor
import router.cli_dispatch
import router.ollama_scorer
from csmart import build_parser
from router.cli_dispatch import DispatchResult
from router.gate import GateResult
from router.logger import CLI_DISPATCH, SERVER_START, SERVER_STOP, StructuredLogger
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

    def fake_start(host: str, port: int, context_dir: str) -> None:
        captured["host"] = host
        captured["port"] = port
        captured["context_dir"] = context_dir

    monkeypatch.setattr(csmart, "cmd_start", fake_start)
    result = csmart.main_cli(["start"])
    assert result is None
    assert captured == {"host": "127.0.0.1", "port": 4000, "context_dir": "."}


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


# --- Wave 4 Track B: logs / stats subcommands -------------------------


def test_parse_logs_sets_command() -> None:
    ns = build_parser().parse_args(["logs", "--tail", "5"])
    assert ns.command == "logs"
    assert ns.tail == 5
    assert ns.follow is False


def test_parse_stats_sets_command() -> None:
    ns = build_parser().parse_args(["stats"])
    assert ns.command == "stats"


def test_parse_logs_event_and_follow() -> None:
    ns = build_parser().parse_args(["logs", "--event", "OLLAMA_TRIAGE", "--follow"])
    assert ns.command == "logs"
    assert ns.event == "OLLAMA_TRIAGE"
    assert ns.follow is True


def test_main_cli_logs_calls_cmd_logs(monkeypatch) -> None:
    """`main_cli(["logs", ...])` routes to cmd_logs with parsed flags."""
    captured: dict[str, object] = {}

    def fake_cmd_logs(log_dir, tail, follow, event) -> None:
        captured["log_dir"] = log_dir
        captured["tail"] = tail
        captured["follow"] = follow
        captured["event"] = event

    monkeypatch.setattr(csmart, "cmd_logs", fake_cmd_logs)
    result = csmart.main_cli(["logs", "--tail", "3"])
    assert result is None
    assert captured["log_dir"] == csmart.DEFAULT_LOG_DIR
    assert captured["tail"] == 3
    assert captured["follow"] is False
    assert captured["event"] is None


def test_main_cli_stats_calls_cmd_stats(monkeypatch) -> None:
    """`main_cli(["stats"])` routes to cmd_stats once."""
    called: list[tuple[object, object, object]] = []

    def fake_cmd_stats(log_dir, report_dir, json_out) -> None:
        called.append((log_dir, report_dir, json_out))

    monkeypatch.setattr(csmart, "cmd_stats", fake_cmd_stats)
    result = csmart.main_cli(["stats"])
    assert result is None
    assert len(called) == 1
    assert called[0][0] == csmart.DEFAULT_LOG_DIR
    assert called[0][1] == ".csmart"
    assert called[0][2] is False


# --- Wave 4 Track D: structured CLI_DISPATCH / SERVER_START / SERVER_STOP ---


def _read_records(tmp_path):
    """Read every JSONL record written by a StructuredLogger into ``tmp_path``."""
    (f,) = tmp_path.glob("session_*.jsonl")
    return [json.loads(line) for line in f.read_text("utf-8").strip().splitlines()]


@pytest.fixture
def capture_logger(tmp_path, monkeypatch):
    """Patch ``router.cli_dispatch.logger`` with a scratch StructuredLogger."""
    lg = StructuredLogger(log_dir=tmp_path)
    monkeypatch.setattr(router.cli_dispatch, "logger", lg)
    return lg


@pytest.fixture
def capture_logger_csmart(tmp_path, monkeypatch):
    """Patch ``csmart.logger`` with a scratch StructuredLogger."""
    lg = StructuredLogger(log_dir=tmp_path)
    monkeypatch.setattr(csmart, "logger", lg)
    return lg


def test_dispatch_claude_dry_run_logs_cli_dispatch(
    monkeypatch, tmp_path, capture_logger
) -> None:
    """A dry-run dispatch must emit exactly one CLI_DISPATCH record (no error)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("def f():\n    pass\n")
    gate = GateResult(
        status="pass",
        selected_files=["x.py"],
        selected_bytes=0,
        estimated_tokens=0,
        dropped_count=0,
        reason="ok",
    )
    result = router.cli_dispatch.dispatch_claude(
        files=["x.py"],
        prompt="task",
        gate_info=gate,
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.exit_code == 0

    capture_logger.flush()
    records = _read_records(tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == CLI_DISPATCH
    assert rec["dry_run"] is True
    assert rec["exit_code"] == 0
    assert rec["gate_status"] == "pass"
    assert rec["files_count"] == 1
    assert rec["error"] is None


def test_dispatch_claude_missing_token_logs_error(
    monkeypatch, tmp_path, capture_logger
) -> None:
    """A missing gateway token must yield exit_code=1 + error in the log record."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("def f():\n    pass\n")
    # Prevent load_dotenv(GATEWAY_ENV_PATH / GATEWAY_ENV_LOCAL_PATH) from
    # re-populating the token.
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        router.cli_dispatch,
        "GATEWAY_ENV_PATH",
        str(tmp_path / "does-not-exist.env"),
    )
    monkeypatch.setattr(
        router.cli_dispatch,
        "GATEWAY_ENV_LOCAL_PATH",
        str(tmp_path / "does-not-exist-local.env"),
    )
    gate = GateResult(
        status="blocked",
        selected_files=["x.py"],
        selected_bytes=0,
        estimated_tokens=0,
        dropped_count=0,
        reason="blocked",
    )
    result = router.cli_dispatch.dispatch_claude(
        files=["x.py"],
        prompt="task",
        gate_info=gate,
        dry_run=False,
    )
    assert result.exit_code == 1

    capture_logger.flush()
    records = _read_records(tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == CLI_DISPATCH
    assert rec["exit_code"] == 1
    assert rec["dry_run"] is False
    assert rec["error"] == "Missing ANTHROPIC_AUTH_TOKEN in gateway .env"


def test_cmd_start_logs_server_start_stop(
    monkeypatch, tmp_path, capture_logger_csmart
) -> None:
    """cmd_start must emit SERVER_START before uvicorn and SERVER_STOP after it."""
    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(csmart.uvicorn, "run", fake_run)
    csmart.main_cli(["start"])

    capture_logger_csmart.flush()
    records = _read_records(tmp_path)
    assert len(records) == 2
    start = next(r for r in records if r["event"] == SERVER_START)
    stop = next(r for r in records if r["event"] == SERVER_STOP)
    assert start["host"] == "127.0.0.1"
    assert start["port"] == 4000
    assert start["context_dir"] == "."
    assert start["upstream_base_url"] == csmart.UPSTREAM_BASE_URL
    assert start["ollama_model"] == csmart.triage_model()
    assert stop["host"] == "127.0.0.1"
    assert stop["port"] == 4000
    assert captured.get("host") == "127.0.0.1"
    assert captured.get("port") == 4000
