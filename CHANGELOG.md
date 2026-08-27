# Changelog

## [2.0.0] — 2026-08-28
### Added
- `router/safe_path.py` — symlink-aware path-traversal guard (`resolve_under_base`/`is_within`) + frozen inter-track contracts in `CONTRACTS.md`
- `router/logger.py` — `StructuredLogger` JSONL (trace_id UUID, non-blocking, credential redaction) with 6 typed event constants
- `router/tool_shadow.py` — local exploration tool executor (GlobTool/GrepTool/View/LS/read_file/FileRead) + qwen summarizer for >4000-char outputs
- `router/cli_dispatch.py` — `dispatch_claude` + `DispatchResult` extracted from dispatcher (F-05 timeout, typed gate_info)
- FastAPI proxy engine: async SSE parser (aiter_lines + partial_json reassembly), `_ShadowStreamer` (≤3 exploration tool_use rounds, local exec + summarize via `asyncio.to_thread`, internal tool_result re-submit, real-time text/Edit/Write passthrough)
- Routing-once-per-session + AST cache; uuid4 trace_id; upstream timeout with 2 retries
- `csmart start/status` argparse subcommands (F-03)
### Fixed
- F-01/F-02: `SyntaxError` in `cmd_status()` and missing entrypoint — `csmart` now maps to `main_cli`
- F-06: `GateResult` typing — `dispatch_claude` consumes `router.gate.GateResult` via `.reason` (no `.message` access)
- F-09: Ollama-selected file paths validated before context injection (path traversal rejected)
- test_ast_extractor: assert JS class extraction instead of TS interface on `.js` fixture
### Changed
- `router/proxy.py` absorbed into `router/dispatcher.py` and deleted (no dual path, R-1)
- `dispatch_claude` relocated to `router/cli_dispatch.py`; `csmart.py` imports repointed, pyright-clean
- `pyproject.toml`: `tree-sitter-language-pack` pinned `>=1.15.8,<2`, added dev dependency group `pytest`
- Removed stale artifacts (`csmart.egg-info/`, `debug_ast.py`, `debug_interface.js`)
### Security
- Path-traversal guard `resolve_under_base` (symlink-aware via `Path.resolve`) applied to all external-input paths
- Structured-log redaction of `authorization`/`api_key`/`x-api-key`/`token` → `[REDACTED]`
### Tests
- 84 hermetic tests, 0 network/Ollama dependency: safe_path, logger, tool_shadow, cli, proxy server (SSE fixture), proxy inject
- Wave-3 review fix loop: +1 regression test (`test_main_cli_skips_path_traversal_selected_files`), 84 passed, pyright 0 errors
