# Changelog

## [Unreleased]
### A/B Test: request-count vs output correctness (2026-08-28)
- `docs/ab-test-request-count.md` — proxy (csmart inject + shadow) vs direct agent loop pada 2 task refactor: ARK calls **10→1** (S1) dan **≥12→2** (S2) = savings request 83-90%.
- **Output verification negatif**: kedua output proxy **tidak dapat dipakai** (S2 = patch malformed + constructor fiktif `max_size`/`env_ttl_key`; S1 = implementasi duplikat `routing_cache.py`). Working tree baseline sudah 15 test gagal (WIP migrasi cache setengah jadi) dan output model tidak memperbaikinya. Savings request real, tapi value belum terbukti.
- Root cause: triage tidak ikut sertakan file yang di-import target (`routing_cache.py`); shadow summarize file `.py` >4000 char menghilangkan detail signature API; tidak ada execution/test feedback loop di jalur proxy.

### Performance (2026-08-28, issue #2 P0-P4)
- **P0 — TTL routing cache**: session-less (production) requests reuse the routing per `context_dir` for `CSMART_ROUTING_TTL` (default 120s, cap 16) — Qwen is **no longer called on message 2+ per burst** (verified `cache_hit=true` @ 0ms). Log field `cache_hit`.
- **P1 — triage model resident**: `keep_alive=-1` + `num_ctx=8192` in `ollama.chat()` — cold reload 18-26s eliminated.
- **P2-server — Ollama env**: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_MAX_LOADED_MODELS=1` (launchd plist; backup `.bak-20260828`). Measured prefill 139→214 t/s (+54%), decode 19→23 t/s (+21%).
- **P3 — smaller routing input**: `_cap_skeleton` (preserves every `// <path>` header, env `CSMART_ROUTING_SKELETON_MAX_CHARS` default 6000) + `_truncate_routing_prompt` (keeps tail, env `CSMART_ROUTING_PROMPT_MAX_CHARS` default 4000). Skeleton 2,600→1,775 tokens; output JSON 61→35 tokens (reasoning ≤10 words, capped ≤120 chars, minified single-line).
- **P4 — rounds counter fixed**: `SSE_STREAM_COMPLETE` logs `rounds=self.round - 1` (actual upstream calls) — single-round request now logs `rounds=1` (was 2).
### Verified (live, 2026-08-28)
- Warm `OLLAMA_TRIAGE` steady-state ≈ **2.5s** (was 4.7s) via prefix KV reuse; burst message 2+ = **0ms** routing (TTL cache hit); prefill cache-hit 15.7k-33k t/s; skeleton cap verified deterministic (26 `//` headers preserved).
- 139 hermetic tests pass, pyright 0 errors.

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
