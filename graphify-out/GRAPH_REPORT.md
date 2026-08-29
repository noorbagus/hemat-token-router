# Graph Report - hemat-token-router  (2026-08-30)

## Corpus Check
- 52 files · ~65,262 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1255 nodes · 2237 edges · 73 communities (68 shown, 5 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 47 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ae95052c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_tool_shadow.py
- LRURoutingCache
- mock_upstream
- SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing
- StructuredLogger
- test_e2e_proxy.py
- CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)
- test_ast_extractor.py
- test_cli.py
- tool_shadow.py
- test_proxy_inject.py
- test_ollama_scorer.py
- RoutingResult
- TTLRoutingCache
- ShadowStreamer
- BodyTooLargeError
- [Unreleased]
- GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)
- A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct
- test_logger.py
- handle_messages_request
- test_proxy.py
- csmart - Claude Smart Local Routing
- run_local_routing
- test_report.py
- dispatcher.py
- TASKS.md - hemat-token-router (csmart.py)
- ADR - hemat-token-router (csmart.py)
- CONTRACTS.md — Inter-track Contracts (frozen)
- test_routing_cache.py
- logs_viewer.py
- main_cli
- Development Environment
- verify.sh
- test_proxy_server.py
- forward_streaming_request
- _truncate_routing_prompt
- test_csmart_proxy.py
- _clamp_max_tokens
- _log
- _mock_upstream
- drip-refresh.sh
- csmart
- Any
- _iter_sse_events
- handle_messages
- _build_upstream_headers
- csmart_proxy.py
- test_logs_viewer.py
- _run
- sanitize_payload
- test_csmart_proxy_openai.py
- _collect_sse
- test_empty_tool_input_defensive_error
- _post_messages
- _hermetic
- transform_anthropic_to_openai_responses
- test_full_chain_event_sequence
- test_shadow_rounds_bounded_at_three
- report.py
- csmart-lite Comparison — Gap Dua Arah (fork partner)
- Leak Vectors — Claude Code & csmart
- csmart Pipeline — Diagram & Checklist
- transform_anthropic_to_openai_chat
- Response
- _safe_json_loads
- logger.py
- apply_gate
- litellm-start.sh
- capture_logger
- test_max_tokens_above_floor_preserved

