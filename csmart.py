#!/usr/bin/env python3
"""csmart - Claude Smart Local Routing / Local Reverse Proxy

Modes:
1. CLI mode (original): `csmart "your prompt"` - direct Claude Code CLI dispatch with pre-routed context
2. Proxy mode: `csmart start` - run local reverse proxy on port 4000 for Anthropic API with context injection

Token-optimized: reduces token usage by 60-90% for large codebases.
"""

import argparse
import asyncio
import sys
import os

import uvicorn

from router.proxy import app, check_ollama_health, check_upstream_health


def cmd_status() -> None:
    """Check health of Ollama and upstream gateway."""
    ollama_ok = check_ollama_health()
    upstream_ok = asyncio.run(check_upstream_health())

    print("csmart health check:")
    print(f"  Ollama (qwen2.5-coder:7b): {'✓ OK' if ollama_ok else '❌ NOT reachable/model not found"}
    print(f"  Upstream gateway: {'✓ OK' if upstream_ok else '❌ NOT reachable"}

    if ollama_ok and upstream_ok:
        sys.exit(0)
    else:
        sys.exit(1)


def cmd_start(host: str = "127.0.0.1", port: int = 4000) -> None:
    """Start the local reverse proxy server."""
    print(f"csmart starting reverse proxy on {host}:{port}")
    print(f"  Upstream: {os.environ.get('ANTHROPIC_UPSTREAM_URL', 'https://ark.talaga.my.id')}")
    print(f"  Set ANTHROPIC_BASE_URL=http://{host}:{port} in your shell before running claude")
    print()
    uvicorn.run(app, host=host, port=port, log_level="info")


def main_cli() -> None:
    """Original CLI mode - direct dispatch to Claude Code."""
    import time
    from typing import Optional
    from router.ast_extractor import scan_project_codebase
    from router.ollama_scorer import route_target_files, RoutingResult
    from router.gate import apply_gate, GateResult
    from router.dispatcher import dispatch_claude, DispatchResult
    from router.report import CsmartReport, GatewayConfig, create_report, write_report

    # Default configuration constants
    DEFAULT_IGNORE_DIRS = {
        ".git", "node_modules", "dist", "build", ".next",
        "venv", ".venv", ".dart_tool", "coverage", ".turbo", ".cache",
        "__pycache__", ".pytest_cache",
    }
    DEFAULT_CONFIDENCE_THRESHOLD = 0.65
    DEFAULT_BUDGET_TOKENS = 16000  # ~64KB at 4 bytes/token
    DEFAULT_REPORT_PATH = ".csmart/last-report.json"
    DEFAULT_TIMEOUT = 600  # 10 minutes max for Claude dispatch

    parser = argparse.ArgumentParser(
        description="csmart - Claude Smart Local Routing"
    )
    parser.add_argument(
        "prompt",
        help="The coding task prompt to execute (CLI mode only)",
        nargs="?",
        default=None,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report to stdout after completion (CLI mode)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Abort execution if confidence is below threshold (fail-closed)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f"Confidence threshold for routing (default: {DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET_TOKENS,
        help=f"Maximum token budget for injected context (default: {DEFAULT_BUDGET_TOKENS})",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=DEFAULT_REPORT_PATH,
        help=f"Path to write JSON report (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds for Claude CLI (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose everything but don't dispatch to Claude (for testing)",
    )
    parser.add_argument(
        "--context-dir",
        type=str,
        default=".",
        help="Root directory to scan for context (default: current directory)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind proxy server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Port to bind proxy server (default: 4000)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "status"],
        help="Command: 'start' = run proxy server, 'status' = health check",
        default=None,
    )

    args = parser.parse_args()

    # Handle proxy mode commands
    if args.command == "status":
        cmd_status()
        return  # cmd_status exits itself

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

    # Step 3: Apply confidence gate and budget cap
    budget_bytes = args.budget * 4  # 4 bytes ≈ 1 token
    gate_result = apply_gate(routing_result, args.threshold, budget_bytes)

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
        if not os.path.exists(os.path.dirname(report_path)):
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        if args.json:
            print()
            print("=" * 50 + " VERIFICATION REPORT (JSON) " + "=" * 50)
            print(json.dumps(report.model_dump(), indent=2))
        sys.exit(2)

    # Step 4: Get selected files exist and calculate injected bytes
    selected_files = gate_result.selected_files
    injected_bytes = 0
    existing_files: list[str] = []
    for file_path in selected_files:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                injected_bytes += len(content.encode("utf-8"))
                existing_files.append(file_path)

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
        )
        status = "ok" if dispatch_result.exit_code == 0 else "dispatch_error"
    else:
        # Dry run - create a dry dispatch result
        from router.dispatcher import DispatchResult
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
    if not os.path.exists(os.path.dirname(report_path)):
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
    write_report(report, report_path)

    # Print report to stdout if --json is requested
    if args.json:
        print()
        print("=" * 50 + " VERIFICATION REPORT (JSON) " + "=" * 50)
        import json
        print(json.dumps(report.model_dump(), indent=2))

    # Exit with appropriate code
    if dispatch_result and dispatch_result.exit_code != 0:
        sys.exit(dispatch_result.exit_code)

    sys.exit(0)


if __name__ == "__main__":
    main_cli()
