#!/usr/bin/env python3
"""csmart - Claude Smart Local Routing / Local Reverse Proxy

Modes:
1. CLI mode (original): `csmart "your prompt"` - direct Claude Code CLI dispatch with pre-routed context
2. Proxy mode: `csmart start` - run local reverse proxy on port 4000 for Anthropic API with context injection
3. Health check: `csmart status` - report Ollama and upstream gateway health

Token-optimized: reduces token usage by 60-90% for large codebases.
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Iterable

import uvicorn

from router.dispatcher import app, check_ollama_health, check_upstream_health


# Known proxy subcommands (Track A: entrypoint + config)
KNOWN_COMMANDS = ("start", "status")

# Default configuration constants (kept at module scope so build_parser() is
# usable from tests without re-executing the CLI flow).
DEFAULT_CONFIDENCE_THRESHOLD = 0.65
DEFAULT_BUDGET_TOKENS = 16000  # ~64KB at 4 bytes/token
DEFAULT_REPORT_PATH = ".csmart/last-report.json"
DEFAULT_TIMEOUT = 600  # 10 minutes max for Claude dispatch
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4000


class CSmartParser(argparse.ArgumentParser):
    """ArgumentParser that routes ``start``/``status`` to subparsers while letting
    any other first positional flow through as a CLI-mode prompt.

    argparse's subparsers action greedily treats the first positional as a
    subcommand, so a bare prompt such as ``csmart "hello"`` would otherwise be
    rejected as an unknown command. This parser pre-scans argv, forwards known
    commands to the native subparsers, and dispatches any other first positional
    to a dedicated CLI-only parser (set as ``_cli_parser`` by ``build_parser``).
    """

    _cli_parser: argparse.ArgumentParser | None = None

    # Return type widened to Namespace | None to match typeshed's parse_args
    # overload resolution (returns Namespace | None when namespace is passed).
    # This override never returns None in practice (argparse exits on help/error).
    def parse_args(  # type: ignore[reportIncompatibleMethodOverride]
        self,
        args: Iterable[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace | None:
        argv = list(args) if args is not None else sys.argv[1:]
        first = self._first_positional(argv)
        if first in KNOWN_COMMANDS:
            # Known subcommand -> let argparse's subparsers handle it.
            return super().parse_args(argv, namespace)
        cli_parser = self._cli_parser
        if first is not None and cli_parser is not None:
            # Anything else is a CLI-mode prompt.
            return cli_parser.parse_args(argv, namespace)
        # No positional (help, empty, or flags-only) -> native parsing.
        return super().parse_args(argv, namespace)

    def _first_positional(self, argv):
        """Return the first positional token in ``argv``, skipping flags and the
        value token of flags that consume one. Returns ``None`` when absent."""
        i, n = 0, len(argv)
        while i < n:
            tok = argv[i]
            if tok == "--":
                return argv[i + 1] if i + 1 < n else None
            if tok.startswith("-") and tok != "-":
                i += 1
                if "=" not in tok and self._takes_value(tok):
                    i += 1
                continue
            return tok
        return None

    def _takes_value(self, option):
        action = self._option_string_actions.get(option)
        if action is None:
            return False
        # store_true / store_false / count / help use nargs == 0 (no value).
        return action.nargs != 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Shared flags live on a single parent parser (``add_help=False``) that is
    inherited by the main parser, each subparser, and the internal CLI-only
    parser, so ``--json``/``--strict``/``--threshold``/... work identically in
    every mode.
    """
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report to stdout after completion (CLI mode)",
    )
    shared.add_argument(
        "--strict",
        action="store_true",
        help="Abort execution if confidence is below threshold (fail-closed)",
    )
    shared.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f"Confidence threshold for routing (default: {DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    shared.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET_TOKENS,
        help=f"Maximum token budget for injected context (default: {DEFAULT_BUDGET_TOKENS})",
    )
    shared.add_argument(
        "--report-path",
        type=str,
        default=DEFAULT_REPORT_PATH,
        help=f"Path to write JSON report (default: {DEFAULT_REPORT_PATH})",
    )
    shared.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds for Claude CLI (default: {DEFAULT_TIMEOUT})",
    )
    shared.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose everything but don't dispatch to Claude (for testing)",
    )
    shared.add_argument(
        "--context-dir",
        type=str,
        default=".",
        help="Root directory to scan for context (default: current directory)",
    )

    parser = CSmartParser(
        prog="csmart",
        description=(
            "csmart - Claude Smart Local Routing\n\n"
            'CLI mode:  csmart "your coding task prompt" [options]\n'
            "Proxy:     csmart start [--host X] [--port Y]\n"
            "Health:    csmart status"
        ),
        parents=[shared],
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="The coding task prompt to execute (CLI mode only)",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="{start,status}",
    )

    start_p = subparsers.add_parser(
        "start",
        parents=[shared],  # type: ignore[reportArgumentType]  # pyright binds the subparser TypeVar to CSmartParser
        help="Run the local reverse proxy server",
    )
    start_p.add_argument(
        "--host",
        type=str,
        default=DEFAULT_HOST,
        help=f"Host to bind proxy server (default: {DEFAULT_HOST})",
    )
    start_p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind proxy server (default: {DEFAULT_PORT})",
    )

    subparsers.add_parser(
        "status",
        parents=[shared],  # type: ignore[reportArgumentType]  # pyright binds the subparser TypeVar to CSmartParser
        help="Check health of Ollama and upstream gateway",
    )

    # Dedicated CLI-mode parser (not a subparser) so `csmart "prompt"` keeps
    # working alongside the subcommand dispatch above.
    cli_parser = argparse.ArgumentParser(add_help=False, parents=[shared])
    cli_parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="The coding task prompt to execute (CLI mode only)",
    )
    cli_parser.set_defaults(command=None)
    parser._cli_parser = cli_parser

    return parser