## God Nodes (most connected - your core abstractions)
1. `StructuredLogger` - 43 edges
2. `_run()` - 32 edges
3. `_run()` - 32 edges
4. `RoutingResult` - 31 edges
5. `mock_upstream()` - 27 edges
6. `_sse_text()` - 23 edges
7. `main_cli()` - 22 edges
8. `execute_local_tool()` - 22 edges
9. `build_parser()` - 20 edges
10. `handle_messages()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `main_cli()` --calls--> `dispatch_claude()`  [INFERRED]
  csmart.py → router/cli_dispatch.py
- `main_cli()` --calls--> `resolve_under_base()`  [INFERRED]
  csmart.py → router/safe_path.py
- `test_scan_counts_only_supported_extensions()` --uses--> `StructuredLogger`  [INFERRED]
  tests/test_ast_extractor.py → router/logger.py
- `test_scan_counts_parse_failure()` --uses--> `StructuredLogger`  [INFERRED]
  tests/test_ast_extractor.py → router/logger.py
- `test_scan_emits_ast_scanned()` --uses--> `StructuredLogger`  [INFERRED]
  tests/test_ast_extractor.py → router/logger.py

## Import Cycles
- None detected.

## Communities (73 total, 5 thin omitted)

### Community 0 - "test_tool_shadow.py"
Cohesion: 0.06
Nodes (66): execute_local_tool(), _extract_message_content(), Execute a local exploration tool against a base_dir-scoped sandbox. Args:…, Pull text out of an ``ollama.chat``-shaped response (or a plain string)., Summarize large non-reader tool output via Ollama; short output passes through.…, summarize_exploration(), capture_logger(), fixture (+58 more)

### Community 1 - "LRURoutingCache"
Cohesion: 0.11
Nodes (13): LRURoutingCache, Thread-safe bounded caching for routing results with LRU and TTL variants. This…, Thread-safe bounded LRU cache for RoutingResult keyed by session key. Semantics…, Lookup a cached entry and bump its recency if present., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing)., _hermetic() (+5 more)

### Community 2 - "mock_upstream"
Cohesion: 0.10
Nodes (28): cwd_tmp(), mock_upstream(), fixture, Install a MockTransport upstream; returns a list recording each request.…, QG-04: text content_block_delta events reach the client immediately., model == OLLAMA_MODEL routes to {OLLAMA_BASE_URL}/v1/messages, auth stripped., S-2: a non-loopback peer is rejected before any routing/upstream call., S-2: CSMART_ALLOW_EXTERNAL=1 lets a non-loopback peer through. (+20 more)

### Community 3 - "SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing"
Cohesion: 0.04
Nodes (46): 10. Observability & Metrics, 11. Rencana Implementasi (Phase-by-Phase), 12. Rencana Testing & Verification Matrix, 13.1 Dev Environment: RTK & DRIP Interference Handling (READ/WRITE), 13. Deployment & Standard Operating Environment (SOP), 14. Risiko & Mitigasi, 15. Open Decisions (item yang perlu dikonfirmasi), 16. Referensi (+38 more)

### Community 4 - "StructuredLogger"
Cohesion: 0.11
Nodes (13): Path, Store the per-turn trace id stamped onto subsequent records. The id lives in a…, Mask a sensitive value. Always returns the fixed placeholder., Block until all pending records have been written to disk., Flush, stop the writer thread, and close the log file. Idempotent., Serialize one record as a JSONL line. False if the lock could not be acquired., Coerce non-JSON-serializable values to str so the writer never chokes., Non-blocking structured logger backed by a bounded queue + one daemon writer… (+5 more)

### Community 5 - "test_e2e_proxy.py"
Cohesion: 0.11
Nodes (38): _hermetic(), _make_client(), _mock_upstream(), _parse_anthropic_sse(), _post(), Any, AsyncClient, asyncio (+30 more)

### Community 6 - "CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)"
Cohesion: 0.06
Nodes (32): 1.1 Peran komponen, 1.2 Topologi makro, 2.1 Pydantic models / DTO (fakta dari kode), 2.2 Class & function signature utama, 2.3 Kontrak antar-stage (alur data), 3.1 Flow `POST /v1/messages` saat ini, 3.2 Detail transformasi payload per stage, 4.1 Status implementasi (fakta) (+24 more)

### Community 7 - "test_ast_extractor.py"
Cohesion: 0.11
Nodes (33): extract_ast_skeleton(), Scan a project directory recursively for supported source files, extracting AST…, Extract AST skeleton (function/class signatures) from a source file. Args:…, scan_project_codebase(), capture_logger(), fixture, Path, Unit tests for ast_extractor.py (+25 more)

### Community 8 - "test_cli.py"
Cohesion: 0.05
Nodes (48): ArgumentParser, build_parser(), CSmartParser, Build the CLI argument parser. Shared flags live on a single parent parser…, ArgumentParser that routes ``start``/``status`` to subparsers while letting any…, Return the first positional token in ``argv``, skipping flags and the value…, Namespace, capture_logger() (+40 more)

### Community 9 - "tool_shadow.py"
Cohesion: 0.09
Nodes (45): is_within(), PathTraversalError, Path, Path validation helpers for safe file access (anti path-traversal). Frozen…, Raised when a path resolves outside the allowed base directory., Resolve *path* to a real absolute path guaranteed inside *base_dir*. Symlink-…, Return True if *path* resolves inside *base_dir* (never raises)., resolve_under_base() (+37 more)

### Community 10 - "test_proxy_inject.py"
Cohesion: 0.09
Nodes (37): inject_context_to_messages(), Inject pre-loaded file context into the last user message. Path-safety (F-09):…, capture_logger(), cwd_tmp(), _last_user_content(), fixture, Hermetic tests for router/proxy.inject_context_to_messages (F-09 path safety).…, FIX #3: expanding ['a.py'] (which does `import b`) yields ['a.py', 'b.py'], and… (+29 more)

### Community 11 - "test_ollama_scorer.py"
Cohesion: 0.08
Nodes (34): _keyword_heuristic(), Truncate an exception string to ``max_len`` chars, appending "..." when cut., Robust fallback heuristic: weighted keyword matching per file from the…, Identify target files to modify based on user prompt using Ollama JSON output.…, route_target_files(), _truncate_error(), capture_logger(), fixture (+26 more)

### Community 12 - "RoutingResult"
Cohesion: 0.11
Nodes (27): BaseModel, RoutingResult, _gate_applied_record(), Unit tests for gate.py budget-aware filtering., Test that confidence exactly equal to threshold passes., Test fallback when overall confidence below but some files pass? Actually all…, GATE_APPLIED emitted with status=pass when all candidates fit., GATE_APPLIED emitted with status=fallback when budget forces a drop. (+19 more)

### Community 13 - "TTLRoutingCache"
Cohesion: 0.10
Nodes (14): Read TTL from environment variable CSMART_ROUTING_TTL if present., Return current effective TTL from environment or default., Lookup a cached entry, evicting if stale (older than TTL)., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing)., Thread-safe bounded TTL cache for RoutingResult keyed by context directory.…, TTLRoutingCache (+6 more)

### Community 14 - "ShadowStreamer"
Cohesion: 0.15
Nodes (11): Any, Shadow loop (N-4 / QG-03 / QG-04): drives the outbound SSE stream with…, Stream one upstream round. Sets ``self._pending_held`` on exit. The injected…, Execute each held exploration tool locally (parallel) and summarize. Defensive…, Reassemble ``partial_json`` fragments into a tool input dict., Append the assistant tool_use + user tool_result turns., Drives the outbound SSE stream with exploration tool-use shadowing. For each…, Yield SSE bytes to the client, looping internal shadow rounds. (+3 more)

### Community 15 - "BodyTooLargeError"
Cohesion: 0.40
Nodes (5): Exception, BodyTooLargeError, Raised when the upstream gateway is unreachable after retries., Raised when a request body exceeds the configured byte cap., UpstreamError

### Community 16 - "[Unreleased]"
Cohesion: 0.10
Nodes (19): [2.0.0] — 2026-08-28, [2.1.0] — 2026-08-28, A/B Test: request-count vs output correctness (2026-08-28), Added, Added, Changed, Changelog, Fixed (+11 more)

### Community 17 - "GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)"
Cohesion: 0.11
Nodes (17): 1. Ringkasan Eksekutif (Verdict), 2. Gap Matrix per Komponen Target, 3.1 Functional Requirements, 3.2 Non-Functional Requirements, 3. Mapping Requirement Target → Status Baseline, 4.1 Critical — Entrypoint & Runtime Bug (kerjakan paling dulu), 4.2 Feature Baru — Observability & Shadowing (inti v2.0), 4.3 Refactor — Proxy Engine & Ownership (+9 more)

### Community 18 - "A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct"
Cohesion: 0.11
Nodes (17): A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct, Akar masalah (atribusi), Baseline working tree (rusak sebelum uji), Caveat (kejujuran pengukuran), Detail direct S1 (definitif, MAX_ROUNDS=12), Detail direct S2 (gagal), Hasil, Hasil aplikasi (+9 more)

### Community 19 - "test_logger.py"
Cohesion: 0.15
Nodes (17): logger(), fixture, Path, Hermetic tests for router/logger.py (StructuredLogger, Track D — CONTRACTS.md…, Two interleaved tasks must not clobber each other's trace id. Deterministic…, asyncio.to_thread must carry the trace context into the worker thread — this is…, _read_records(), test_close_flushes_pending() (+9 more)

### Community 20 - "handle_messages_request"
Cohesion: 0.17
Nodes (16): JSONResponse, _context_dir(), handle_messages_request(), _max_body_bytes(), passthrough_request(), proxy_handler(), api_route, Request (+8 more)

### Community 21 - "test_proxy.py"
Cohesion: 0.17
Nodes (14): _hermetic(), fixture, Hermetic tests for the csmart reverse-proxy engine (``router.dispatcher``). No…, /v1/messages is intercepted and the mocked SSE upstream is streamed back., Run a coroutine to completion with a fresh event loop., Clear proxy caches + patch routing so no test touches Ollama/AST., CORS preflight OPTIONS allows a loopback Origin and echoes it., CORS preflight with a non-loopback Origin gets no allow-origin header. (+6 more)

### Community 22 - "csmart - Claude Smart Local Routing"
Cohesion: 0.08
Nodes (23): 1. Routing Result (`RoutingResult` - pydantic), 2. Gate Result (`GateResult` - pydantic), 3. Final Report (`CsmartReport` - pydantic), Anti-Spaghetti Coding Rules, Arsitektur (Pipeline Pattern), Aturan, Aturan untuk AI Coding Tools (CLAUDE.md ini dibaca sebelum edit), CLI Usage (+15 more)

### Community 23 - "run_local_routing"
Cohesion: 0.20
Nodes (10): _cap_skeleton(), _get_or_scan_ast(), Scan the project once per context_dir (cached). Non-blocking (P-2). Returns…, Cap the AST skeleton sent to Ollama while keeping every file header. Lines…, Run local routing: AST scan (cached) -> Ollama scoring -> gate. Async and non-…, run_local_routing(), A skeleton already under the cap is returned byte-identical., Over budget: every // header is kept, the longest - signatures go first. (+2 more)

### Community 24 - "test_report.py"
Cohesion: 0.11
Nodes (29): aggregate_reports(), CsmartReport, load_report(), Write JSON report to file, creating directory if needed., Full structured report for a csmart execution., Load a CsmartReport from a JSON file. FileNotFoundError and…, Aggregate multiple report files into a StatsSummary. Skips any path that is…, write_report() (+21 more)

### Community 25 - "dispatcher.py"
Cohesion: 0.13
Nodes (22): middleware, _allow_external(), _consume_token(), _expand_selected_with_imports(), _import_candidates(), _is_loopback(), _module_candidates(), _origin_loopback() (+14 more)

### Community 26 - "TASKS.md - hemat-token-router (csmart.py)"
Cohesion: 0.18
Nodes (10): Kontrak bersama (Task 1 deliverable - field names EXACT, jangan diganti), Phase 1: Eksplorasi lingkungan, Phase 2: Desain & ADR, Phase 3: Implementasi, Phase 4: Verifikasi akhir (setelah semua task merge), Tasks, TASKS.md - hemat-token-router (csmart.py), Wave 0-3 — Execution Log (2026-08-27/28) (+2 more)

### Community 27 - "ADR - hemat-token-router (csmart.py)"
Cohesion: 0.22
Nodes (8): ADR-1: Dependency AST - tree-sitter-language-pack (bukan tree-sitter-languages), ADR-2: Modular monolith + pipeline pattern, ADR-3: Confidence gate dengan fallback chain (fail-open default, strict opt-in), ADR-4: Budget cap dengan whole-chunk drop (bukan byte truncation), ADR-5: Report JSON selalu dibuat; --json hanya mengontrol stdout, ADR-6: Dispatch Claude Code CLI via stdin, single-shot, ADR - hemat-token-router (csmart.py), Exit codes (kontrak global)

### Community 28 - "CONTRACTS.md — Inter-track Contracts (frozen)"
Cohesion: 0.25
Nodes (7): 1. `router/safe_path.py` — anti path-traversal (dibuat Wave 0), 2. `router/logger.py` — StructuredLogger (Track D), 3. `router/tool_shadow.py` — exploration tool executor (Track E), 4. `router/dispatcher.py` public API (Wave 2 — proxy engine), 5. `router/cli_dispatch.py` (Wave 2 — CLI subprocess), 6. Ownership & Rules, CONTRACTS.md — Inter-track Contracts (frozen)

### Community 29 - "test_routing_cache.py"
Cohesion: 0.31
Nodes (12): capture_logger(), fixture, Hermetic tests for router/routing_cache.py structured-log cache events., _read_records(), test_lru_get_miss(), test_lru_put_eviction_reports_evicted_key(), test_lru_put_then_get_hit(), test_ttl_get_expired() (+4 more)

### Community 30 - "logs_viewer.py"
Cohesion: 0.12
Nodes (24): cmd_logs(), cmd_stats(), _count_events(), _file_eof_offsets(), follow_log(), _format_stats_table(), _parse_line(), Read-only viewer for csmart JSONL audit logs (no new third-party deps).… (+16 more)

### Community 31 - "main_cli"
Cohesion: 0.19
Nodes (14): cmd_start(), cmd_status(), main_cli(), Check health of Ollama and upstream gateway., Start the local reverse proxy server., Entry point. Original CLI mode: direct dispatch to Claude Code with pre-routed…, check_ollama_health(), check_upstream_health() (+6 more)

### Community 32 - "Development Environment"
Cohesion: 0.29
Nodes (6): Development Environment, DRIP — Read Layer, Multi-Agent SDLC Rules, Quick Start, RTK — Command Layer, Verify the Tooling

### Community 33 - "verify.sh"
Cohesion: 0.67
Nodes (6): cmd_all(), cmd_smoke(), cmd_test(), cmd_typecheck(), verify.sh script, usage()

### Community 34 - "test_proxy_server.py"
Cohesion: 0.13
Nodes (16): _asgi_request(), Request, Hermetic server tests for the csmart proxy engine (``router.dispatcher``).…, FIX #2: the session-less TTL cache key includes the prompt, so a different…, model != OLLAMA_MODEL keeps the existing upstream route + auth (unchanged)., Convert an httpx.Request into a Starlette Request (scope + receive). Used for…, P-5: read_full_body catches the chunked/no-content-length oversized path., S-1: _build_upstream_headers forwards only allowlisted headers. (+8 more)

### Community 35 - "forward_streaming_request"
Cohesion: 0.19
Nodes (16): extract_last_user_prompt(), _forward_streaming_ollama(), forward_streaming_request(), Any, AsyncClient, Response, Forward a streaming request to upstream and stream the SSE response back., Forward a request for ``OLLAMA_MODEL`` to local Ollama, streaming SSE back. No… (+8 more)

### Community 36 - "_truncate_routing_prompt"
Cohesion: 0.33
Nodes (6): Keep the TAIL of a routing prompt so cold prefill stays small (P-2). The…, _truncate_routing_prompt(), Long prompts are cut to the TAIL (the task statement lives at the end)., A short prompt is returned unchanged., test_truncate_routing_prompt_keeps_tail(), test_truncate_routing_prompt_short_unchanged()

### Community 37 - "test_csmart_proxy.py"
Cohesion: 0.06
Nodes (57): _canonicalize_path(), check_security_guardrails(), Unmask markers on the client-bound path without splitting them at chunk…, Expand ~ and resolve symlinks/.. so pattern checks cannot be bypassed., Return a violation message if *tool_input* touches credentials, else None., StreamingRedactor, _hermetic(), _log_text() (+49 more)

### Community 38 - "_clamp_max_tokens"
Cohesion: 0.50
Nodes (4): _clamp_max_tokens(), _min_max_tokens(), Floor for ``max_tokens`` (mirrors ark Smart Gate). Env-overridable., Force ``body["max_tokens"]`` up to the floor, in place. Issue #1 fix: below the…

### Community 39 - "_log"
Cohesion: 0.11
Nodes (19): Connection, get_ccr_payload(), get_db(), _log(), Transform OpenAI Chat Completions SSE stream → Anthropic Messages SSE stream.…, Blank sensitive values by key name (never prints credentials)., Emit one redacted JSONL event. Never raises; never logs secrets., Shannon entropy in bits per character (base 2). (+11 more)

### Community 40 - "_mock_upstream"
Cohesion: 0.20
Nodes (14): _mock_upstream(), _post(), AsyncClient, asyncio, Make a POST request to /v1/messages with proper headers., End-to-end test: Anthropic request -> OpenAI transformation -> response back to…, Test that existing Anthropic flow still works unchanged., Test that client Authorization header is never forwarded to upstream (same as… (+6 more)

### Community 45 - "Any"
Cohesion: 0.27
Nodes (9): _format_event(), _iter_sse_events(), _parse_sse_data(), ProxyStreamer, Any, Response, Open the upstream stream, canonical-serialize the body, yield SSE events., Stream upstream SSE to the client, shadowing tool_use locally: -… (+1 more)

### Community 46 - "_iter_sse_events"
Cohesion: 0.32
Nodes (7): _iter_sse_events(), _parse_sse_data(), Any, Response, SSE (Server-Sent Events) line parsing for the csmart proxy (N-3). Pure parsing:…, Join ``data:`` lines and JSON-decode them into a payload dict., Parse an httpx streaming response into ``(event_name, payload)`` tuples.

### Community 47 - "handle_messages"
Cohesion: 0.12
Nodes (17): align_prefix_3_region(), clamp_max_tokens(), clean_openai_model_name(), detect_openai_endpoint_type(), handle_messages(), _mock_anthropic_json(), passthrough(), api_route (+9 more)

### Community 48 - "_build_upstream_headers"
Cohesion: 0.40
Nodes (5): _build_upstream_headers(), _header_allowlist(), Request, HTTP header helpers for the csmart reverse proxy (S-1 header whitelist). Pure…, Copy only allowlisted client headers upstream (S-1 header whitelist).…

### Community 49 - "csmart_proxy.py"
Cohesion: 0.15
Nodes (14): _b64url_key(), init_db(), keepalive_worker(), lifespan(), _load_gateway_env(), _mask_dict(), _mock_anthropic_stream(), Transform OpenAI Responses API SSE stream → Anthropic Messages SSE stream.… (+6 more)

### Community 50 - "test_logs_viewer.py"
Cohesion: 0.18
Nodes (15): dispatch_claude(), DispatchResult, BaseModel, CLI subprocess dispatch for csmart (moved from ``router/dispatcher.py``). Wave…, Result of a Claude CLI dispatch invocation. Field names are frozen…, Read the full content of a file (utf-8)., Dispatch a Claude CLI request with pre-loaded file context. Args: files: List…, read_file_content() (+7 more)

### Community 51 - "_run"
Cohesion: 0.14
Nodes (14): P-0: TTL=0 disables reuse — every session-less request re-routes., Run a coroutine to completion with a fresh event loop., P-3: upstream connect timeout -> clean SSE error, no hang, bounded retries., P-5 MAJOR: an oversized chunked body aborts early, never full-buffers., S-2: loopback peers are exempt from rate limiting (no spurious 429s)., run_local_routing hands Ollama a skeleton capped to the env budget., P-0: session-less requests with the SAME prompt route via Ollama once., _run() (+6 more)

### Community 52 - "sanitize_payload"
Cohesion: 0.11
Nodes (20): _extract_last_text(), is_openai_model(), _mask_text_block(), Strip ANSI escapes and head-tail truncate logs > 2KB., Sanitize + mask a text block (dict with 'text' / string)., In-place: sanitize + mask system and message content, block tool_use.input., Pick a model for this request. Pinned per session (cache stability)., Detect if model is OpenAI-native (requires protocol transformation). (+12 more)

### Community 53 - "test_csmart_proxy_openai.py"
Cohesion: 0.11
Nodes (17): Hermetic tests for OpenAI-native protocol adapter in csmart_proxy.py. Runs…, Test basic Anthropic -> OpenAI Chat Completions transformation., Test tool format conversion from Anthropic -> OpenAI., Test transformation handles Anthropic block format content., Test endpoint type detection based on model name., Anthropic reasoning/thinking config -> Responses API effort (max clamped)., transform should carry reasoning.effort into the Responses payload., A tool_result whose content is a dict must become valid JSON in the Responses… (+9 more)

### Community 54 - "_collect_sse"
Cohesion: 0.12
Nodes (17): _collect_sse(), Any, Build SSE response body from a list of events., Consume the async transform generator synchronously., Real Responses API sends delta as STRING. Regression test for the…, Responses API function_call: output_item.added -> content_block_start tool_use,…, A provider that emits ONLY response.function_call_arguments.done (full args…, A provider that emits ONLY response.output_text.done (final full text) with no… (+9 more)

### Community 55 - "test_empty_tool_input_defensive_error"
Cohesion: 0.33
Nodes (6): A tool_use block that streams NO input_json deltas (input stays {})., A full round: message envelope + one tool_use block with empty input., Issue #1: a tool_use with no streamed args yields an actionable error…, _sse_tool_use_empty_input(), _sse_tool_use_empty_round(), test_empty_tool_input_defensive_error()

### Community 56 - "_post_messages"
Cohesion: 0.12
Nodes (18): _post_messages(), A single content-block SSE fragment (no message envelope)., A full round: message envelope + one tool_use block., POST /v1/messages to the ASGI app and return the response., QG-03: an exploration tool_use is held + resolved locally, not forwarded., QG-04: Edit/Write tool_use is forwarded immediately, never shadowed., Issue #1: max_tokens below the floor is raised to the floor upstream., Issue #1: absent max_tokens is defaulted to the floor. (+10 more)

### Community 60 - "_hermetic"
Cohesion: 0.40
Nodes (5): _hermetic(), fixture, MonkeyPatch, Path, Reset all global state between tests for hermeticity.

### Community 61 - "transform_anthropic_to_openai_responses"
Cohesion: 0.25
Nodes (8): _convert_anthropic_message_to_openai_responses(), _convert_anthropic_tool_to_openai_responses(), Convert Anthropic tool format → OpenAI Responses API tool format. Responses API…, Convert Anthropic message → LIST of OpenAI Responses API input items. Returns a…, Transform Anthropic Messages API payload → OpenAI Responses API payload.…, Resolve Anthropic reasoning/thinking config to an OpenAI Responses effort.…, _resolve_reasoning_effort(), transform_anthropic_to_openai_responses()

### Community 62 - "test_full_chain_event_sequence"
Cohesion: 0.50
Nodes (4): The real pipeline logs every source event once, in order, one trace_id.…, Read every JSONL record written to a StructuredLogger in ``tmp_path``., _read_records(), test_full_chain_event_sequence()

### Community 63 - "test_shadow_rounds_bounded_at_three"
Cohesion: 0.50
Nodes (4): A full round with ``count`` consecutive GrepTool tool_use blocks., N-4/OD-3: with 5 exploration tool_use, <= 3 are held, the rest pass through., _sse_n_tool_uses(), test_shadow_rounds_bounded_at_three()

### Community 66 - "report.py"
Cohesion: 0.22
Nodes (10): DispatchResult, create_report(), ExecutionMetrics, BaseModel, RoutingResult, JSON report schema for csmart execution. Full structured report that persists…, Create a complete CsmartReport with proper timestamp and metrics., Timing and size metrics for the entire prepass. (+2 more)

### Community 67 - "csmart-lite Comparison — Gap Dua Arah (fork partner)"
Cohesion: 0.22
Nodes (8): 1. Kesimpulan, 2. Gap di kita (csmart-lite sudah punya) — 10, 3. Gap di csmart-lite (kita sudah punya) — 5, 4. Gap shared (dua-duanya masih bolong) — 10, 5. Tool calling — fokus utama, 6. Action items, 7. Referensi, csmart-lite Comparison — Gap Dua Arah (fork partner)

### Community 68 - "Leak Vectors — Claude Code & csmart"
Cohesion: 0.25
Nodes (7): 1. Peta per tool call Claude Code, 2. Vektor dari riset internet, 3. Cakupan penutup per layer, 4. Prioritas usulan, 5. Yang TIDAK bisa ditutup proxy csmart, Leak Vectors — Claude Code & csmart, Tujuan

### Community 69 - "csmart Pipeline — Diagram & Checklist"
Cohesion: 0.25
Nodes (7): 1. Pipeline Overview (mermaid), 2. Stage-by-Stage Checklist (proxy path), 3. Pipeline Gaps — Priority (X marks the spot), 4. CLI Mode Pipeline (router/* — `csmart` CLI), 5. SSE Event Sequence (Issue #4 — evidence), 6. Cross-reference: issue & doc, csmart Pipeline — Diagram & Checklist

### Community 70 - "transform_anthropic_to_openai_chat"
Cohesion: 0.25
Nodes (8): _convert_anthropic_message_to_openai(), _convert_anthropic_tool_to_openai(), _extract_system_text(), Extract concatenated system text from Anthropic system format (str or list)., Convert Anthropic tool format (input_schema) → OpenAI Chat Completions tool…, Convert Anthropic message format → OpenAI Chat Completions message., Transform Anthropic Messages API payload → OpenAI Chat Completions API payload., transform_anthropic_to_openai_chat()

### Community 71 - "Response"
Cohesion: 0.32
Nodes (8): Request, Response, Build a simple MockTransport handler that returns complete text SSE., Build a MockTransport handler that returns streaming tool call., MockTransport handler that rejects with an HTTP error., _reject_upstream(), _simple_upstream(), _tool_use_upstream()

### Community 72 - "_safe_json_loads"
Cohesion: 0.33
Nodes (6): Transform OpenAI Responses API JSON response → Anthropic Messages JSON…, Transform OpenAI Chat Completions JSON response → Anthropic Messages JSON…, Parse JSON string, fall back to {} on failure., _safe_json_loads(), transform_openai_chat_to_anthropic_json(), transform_openai_responses_to_anthropic_json()

### Community 73 - "logger.py"
Cohesion: 0.25
Nodes (7): Node, _get_signature_first_line(), AST-based code skeleton extraction using tree-sitter. Extracts…, Extract the first line of a node's signature from source bytes., Recursively traverse AST, collect signatures of target node types., _traverse_collect_signatures(), StructuredLogger for csmart — non-blocking, thread-safe JSONL audit logging.…

### Community 74 - "apply_gate"
Cohesion: 0.22
Nodes (9): apply_gate(), GateResult, hook_test_helper(), BaseModel, RoutingResult, Budget-aware gate that filters candidate files based on confidence and token…, Result of gate application after confidence and budget filtering., Test helper to verify graphify post-commit hook rebuilds the graph. (+1 more)

## Knowledge Gaps
- **171 isolated node(s):** `1. `router/safe_path.py` — anti path-traversal (dibuat Wave 0)`, `2. `router/logger.py` — StructuredLogger (Track D)`, `3. `router/tool_shadow.py` — exploration tool executor (Track E)`, `4. `router/dispatcher.py` public API (Wave 2 — proxy engine)`, `5. `router/cli_dispatch.py` (Wave 2 — CLI subprocess)` (+166 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StructuredLogger` connect `StructuredLogger` to `test_tool_shadow.py`, `test_proxy_server.py`, `test_ast_extractor.py`, `test_cli.py`, `logger.py`, `test_proxy_inject.py`, `test_ollama_scorer.py`, `RoutingResult`, `capture_logger`, `test_logger.py`, `test_routing_cache.py`, `test_full_chain_event_sequence`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Why does `GateResult` connect `apply_gate` to `report.py`, `test_cli.py`, `test_logs_viewer.py`, `run_local_routing`, `test_report.py`, `dispatcher.py`, `main_cli`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Why does `resolve_under_base()` connect `tool_shadow.py` to `dispatcher.py`, `test_proxy_inject.py`, `main_cli`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 13 inferred relationships involving `StructuredLogger` (e.g. with `test_scan_counts_only_supported_extensions()` and `test_scan_counts_parse_failure()`) actually correct?**
  _`StructuredLogger` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `RoutingResult` (e.g. with `LRURoutingCache` and `TTLRoutingCache`) actually correct?**
  _`RoutingResult` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `1. `router/safe_path.py` — anti path-traversal (dibuat Wave 0)`, `2. `router/logger.py` — StructuredLogger (Track D)`, `3. `router/tool_shadow.py` — exploration tool executor (Track E)` to the rest of the system?**
  _171 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_tool_shadow.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06105834464043419 - nodes in this community are weakly interconnected._