# Changelog

## [Unreleased]
### Fixed
- S-1 header-whitelist comment corrected per live smoke (2026-08-28): the `ark.talaga.my.id` gateway accepts only `Authorization: Bearer` — `x-api-key` returns 401 — so Claude Code integration must set `ANTHROPIC_AUTH_TOKEN`, not `ANTHROPIC_API_KEY`. The allowlist is unchanged; only the comment was wrong.
### Verified (live smoke)
- First live round-trip `csmart start → /v1/messages → ark.talaga.my.id`: HTTP 200, complete SSE (`message_start` → `content_block_delta` ×64 → `message_stop`), model reply returned; AST scan 25 files + Ollama triage ran; pipeline trace `status=ok`.

## [2.1.0] — 2026-08-28
### Added
- `router/report.py`: `StatsSummary` + `load_report()`/`aggregate_reports()` — `csmart stats` aggregates `.csmart/*.json` reports + per-event counts from session JSONL (R-3)
- `router/logs_viewer.py`: `csmart logs` viewer (`--tail`, `--follow`, `--event`) — stdlib-only plain-text render, no new third-party deps (N-5); `csmart stats` subcommand (F-03)
- F-13: `create_report(..., skeleton_bytes=...)` computes a real `estimated_tokens_saved` estimate (was `None`)
- `OLLAMA_TRIAGE_MODEL` env override — `triage_model()` single source shared by routing, `csmart status`, and `check_ollama_health` (S-6)
- RTK/DRIP dev tooling: `scripts/verify.sh` (RTK-safe test/typecheck/smoke gates), `scripts/drip-refresh.sh`, `DEVELOPMENT.md` (implements arsitektur §13.1)
### Security
- S-1: upstream header whitelist — only `authorization`, `x-api-key`, `content-type`, `accept`, `anthropic-version`, `anthropic-beta`, `x-app` forwarded; `cookie`/`user-agent`/`sec-*`/`origin` stripped (overridable via `CSMART_HEADER_ALLOWLIST`)
- S-2: loopback-only enforcement (403) via `ipaddress.is_loopback` (covers `127.0.0.0/8`, `::1`, `::ffff:7f00:1`); per-IP token-bucket rate limit (429 + `Retry-After`, `CSMART_RATE_LIMIT_PER_MIN`) with loopback exempt; CORS allow-origin gated on loopback `Origin` (no bare `*`)
- P-5: bounded body reader `_read_body_bounded()` (streaming early-abort over `request.stream()`) closes the chunked/no-Content-Length OOM bypass; Content-Length pre-check fast path; JSON `413`/`400` responses (`BodyTooLargeError`)
### Fixed
- `_keyword_heuristic` attribution bug: signature-line keyword hits fabricated pseudo-file entries (e.g. `- def check()`) — now attributed to the current file block (T-4 regression test)
- `check_ollama_health` probed the legacy `OLLAMA_MODEL` — now probes `triage_model()`
### Tests
- 84 → 128 hermetic tests (Wave 4: report aggregator, logs viewer, CLI subparsers; Wave 5: loopback/rate-limit/body-cap/header-whitelist, model env, heuristic attribution)

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