def cmd_status() -> None:
    """Check health of Ollama and upstream gateway."""
    ollama_ok = check_ollama_health()
    upstream_ok = asyncio.run(check_upstream_health())

    print("csmart health check:")
    print(f"  Ollama (qwen2.5-coder:7b): {'✓ OK' if ollama_ok else '❌ NOT reachable/model not found'}")
    print(f"  Upstream gateway: {'✓ OK' if upstream_ok else '❌ NOT reachable'}")

    if ollama_ok and upstream_ok:
        sys.exit(0)
    else:
        sys.exit(1)


def cmd_start(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the local reverse proxy server."""
    print(f"csmart starting reverse proxy on {host}:{port}")
    print(f"  Upstream: {os.environ.get('ANTHROPIC_UPSTREAM_URL', 'https://ark.talaga.my.id')}")
    print(f"  Set ANTHROPIC_BASE_URL=http://{host}:{port} in your shell before running claude")
    print()
    uvicorn.run(app, host=host, port=port, log_level="info")


def main_cli(argv: list[str] | None = None) -> None:
    """Entry point.

    Original CLI mode: direct dispatch to Claude Code with pre-routed context.
    Subcommands: ``start`` (proxy server) and ``status`` (health check).
    """
    import time
    from typing import Optional
    from router.ast_extractor import scan_project_codebase
    from router.ollama_scorer import route_target_files
    from router.gate import apply_gate
    from router.safe_path import PathTraversalError, resolve_under_base
    from router.cli_dispatch import dispatch_claude, DispatchResult
    from router.report import GatewayConfig, create_report, write_report

    # Default configuration constants
    DEFAULT_IGNORE_DIRS = {
        ".git", "node_modules", "dist", "build", ".next",
        "venv", ".venv", ".dart_tool", "coverage", ".turbo", ".cache",
        "__pycache__", ".pytest_cache",
    }

    parser = build_parser()
    args = parser.parse_args(argv)
    assert args is not None  # parse_args never returns None (argparse exits on help/error)

    # Handle proxy mode commands
    if args.command == "status":
        cmd_status()
        return  # cmd_status exits itself; this return is for testability

    if args.command == "start":
        cmd_start(args.host, args.port)
        return

    # CLI mode - requires prompt argument
    if args.prompt is None:
        parser.print_help()
        sys.exit(1)

    # Original CLI flow
    # Step 1: AST skeleton extraction
    t0 = time.time()
    skeletons = scan_project_codebase(args.context_dir, DEFAULT_IGNORE_DIRS)
    t_ast = int((time.time() - t0) * 1000)

    # Combine all skeletons into one payload
    full_skeleton = "\n".join(skeletons)

    # Step 2: Local routing with Ollama
    t1 = time.time()
    routing_result = route_target_files(full_skeleton, args.prompt)
    t_routing = int((time.time() - t1) * 1000)

    # Step 3: Apply confidence gate and budget cap.
    # apply_gate takes *tokens* (it converts to bytes internally); the old
    # `* 4` passed bytes-as-tokens, making the budget 4x too lenient.
    gate_result = apply_gate(
        routing_result, args.threshold, args.budget, base_dir=args.context_dir
    )

    # Check if we should abort in --strict mode
    if args.strict and gate_result.status == "blocked":
        status = "gate_blocked"
        gateway_config = GatewayConfig(
            base_url=os.getenv("ANTHROPIC_BASE_URL", "https://ark.talaga.my.id"),
            primary_model=os.getenv("ANTHROPIC_MODEL", "doubao-seed-2.0-lite"),
            opus_model=os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL", "glm-5.3"),
            fast_model=os.getenv("ANTHROPIC_SMALL_FAST_MODEL", "deepseek-v4-flash"),
            effort_level=os.getenv("CLAUDE_CODE_EFFORT_LEVEL", "low"),
        )
        report = create_report(
            task=args.prompt,
            ast_scan_ms=t_ast,
            local_routing_ms=t_routing,
            routing_result=routing_result,
            gate_result=gate_result,
            injected_bytes=0,
            gateway_config=gateway_config,
            claude_result=None,
            status=status,
        )
        report_path = args.report_path
        report_dir = os.path.dirname(report_path)
        if report_dir and not os.path.exists(report_dir):
            os.makedirs(report_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        if args.json:
            print()
            print("=" * 50 + " VERIFICATION REPORT (JSON) " + "=" * 50)
            print(json.dumps(report.model_dump(), indent=2))
        sys.exit(2)

    # Step 4: Validate selected files are inside context_dir and read them.
    # Path-safety (review BLOCKER): paths are Ollama-chosen, so every one is
    # checked through resolve_under_base before touching the filesystem; a
    # traversal attempt (.., absolute-outside, symlink-outside) is skipped
    # rather than read, so an adversarial routing result cannot exfiltrate
    # files outside the project (CONTRACTS.md §6).
    selected_files = gate_result.selected_files
    injected_bytes = 0
    existing_files: list[str] = []
    for file_path in selected_files:
        try:
            resolved = resolve_under_base(file_path, args.context_dir)
        except PathTraversalError:
            print(
                f"csmart: skipping selected path outside context dir: {file_path}",
                file=sys.stderr,
            )
            continue
        if not resolved.is_file():
            print(
                f"csmart: skipping missing selected file: {file_path}",
                file=sys.stderr,
            )
            continue
        content = resolved.read_text(encoding="utf-8", errors="replace")
        injected_bytes += len(content.encode("utf-8"))
        existing_files.append(str(resolved))

    # Step 5: Dispatch to Claude Code CLI
    gateway_config = GatewayConfig(
        base_url=os.getenv("ANTHROPIC_BASE_URL", "https://ark.talaga.my.id"),
        primary_model=os.getenv("ANTHROPIC_MODEL", "doubao-seed-2.0-lite"),
        opus_model=os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL", "glm-5.3"),
        fast_model=os.getenv("ANTHROPIC_SMALL_FAST_MODEL", "deepseek-v4-flash"),
        effort_level=os.getenv("CLAUDE_CODE_EFFORT_LEVEL", "low"),
    )
    dispatch_result: Optional[DispatchResult] = None

    if not args.dry_run:
        dispatch_result = dispatch_claude(
            files=existing_files,
            prompt=args.prompt,
            gate_info=gate_result,
            dry_run=False,
            timeout=args.timeout,
        )
        assert dispatch_result is not None  # dispatch_claude always returns a result
        status = "ok" if dispatch_result.exit_code == 0 else "dispatch_error"
    else:
        # Dry run - create a dry dispatch result
        dispatch_result = DispatchResult(
            exit_code=0,
            duration_ms=0,
            cost_usd=None,
            session_id=None,
            result_excerpt=f"Dry run: {len(existing_files)} files selected, {injected_bytes} bytes",
            dry_run=True,
        )
        status = "ok"

    # Step 6: Always write JSON report
    report = create_report(
        task=args.prompt,
        ast_scan_ms=t_ast,
        local_routing_ms=t_routing,
        routing_result=routing_result,
        gate_result=gate_result,
        injected_bytes=injected_bytes,
        gateway_config=gateway_config,
        claude_result=dispatch_result,
        status=status,
    )
    report_path = args.report_path
    report_dir = os.path.dirname(report_path)
    if report_dir and not os.path.exists(report_dir):
        os.makedirs(report_dir, exist_ok=True)
    write_report(report, report_path)

    # Print report to stdout if --json is requested
    if args.json:
        print()
        print("=" * 50 + " VERIFICATION REPORT (JSON) " + "=" * 50)
        print(json.dumps(report.model_dump(), indent=2))

    # Exit with appropriate code
    if dispatch_result and dispatch_result.exit_code != 0:
        sys.exit(dispatch_result.exit_code)

    sys.exit(0)


if __name__ == "__main__":
    main_cli()
