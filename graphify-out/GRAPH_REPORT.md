# Graph Report - hemat-token-router  (2026-08-30)

## Corpus Check
- 63 files · ~77,101 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1325 nodes · 2320 edges · 91 communities (76 shown, 15 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 50 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2697ad79`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_tool_shadow.py
- tool_shadow.py
- test_proxy_server.py
- SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing
- StructuredLogger
- test_e2e_proxy.py
- CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)
- test_ast_extractor.py
- test_cli.py
- resolve_under_base
- test_proxy_inject.py
- test_ollama_scorer.py
- apply_gate
- TTLRoutingCache
- ShadowStreamer
- BodyTooLargeError
- [Unreleased]
- GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)
- A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct
- transform_anthropic_to_openai_responses
- handle_messages_request
- RoutingResult
- csmart - Claude Smart Local Routing
- run_local_routing
- test_report.py
- dispatcher.py
- TASKS.md - hemat-token-router (csmart.py)
- ADR - hemat-token-router (csmart.py)
- CONTRACTS.md — Inter-track Contracts (frozen)
- summarize_exploration
- test_logs_viewer.py
- main_cli
- Development Environment
- verify.sh
- _asgi_request
- forward_streaming_request
- _truncate_routing_prompt
- test_csmart_proxy.py
- _clamp_max_tokens
- GateResult
- AsyncClient
- drip-refresh.sh
- csmart
- Any
- _iter_sse_events
- handle_messages
- SecretVault
- csmart_proxy.py
- logger.py
- report.py
- sanitize_payload
- CSmartParser
- test_csmart_proxy_openai.py
- Request
- _post_messages
- test_adopt_gaps.py
- _import_candidates
- _read_records
- transform_openai_chat_to_anthropic_json
- asyncio
- load_report
- test_reader_long_passthrough_no_ollama
- run.sh
- clamp_max_tokens
- _build_upstream_headers
- csmart-lite Comparison — Gap Dua Arah (fork partner)
- Leak Vectors — Claude Code & csmart
- csmart Pipeline — Diagram & Checklist
- init-firewall.sh
- fixture
- autostart-proxy.sh
- apply-firewall.sh
- Firewall (egress DENY-BY-DEFAULT)
- logs_viewer.py
- litellm-start.sh
- _post
- _collect_sse
- api_route
- test_empty_tool_input_defensive_error
- MonkeyPatch
- post
- parametrize
- Path
- _hermetic
- Response
- Any
- capture_logger
- test_tool_names_contract

## God Nodes (most connected - your core abstractions)
1. `StructuredLogger` - 43 edges
2. `_run()` - 32 edges
3. `_run()` - 32 edges
4. `RoutingResult` - 31 edges
5. `mock_upstream()` - 27 edges
6. `_sse_text()` - 23 edges
7. `execute_local_tool()` - 22 edges
8. `main_cli()` - 22 edges
9. `handle_messages()` - 21 edges
10. `GateResult` - 20 edges

## Surprising Connections (you probably didn't know these)
- `_hermetic()` --calls--> `TTLRoutingCache`  [INFERRED]
  tests/test_proxy_server.py → router/routing_cache.py
- `_hermetic()` --calls--> `LRURoutingCache`  [INFERRED]
  tests/test_proxy_server.py → router/routing_cache.py
- `test_scan_counts_only_supported_extensions()` --uses--> `StructuredLogger`  [INFERRED]
  tests/test_ast_extractor.py → router/logger.py
- `test_scan_counts_parse_failure()` --uses--> `StructuredLogger`  [INFERRED]
  tests/test_ast_extractor.py → router/logger.py
- `test_scan_emits_ast_scanned()` --uses--> `StructuredLogger`  [INFERRED]
  tests/test_ast_extractor.py → router/logger.py

## Import Cycles
- None detected.

## Communities (91 total, 15 thin omitted)

### Community 0 - "test_tool_shadow.py"
Cohesion: 0.16
Nodes (27): execute_local_tool(), Execute a local exploration tool against a base_dir-scoped sandbox. Args:…, Hermetic tests for router.tool_shadow exploration tool executor. No live Ollama…, ../secret.txt' must not be read; an ERROR string is returned instead., An absolute path outside base_dir must not be read., base_dir reached through a symlink alias must still yield relative paths.…, Run a coroutine to completion with a fresh event loop., A successful local read emits exactly one TOOL_LOCAL_EXEC record. (+19 more)

### Community 1 - "tool_shadow.py"
Cohesion: 0.17
Nodes (22): _bounded(), _execute_local_tool_sync(), _get_path(), _normalize_tool_name(), Path, Exploration tool executor for the csmart shadow loop. Frozen contract at Wave 0…, Read a single file's text content (utf-8, lossy)., List directory entries as ``name (dir|file)`` lines. (+14 more)

### Community 2 - "test_proxy_server.py"
Cohesion: 0.08
Nodes (54): mock_upstream(), Hermetic server tests for the csmart proxy engine (``router.dispatcher``).…, FIX #2: the session-less TTL cache key includes the prompt, so a different…, P-0: TTL=0 disables reuse — every session-less request re-routes., A full round with ``count`` consecutive GrepTool tool_use blocks., Install a MockTransport upstream; returns a list recording each request.…, QG-04: text content_block_delta events reach the client immediately., model == OLLAMA_MODEL routes to {OLLAMA_BASE_URL}/v1/messages, auth stripped. (+46 more)

### Community 3 - "SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing"
Cohesion: 0.04
Nodes (46): 10. Observability & Metrics, 11. Rencana Implementasi (Phase-by-Phase), 12. Rencana Testing & Verification Matrix, 13.1 Dev Environment: RTK & DRIP Interference Handling (READ/WRITE), 13. Deployment & Standard Operating Environment (SOP), 14. Risiko & Mitigasi, 15. Open Decisions (item yang perlu dikonfirmasi), 16. Referensi (+38 more)

### Community 4 - "StructuredLogger"
Cohesion: 0.06
Nodes (37): Path, Store the per-turn trace id stamped onto subsequent records. The id lives in a…, Mask a sensitive value. Always returns the fixed placeholder., Block until all pending records have been written to disk., Flush, stop the writer thread, and close the log file. Idempotent., Serialize one record as a JSONL line. False if the lock could not be acquired., Coerce non-JSON-serializable values to str so the writer never chokes., Non-blocking structured logger backed by a bounded queue + one daemon writer… (+29 more)

### Community 5 - "test_e2e_proxy.py"
Cohesion: 0.11
Nodes (38): _hermetic(), _make_client(), _mock_upstream(), _parse_anthropic_sse(), _post(), Any, AsyncClient, asyncio (+30 more)

### Community 6 - "CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)"
Cohesion: 0.06
Nodes (32): 1.1 Peran komponen, 1.2 Topologi makro, 2.1 Pydantic models / DTO (fakta dari kode), 2.2 Class & function signature utama, 2.3 Kontrak antar-stage (alur data), 3.1 Flow `POST /v1/messages` saat ini, 3.2 Detail transformasi payload per stage, 4.1 Status implementasi (fakta) (+24 more)

### Community 7 - "test_ast_extractor.py"
Cohesion: 0.09
Nodes (39): Node, extract_ast_skeleton(), _get_signature_first_line(), AST-based code skeleton extraction using tree-sitter. Extracts…, Scan a project directory recursively for supported source files, extracting AST…, Extract the first line of a node's signature from source bytes., Recursively traverse AST, collect signatures of target node types., Extract AST skeleton (function/class signatures) from a source file. Args:… (+31 more)

### Community 8 - "test_cli.py"
Cohesion: 0.15
Nodes (21): ArgumentParser, build_parser(), Build the CLI argument parser. Shared flags live on a single parent parser…, Hermetic unit tests for csmart CLI parser + main_cli routing (Track A). These…, Shared flags must be inherited by subparsers too., An unknown token in subcommand position raises SystemExit. Note: a *bare* first…, A bare non-command token is a CLI prompt (not an error)., test_bare_noncommand_token_is_cli_prompt() (+13 more)

### Community 9 - "resolve_under_base"
Cohesion: 0.19
Nodes (21): is_within(), PathTraversalError, Path, Path validation helpers for safe file access (anti path-traversal). Frozen…, Raised when a path resolves outside the allowed base directory., Resolve *path* to a real absolute path guaranteed inside *base_dir*. Symlink-…, Return True if *path* resolves inside *base_dir* (never raises)., resolve_under_base() (+13 more)

### Community 10 - "test_proxy_inject.py"
Cohesion: 0.09
Nodes (39): _expand_selected_with_imports(), inject_context_to_messages(), Inject pre-loaded file context into the last user message. Path-safety (F-09):…, Append top-level-imported local modules to the triage-selected files. FIX #3…, capture_logger(), cwd_tmp(), _last_user_content(), fixture (+31 more)

### Community 11 - "test_ollama_scorer.py"
Cohesion: 0.08
Nodes (36): _keyword_heuristic(), Truncate an exception string to ``max_len`` chars, appending "..." when cut., Robust fallback heuristic: weighted keyword matching per file from the…, Ollama triage model, overridable via ``OLLAMA_TRIAGE_MODEL``., Identify target files to modify based on user prompt using Ollama JSON output.…, route_target_files(), triage_model(), _truncate_error() (+28 more)

### Community 12 - "apply_gate"
Cohesion: 0.10
Nodes (30): apply_gate(), RoutingResult, Apply confidence threshold and token budget gate to routing result. Rules: 1.…, capture_logger(), _gate_applied_record(), fixture, Unit tests for gate.py budget-aware filtering., Test that confidence exactly equal to threshold passes. (+22 more)

### Community 13 - "TTLRoutingCache"
Cohesion: 0.10
Nodes (24): Read TTL from environment variable CSMART_ROUTING_TTL if present., Return current effective TTL from environment or default., Lookup a cached entry, evicting if stale (older than TTL)., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing)., Thread-safe bounded TTL cache for RoutingResult keyed by context directory.…, TTLRoutingCache (+16 more)

### Community 14 - "ShadowStreamer"
Cohesion: 0.18
Nodes (10): Any, Stream one upstream round. Sets ``self._pending_held`` on exit. The injected…, Execute each held exploration tool locally (parallel) and summarize. Defensive…, Reassemble ``partial_json`` fragments into a tool input dict., Append the assistant tool_use + user tool_result turns., Drives the outbound SSE stream with exploration tool-use shadowing. For each…, Yield SSE bytes to the client, looping internal shadow rounds., ShadowStreamer (+2 more)

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

### Community 19 - "transform_anthropic_to_openai_responses"
Cohesion: 0.17
Nodes (12): _convert_anthropic_message_to_openai(), _convert_anthropic_message_to_openai_responses(), _convert_anthropic_tool_to_openai_responses(), Convert Anthropic message → LIST of OpenAI Responses API input items. Returns a…, Transform Anthropic Messages API payload → OpenAI Responses API payload.…, Resolve Anthropic reasoning/thinking config to an OpenAI Responses effort.…, Convert Anthropic tool format → OpenAI Responses API tool format. Responses API…, Convert Anthropic message → LIST of OpenAI Chat Completions messages. Returns a… (+4 more)

### Community 20 - "handle_messages_request"
Cohesion: 0.15
Nodes (18): JSONResponse, _context_dir(), handle_messages_request(), _max_body_bytes(), passthrough_request(), proxy_handler(), api_route, Request (+10 more)

### Community 21 - "RoutingResult"
Cohesion: 0.08
Nodes (27): BaseModel, RoutingResult, LRURoutingCache, Thread-safe bounded caching for routing results with LRU and TTL variants. This…, Thread-safe bounded LRU cache for RoutingResult keyed by session key. Semantics…, Lookup a cached entry and bump its recency if present., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing). (+19 more)

### Community 22 - "csmart - Claude Smart Local Routing"
Cohesion: 0.08
Nodes (24): 1. Routing Result (`RoutingResult` - pydantic), 2. Gate Result (`GateResult` - pydantic), 3. Final Report (`CsmartReport` - pydantic), Anti-Spaghetti Coding Rules, Arsitektur (Pipeline Pattern), Aturan, Aturan untuk AI Coding Tools (CLAUDE.md ini dibaca sebelum edit), CLI Usage (+16 more)

### Community 23 - "run_local_routing"
Cohesion: 0.17
Nodes (12): _cap_skeleton(), _get_or_scan_ast(), Scan the project once per context_dir (cached). Non-blocking (P-2). Returns…, Cap the AST skeleton sent to Ollama while keeping every file header. Lines…, Run local routing: AST scan (cached) -> Ollama scoring -> gate. Async and non-…, run_local_routing(), A skeleton already under the cap is returned byte-identical., Over budget: every // header is kept, the longest - signatures go first. (+4 more)

### Community 24 - "test_report.py"
Cohesion: 0.14
Nodes (21): aggregate_reports(), Write JSON report to file, creating directory if needed., Aggregated statistics across multiple CsmartReport files., Aggregate multiple report files into a StatsSummary. Skips any path that is…, StatsSummary, write_report(), _make_report(), Hermetic unit tests for report.py (schema, create_report, aggregate). These… (+13 more)

### Community 25 - "dispatcher.py"
Cohesion: 0.23
Nodes (12): middleware, _allow_external(), _consume_token(), _is_loopback(), _origin_loopback(), _rate_limit_per_min(), FastAPI reverse-proxy engine for csmart (absorbs ``router/proxy.py``). Wave 2…, True if ``host`` is a loopback IP (``127.0.0.0/8``, ``::1``, IPv4-mapped). Uses… (+4 more)

### Community 26 - "TASKS.md - hemat-token-router (csmart.py)"
Cohesion: 0.18
Nodes (10): Kontrak bersama (Task 1 deliverable - field names EXACT, jangan diganti), Phase 1: Eksplorasi lingkungan, Phase 2: Desain & ADR, Phase 3: Implementasi, Phase 4: Verifikasi akhir (setelah semua task merge), Tasks, TASKS.md - hemat-token-router (csmart.py), Wave 0-3 — Execution Log (2026-08-27/28) (+2 more)

### Community 27 - "ADR - hemat-token-router (csmart.py)"
Cohesion: 0.22
Nodes (8): ADR-1: Dependency AST - tree-sitter-language-pack (bukan tree-sitter-languages), ADR-2: Modular monolith + pipeline pattern, ADR-3: Confidence gate dengan fallback chain (fail-open default, strict opt-in), ADR-4: Budget cap dengan whole-chunk drop (bukan byte truncation), ADR-5: Report JSON selalu dibuat; --json hanya mengontrol stdout, ADR-6: Dispatch Claude Code CLI via stdin, single-shot, ADR - hemat-token-router (csmart.py), Exit codes (kontrak global)

### Community 28 - "CONTRACTS.md — Inter-track Contracts (frozen)"
Cohesion: 0.25
Nodes (7): 1. `router/safe_path.py` — anti path-traversal (dibuat Wave 0), 2. `router/logger.py` — StructuredLogger (Track D), 3. `router/tool_shadow.py` — exploration tool executor (Track E), 4. `router/dispatcher.py` public API (Wave 2 — proxy engine), 5. `router/cli_dispatch.py` (Wave 2 — CLI subprocess), 6. Ownership & Rules, CONTRACTS.md — Inter-track Contracts (frozen)

### Community 29 - "summarize_exploration"
Cohesion: 0.11
Nodes (18): _extract_message_content(), Pull text out of an ``ollama.chat``-shaped response (or a plain string)., Summarize large non-reader tool output via Ollama; short output passes through.…, Truncate *text* to :data:`SUMMARIZE_THRESHOLD` chars with a note., summarize_exploration(), _truncated(), Short output returns unchanged and never touches ollama.chat., Long output with ollama.chat patched returns the mock summary. (+10 more)

### Community 30 - "test_logs_viewer.py"
Cohesion: 0.27
Nodes (10): DispatchResult, BaseModel, Result of a Claude CLI dispatch invocation. Field names are frozen…, Path, Hermetic tests for the csmart logs viewer (Wave 4 Track B). No network, no…, test_cmd_stats_aggregates_fixture_reports(), test_follow_yields_append(), test_read_log_records_filters_by_event() (+2 more)

### Community 31 - "main_cli"
Cohesion: 0.10
Nodes (22): cmd_start(), cmd_status(), main_cli(), Check health of Ollama and upstream gateway., Start the local reverse proxy server., Entry point. Original CLI mode: direct dispatch to Claude Code with pre-routed…, check_ollama_health(), check_upstream_health() (+14 more)

### Community 32 - "Development Environment"
Cohesion: 0.29
Nodes (6): Development Environment, DRIP — Read Layer, Multi-Agent SDLC Rules, Quick Start, RTK — Command Layer, Verify the Tooling

### Community 33 - "verify.sh"
Cohesion: 0.67
Nodes (6): cmd_all(), cmd_smoke(), cmd_test(), cmd_typecheck(), verify.sh script, usage()

### Community 34 - "_asgi_request"
Cohesion: 0.29
Nodes (7): _asgi_request(), Request, Convert an httpx.Request into a Starlette Request (scope + receive). Used for…, P-5: read_full_body catches the chunked/no-content-length oversized path., S-1: _build_upstream_headers forwards only allowlisted headers., test_read_full_body_rejects_oversized(), test_upstream_headers_whitelist()

### Community 35 - "forward_streaming_request"
Cohesion: 0.19
Nodes (16): extract_last_user_prompt(), _forward_streaming_ollama(), forward_streaming_request(), Any, AsyncClient, Response, Forward a streaming request to upstream and stream the SSE response back., Forward a request for ``OLLAMA_MODEL`` to local Ollama, streaming SSE back. No… (+8 more)

### Community 36 - "_truncate_routing_prompt"
Cohesion: 0.33
Nodes (6): Keep the TAIL of a routing prompt so cold prefill stays small (P-2). The…, _truncate_routing_prompt(), Long prompts are cut to the TAIL (the task statement lives at the end)., A short prompt is returned unchanged., test_truncate_routing_prompt_keeps_tail(), test_truncate_routing_prompt_short_unchanged()

### Community 37 - "test_csmart_proxy.py"
Cohesion: 0.05
Nodes (57): Unmask markers on the client-bound path without splitting them at chunk…, StreamingRedactor, parametrize, _hermetic(), _log_text(), _mask_id_for(), mock_upstream(), _post() (+49 more)

### Community 38 - "_clamp_max_tokens"
Cohesion: 0.50
Nodes (4): _clamp_max_tokens(), _min_max_tokens(), Floor for ``max_tokens`` (mirrors ark Smart Gate). Env-overridable., Force ``body["max_tokens"]`` up to the floor, in place. Issue #1 fix: below the…

### Community 39 - "GateResult"
Cohesion: 0.20
Nodes (11): GateResult, BaseModel, Result of gate application after confidence and budget filtering., Read every JSONL record written by a StructuredLogger into ``tmp_path``., A dry-run dispatch must emit exactly one CLI_DISPATCH record (no error)., A missing gateway token must yield exit_code=1 + error in the log record., cmd_start must emit SERVER_START before uvicorn and SERVER_STOP after it., _read_records() (+3 more)

### Community 45 - "Any"
Cohesion: 0.15
Nodes (17): _canonicalize_path(), check_security_guardrails(), _format_event(), _iter_sse_events(), _mask_dict(), _mock_anthropic_stream(), _parse_sse_data(), ProxyStreamer (+9 more)

### Community 46 - "_iter_sse_events"
Cohesion: 0.32
Nodes (7): _iter_sse_events(), _parse_sse_data(), Any, Response, SSE (Server-Sent Events) line parsing for the csmart proxy (N-3). Pure parsing:…, Join ``data:`` lines and JSON-decode them into a payload dict., Parse an httpx streaming response into ``(event_name, payload)`` tuples.

### Community 47 - "handle_messages"
Cohesion: 0.11
Nodes (20): api_route, align_prefix_3_region(), clean_openai_model_name(), _convert_anthropic_tool_to_openai(), detect_openai_endpoint_type(), _extract_system_text(), handle_messages(), _mock_anthropic_json() (+12 more)

### Community 48 - "SecretVault"
Cohesion: 0.22
Nodes (7): Shannon entropy in bits per character (base 2)., Two-tier masking + bidirectional restore. At-rest (default): real secrets live…, Two-tier masking: high-precision regex, then selective entropy pass., Restore secrets on the client-bound path ONLY (never sent upstream)., Conservative heuristic so legit code (hashes, paths, UUIDs) is not masked., SecretVault, _shannon_entropy()

### Community 49 - "csmart_proxy.py"
Cohesion: 0.13
Nodes (22): Connection, _b64url_key(), get_ccr_payload(), get_db(), init_db(), keepalive_worker(), lifespan(), _load_gateway_env() (+14 more)

### Community 50 - "logger.py"
Cohesion: 0.16
Nodes (10): dispatch_claude(), CLI subprocess dispatch for csmart (moved from ``router/dispatcher.py``). Wave…, Read the full content of a file (utf-8)., Dispatch a Claude CLI request with pre-loaded file context. Args: files: List…, read_file_content(), hook_test_helper(), Budget-aware gate that filters candidate files based on confidence and token…, Test helper to verify graphify post-commit hook rebuilds the graph. (+2 more)

### Community 51 - "report.py"
Cohesion: 0.22
Nodes (12): DispatchResult, create_report(), CsmartReport, ExecutionMetrics, GatewayConfig, BaseModel, RoutingResult, JSON report schema for csmart execution. Full structured report that persists… (+4 more)

### Community 52 - "sanitize_payload"
Cohesion: 0.10
Nodes (21): _extract_last_text(), is_anthropic_native_model(), is_openai_model(), _mask_text_block(), Strip ANSI escapes and head-tail truncate logs > 2KB., Sanitize + mask a text block (dict with 'text' / string)., In-place: sanitize + mask system and message content, block tool_use.input., Pick a model for this request. Pinned per session (cache stability). (+13 more)

### Community 53 - "CSmartParser"
Cohesion: 0.38
Nodes (4): CSmartParser, ArgumentParser that routes ``start``/``status`` to subparsers while letting any…, Return the first positional token in ``argv``, skipping flags and the value…, Namespace

### Community 54 - "test_csmart_proxy_openai.py"
Cohesion: 0.09
Nodes (21): Hermetic tests for OpenAI-native protocol adapter in csmart_proxy.py. Runs…, Test basic Anthropic -> OpenAI Chat Completions transformation., Test tool format conversion from Anthropic -> OpenAI., Test transformation handles Anthropic block format content., Test endpoint type detection based on model name., DeepSeek's real API ids aren't served by OpenCode Go — they must map to…, Every model id in docs/endpoints-opencode.md must route to the endpoint its row…, Anthropic reasoning/thinking config -> Responses API effort (max clamped). (+13 more)

### Community 56 - "_post_messages"
Cohesion: 0.13
Nodes (18): _post_messages(), A single content-block SSE fragment (no message envelope)., The real pipeline logs every source event once, in order, one trace_id.…, A full round: message envelope + one tool_use block., POST /v1/messages to the ASGI app and return the response., QG-03: an exploration tool_use is held + resolved locally, not forwarded., QG-04: Edit/Write tool_use is forwarded immediately, never shadowed., Read every JSONL record written to a StructuredLogger in ``tmp_path``. (+10 more)

### Community 57 - "test_adopt_gaps.py"
Cohesion: 0.08
Nodes (27): Event, fixture, MonkeyPatch, Path, _collect_chat_sse(), _collect_responses_sse(), _hermetic(), Any (+19 more)

### Community 58 - "_import_candidates"
Cohesion: 0.33
Nodes (6): _import_candidates(), _module_candidates(), Map a dotted module name to absolute candidate paths (may not exist). ``mod``…, Split a ``from ... import <names>`` clause into module names. Each comma-…, Collect local module paths imported at the top level of *source*. Absolute…, _split_import_names()

### Community 59 - "_read_records"
Cohesion: 0.22
Nodes (9): Short output -> decision passthrough_short, model is None., Reader tool with long output -> decision passthrough_reader, model is None., Successful ollama summarize -> decision summarize with resolved model., ollama.chat raising -> decision fallback_truncated, model resolved., _read_records(), test_summarize_logs_fallback_truncated(), test_summarize_logs_ollama_summarize(), test_summarize_logs_reader_passthrough() (+1 more)

### Community 60 - "transform_openai_chat_to_anthropic_json"
Cohesion: 0.33
Nodes (6): Transform OpenAI Responses API JSON response → Anthropic Messages JSON…, Transform OpenAI Chat Completions JSON response → Anthropic Messages JSON…, Parse JSON string, fall back to {} on failure., _safe_json_loads(), transform_openai_chat_to_anthropic_json(), transform_openai_responses_to_anthropic_json()

### Community 62 - "load_report"
Cohesion: 0.25
Nodes (8): load_report(), Load a CsmartReport from a JSON file. FileNotFoundError and…, load_report lets JSONDecodeError propagate (aggregate handles it)., load_report lets FileNotFoundError propagate (aggregate handles it)., write_report then load_report returns an identical report., test_load_report_propagates_garbage_json(), test_load_report_propagates_missing_file(), test_write_load_roundtrip()

### Community 63 - "test_reader_long_passthrough_no_ollama"
Cohesion: 0.29
Nodes (7): parametrize, Reader tool output over the threshold passes through; ollama never runs., Reader tool output over MAX_OUTPUT_CHARS is bounded, never summarized., Short output (<= threshold) passes through unchanged for every tool., test_reader_long_passthrough_no_ollama(), test_reader_over_max_still_bounded(), test_short_unchanged_any_tool()

### Community 64 - "run.sh"
Cohesion: 0.29
Nodes (5): ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, CLAUDE_CODE_SUBPROCESS_ENV_SCRUB, run.sh script, UPSTREAM_API_KEY

### Community 65 - "clamp_max_tokens"
Cohesion: 0.50
Nodes (4): clamp_max_tokens(), _model_token_limits(), Resolve (floor, ceil) for a model name. Falls back to global default., Clamp client max_tokens to [floor, ceil]. Emits a structured JSON log…

### Community 66 - "_build_upstream_headers"
Cohesion: 0.40
Nodes (5): _build_upstream_headers(), _header_allowlist(), Request, HTTP header helpers for the csmart reverse proxy (S-1 header whitelist). Pure…, Copy only allowlisted client headers upstream (S-1 header whitelist).…

### Community 67 - "csmart-lite Comparison — Gap Dua Arah (fork partner)"
Cohesion: 0.22
Nodes (8): 1. Kesimpulan, 2. Gap di kita (csmart-lite sudah punya) — 10, 3. Gap di csmart-lite (kita sudah punya) — 5, 4. Gap shared (dua-duanya masih bolong) — 10, 5. Tool calling — fokus utama, 6. Action items, 7. Referensi, csmart-lite Comparison — Gap Dua Arah (fork partner)

### Community 68 - "Leak Vectors — Claude Code & csmart"
Cohesion: 0.25
Nodes (7): 1. Peta per tool call Claude Code, 2. Vektor dari riset internet, 3. Cakupan penutup per layer, 4. Prioritas usulan, 5. Yang TIDAK bisa ditutup proxy csmart, Leak Vectors — Claude Code & csmart, Tujuan

### Community 69 - "csmart Pipeline — Diagram & Checklist"
Cohesion: 0.25
Nodes (7): 1. Pipeline Overview (mermaid), 2. Stage-by-Stage Checklist (proxy path), 3. Pipeline Gaps — Priority (X marks the spot), 4. CLI Mode Pipeline (router/* — `csmart` CLI), 5. SSE Event Sequence (Issue #4 — evidence), 6. Cross-reference: issue & doc, csmart Pipeline — Diagram & Checklist

### Community 70 - "init-firewall.sh"
Cohesion: 0.83
Nodes (3): setup_iptables(), setup_nft(), init-firewall.sh script

### Community 74 - "Firewall (egress DENY-BY-DEFAULT)"
Cohesion: 0.33
Nodes (5): Firewall (egress DENY-BY-DEFAULT), Langkah setelah `Reopen in Container`, Sandbox devcontainer — hemat-token-router, UX attach, Verify

### Community 75 - "logs_viewer.py"
Cohesion: 0.12
Nodes (24): cmd_logs(), cmd_stats(), _count_events(), _file_eof_offsets(), follow_log(), _format_stats_table(), _parse_line(), Read-only viewer for csmart JSONL audit logs (no new third-party deps).… (+16 more)

### Community 77 - "_post"
Cohesion: 0.18
Nodes (16): AsyncClient, asyncio, _mock_upstream(), _post(), Make a POST request to /v1/messages with proper headers., End-to-end test: Anthropic request -> OpenAI transformation -> response back to…, Test that existing Anthropic flow still works unchanged., minimax/qwen3 are Anthropic-native on OpenCode Go /messages: the client model… (+8 more)

### Community 78 - "_collect_sse"
Cohesion: 0.17
Nodes (12): _collect_sse(), Consume the async transform generator synchronously., Real Responses API sends delta as STRING. Regression test for the…, Responses API function_call: output_item.added -> content_block_start tool_use,…, A provider that emits ONLY response.function_call_arguments.done (full args…, A provider that emits ONLY response.output_text.done (final full text) with no…, An upstream error event must surface to the client, not be swallowed into an…, test_responses_sse_transform_forwards_upstream_error() (+4 more)

### Community 80 - "test_empty_tool_input_defensive_error"
Cohesion: 0.33
Nodes (6): A tool_use block that streams NO input_json deltas (input stays {})., A full round: message envelope + one tool_use block with empty input., Issue #1: a tool_use with no streamed args yields an actionable error…, _sse_tool_use_empty_input(), _sse_tool_use_empty_round(), test_empty_tool_input_defensive_error()

### Community 85 - "_hermetic"
Cohesion: 0.40
Nodes (5): cwd_tmp(), _hermetic(), fixture, Clear caches + patch routing to hermetic fixtures for every test., chdir to tmp_path so inject's base '.' == tmp_path; restore afterwards.

### Community 86 - "Response"
Cohesion: 0.32
Nodes (8): Request, Response, Build a simple MockTransport handler that returns complete text SSE., Build a MockTransport handler that returns streaming tool call., MockTransport handler that rejects with an HTTP error., _reject_upstream(), _simple_upstream(), _tool_use_upstream()

### Community 87 - "Any"
Cohesion: 0.40
Nodes (5): Any, Build SSE response body from a list of events., Run an async coroutine from sync., _run(), _sse_body()

### Community 88 - "capture_logger"
Cohesion: 0.40
Nodes (5): capture_logger(), fixture, Swap the module's logger for a hermetic one rooted at tmp_path., Build a small project tree: src/a.py, src/pkg/b.py, readme.txt., sample_tree()

## Knowledge Gaps
- **182 isolated node(s):** `run.sh script`, `UPSTREAM_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` (+177 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StructuredLogger` connect `StructuredLogger` to `test_tool_shadow.py`, `test_proxy_server.py`, `test_ast_extractor.py`, `test_cli.py`, `test_proxy_inject.py`, `test_ollama_scorer.py`, `apply_gate`, `TTLRoutingCache`, `logger.py`, `_post_messages`, `capture_logger`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `RoutingResult` connect `RoutingResult` to `test_ollama_scorer.py`, `apply_gate`, `TTLRoutingCache`, `test_report.py`, `test_logs_viewer.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `main_cli()` connect `main_cli` to `GateResult`, `test_cli.py`, `test_ast_extractor.py`, `resolve_under_base`, `logs_viewer.py`, `apply_gate`, `test_ollama_scorer.py`, `logger.py`, `report.py`, `test_report.py`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 13 inferred relationships involving `StructuredLogger` (e.g. with `test_scan_counts_only_supported_extensions()` and `test_scan_counts_parse_failure()`) actually correct?**
  _`StructuredLogger` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `RoutingResult` (e.g. with `LRURoutingCache` and `TTLRoutingCache`) actually correct?**
  _`RoutingResult` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `run.sh script`, `UPSTREAM_API_KEY`, `ANTHROPIC_BASE_URL` to the rest of the system?**
  _182 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_proxy_server.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07676767676767676 - nodes in this community are weakly interconnected._