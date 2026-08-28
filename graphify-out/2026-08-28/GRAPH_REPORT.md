# Graph Report - hemat-token-router  (2026-08-28)

## Corpus Check
- 40 files · ~41,258 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 821 nodes · 1436 edges · 49 communities (42 shown, 7 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9d0e66c6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_tool_shadow.py
- resolve_under_base
- mock_upstream
- SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing
- StructuredLogger
- test_logs_viewer.py
- CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)
- test_ast_extractor.py
- test_cli.py
- csmart.py
- logs_viewer.py
- test_ollama_scorer.py
- apply_gate
- RoutingResult
- Any
- _read_body_bounded
- [2.0.0] — 2026-08-28
- GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)
- A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct
- LRURoutingCache
- handle_messages_request
- _post_messages
- csmart - Claude Smart Local Routing
- _run
- test_report.py
- dispatcher.py
- TASKS.md - hemat-token-router (csmart.py)
- ADR - hemat-token-router (csmart.py)
- CONTRACTS.md — Inter-track Contracts (frozen)
- _cap_skeleton
- test_shadow_rounds_bounded_at_three
- CSmartParser
- Development Environment
- verify.sh
- _asgi_request
- _import_candidates
- _truncate_routing_prompt
- test_proxy_server.py
- _clamp_max_tokens
- test_max_tokens_clamped_to_floor
- test_empty_tool_input_defensive_error
- drip-refresh.sh
- csmart
- test_main_cli_start_calls_cmd_start
- test_main_cli_logs_calls_cmd_logs
- test_main_cli_status_returns_without_blocking
- BaseModel

## God Nodes (most connected - your core abstractions)
1. `RoutingResult` - 43 edges
2. `_run()` - 29 edges
3. `_run()` - 26 edges
4. `mock_upstream()` - 24 edges
5. `resolve_under_base()` - 22 edges
6. `main_cli()` - 22 edges
7. `execute_local_tool()` - 21 edges
8. `StructuredLogger` - 20 edges
9. `_sse_text()` - 20 edges
10. `build_parser()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `main_cli()` --uses--> `PathTraversalError`  [INFERRED]
  csmart.py → router/safe_path.py
- `_hermetic()` --uses--> `LRURoutingCache`  [INFERRED]
  tests/test_proxy_server.py → router/routing_cache.py
- `_make_report()` --uses--> `CsmartReport`  [INFERRED]
  tests/test_report.py → router/report.py
- `test_write_load_roundtrip()` --uses--> `CsmartReport`  [INFERRED]
  tests/test_report.py → router/report.py
- `_make_report()` --calls--> `GateResult`  [EXTRACTED]
  tests/test_report.py → router/gate.py

## Import Cycles
- None detected.

## Communities (49 total, 7 thin omitted)

### Community 0 - "test_tool_shadow.py"
Cohesion: 0.05
Nodes (75): parametrize, _bounded(), execute_local_tool(), _execute_local_tool_sync(), _extract_message_content(), _get_path(), _normalize_tool_name(), Path (+67 more)

### Community 1 - "resolve_under_base"
Cohesion: 0.07
Nodes (54): _expand_selected_with_imports(), inject_context_to_messages(), Inject pre-loaded file context into the last user message. Path-safety (F-09):…, Total on-disk bytes of *relpaths* under *base_dir*; missing files count 0.…, Append top-level-imported local modules to the triage-selected files. FIX #3…, _sum_selected_bytes(), is_within(), PathTraversalError (+46 more)

### Community 2 - "mock_upstream"
Cohesion: 0.10
Nodes (26): cwd_tmp(), mock_upstream(), fixture, Install a MockTransport upstream; returns a list recording each request.…, S-2: a non-loopback peer is rejected before any routing/upstream call., S-2: CSMART_ALLOW_EXTERNAL=1 lets a non-loopback peer through., S-2: 4th request inside the same minute returns 429 + Retry-After. Uses a non-…, P-5: an oversized POST body is rejected with 413 before any upstream call. (+18 more)

### Community 3 - "SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing"
Cohesion: 0.04
Nodes (46): 10. Observability & Metrics, 11. Rencana Implementasi (Phase-by-Phase), 12. Rencana Testing & Verification Matrix, 13.1 Dev Environment: RTK & DRIP Interference Handling (READ/WRITE), 13. Deployment & Standard Operating Environment (SOP), 14. Risiko & Mitigasi, 15. Open Decisions (item yang perlu dikonfirmasi), 16. Referensi (+38 more)

### Community 4 - "StructuredLogger"
Cohesion: 0.08
Nodes (26): Path, StructuredLogger for csmart — non-blocking, thread-safe JSONL audit logging.…, Serialize one record as a JSONL line. False if the lock could not be acquired., Coerce non-JSON-serializable values to str so the writer never chokes., Non-blocking structured logger backed by a bounded queue + one daemon writer…, Enqueue a record asynchronously. Never blocks the caller., Store the per-turn trace id stamped onto subsequent records., Mask a sensitive value. Always returns the fixed placeholder. (+18 more)

### Community 5 - "test_logs_viewer.py"
Cohesion: 0.10
Nodes (33): BaseModel, dispatch_claude(), DispatchResult, BaseModel, CLI subprocess dispatch for csmart (moved from ``router/dispatcher.py``). Wave…, Result of a Claude CLI dispatch invocation. Field names are frozen…, Read the full content of a file (utf-8)., Dispatch a Claude CLI request with pre-loaded file context. Args: files: List… (+25 more)

### Community 6 - "CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)"
Cohesion: 0.06
Nodes (32): 1.1 Peran komponen, 1.2 Topologi makro, 2.1 Pydantic models / DTO (fakta dari kode), 2.2 Class & function signature utama, 2.3 Kontrak antar-stage (alur data), 3.1 Flow `POST /v1/messages` saat ini, 3.2 Detail transformasi payload per stage, 4.1 Status implementasi (fakta) (+24 more)

### Community 7 - "test_ast_extractor.py"
Cohesion: 0.11
Nodes (27): Node, extract_ast_skeleton(), _get_signature_first_line(), AST-based code skeleton extraction using tree-sitter. Extracts…, Scan a project directory recursively for supported source files, extracting AST…, Extract the first line of a node's signature from source bytes., Recursively traverse AST, collect signatures of target node types., Extract AST skeleton (function/class signatures) from a source file. Args:… (+19 more)

### Community 8 - "test_cli.py"
Cohesion: 0.15
Nodes (21): ArgumentParser, build_parser(), Build the CLI argument parser. Shared flags live on a single parent parser…, Hermetic unit tests for csmart CLI parser + main_cli routing (Track A). These…, Shared flags must be inherited by subparsers too., An unknown token in subcommand position raises SystemExit. Note: a *bare* first…, A bare non-command token is a CLI prompt (not an error)., test_bare_noncommand_token_is_cli_prompt() (+13 more)

### Community 9 - "csmart.py"
Cohesion: 0.12
Nodes (21): cmd_start(), cmd_status(), main_cli(), Check health of Ollama and upstream gateway., Start the local reverse proxy server., Entry point. Original CLI mode: direct dispatch to Claude Code with pre-routed…, check_ollama_health(), check_upstream_health() (+13 more)

### Community 10 - "logs_viewer.py"
Cohesion: 0.13
Nodes (20): cmd_logs(), _file_eof_offsets(), follow_log(), _format_stats_table(), _parse_line(), Read-only viewer for csmart JSONL audit logs (no new third-party deps).…, Record the current byte size of every session log file., Yield the last ``tail`` records (all when ``tail <= 0``), then poll for… (+12 more)

### Community 11 - "test_ollama_scorer.py"
Cohesion: 0.12
Nodes (21): _keyword_heuristic(), Robust fallback heuristic: weighted keyword matching per file from the…, Identify target files to modify based on user prompt using Ollama JSON output.…, route_target_files(), Hermetic tests for router/ollama_scorer.py (S-6 model env, T-4 heuristic).…, Short reasoning stays intact (no over-truncation)., T-4: a keyword hitting the real file's path must outrank the same keyword…, Regression: signature-only hits must attribute to the real file, never… (+13 more)

### Community 12 - "apply_gate"
Cohesion: 0.13
Nodes (20): apply_gate(), Apply confidence threshold and token budget gate to routing result. Rules: 1.…, RoutingResult, Unit tests for gate.py budget-aware filtering., Test that confidence exactly equal to threshold passes., Test fallback when overall confidence below but some files pass? Actually all…, Test gate when routing returns no files., Test gate when all candidates are below confidence threshold. (+12 more)

### Community 13 - "RoutingResult"
Cohesion: 0.07
Nodes (33): BaseModel, RoutingResult, Thread-safe bounded caching for routing results with LRU and TTL variants. This…, Return current effective TTL from environment or default., Lookup a cached entry, evicting if stale (older than TTL)., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing). (+25 more)

### Community 14 - "Any"
Cohesion: 0.17
Nodes (12): Any, _iter_sse_events(), _parse_sse_data(), Reassemble ``partial_json`` fragments into a tool input dict., Append the assistant tool_use + user tool_result turns., Join ``data:`` lines and JSON-decode them into a payload dict., Parse an httpx streaming response into ``(event_name, payload)`` tuples., Drives the outbound SSE stream with exploration tool-use shadowing. For each… (+4 more)

### Community 15 - "_read_body_bounded"
Cohesion: 0.18
Nodes (11): AsyncClient, Exception, BodyTooLargeError, _max_body_bytes(), Raised when the upstream gateway is unreachable after retries., Raised when a request body exceeds the configured byte cap., Read the request body, aborting early once the configured cap is exceeded. Uses…, Send a request to upstream with bounded retry; return (client, resp). The… (+3 more)

### Community 16 - "[2.0.0] — 2026-08-28"
Cohesion: 0.11
Nodes (18): [2.0.0] — 2026-08-28, [2.1.0] — 2026-08-28, A/B Test: request-count vs output correctness (2026-08-28), Added, Added, Changed, Changelog, Fixed (+10 more)

### Community 17 - "GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)"
Cohesion: 0.11
Nodes (17): 1. Ringkasan Eksekutif (Verdict), 2. Gap Matrix per Komponen Target, 3.1 Functional Requirements, 3.2 Non-Functional Requirements, 3. Mapping Requirement Target → Status Baseline, 4.1 Critical — Entrypoint & Runtime Bug (kerjakan paling dulu), 4.2 Feature Baru — Observability & Shadowing (inti v2.0), 4.3 Refactor — Proxy Engine & Ownership (+9 more)

### Community 18 - "A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct"
Cohesion: 0.11
Nodes (17): A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct, Akar masalah (atribusi), Baseline working tree (rusak sebelum uji), Caveat (kejujuran pengukuran), Detail direct S1 (definitif, MAX_ROUNDS=12), Detail direct S2 (gagal), Hasil, Hasil aplikasi (+9 more)

### Community 19 - "LRURoutingCache"
Cohesion: 0.13
Nodes (10): LRURoutingCache, Thread-safe bounded LRU cache for RoutingResult keyed by session key. Semantics…, Lookup a cached entry and bump its recency if present., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing)., Get on an existing entry moves it to the end of the LRU order., LRU cache respects max capacity and evicts least recently used. (+2 more)

### Community 20 - "handle_messages_request"
Cohesion: 0.17
Nodes (18): api_route, Response, _build_upstream_headers(), _context_dir(), forward_streaming_request(), handle_messages_request(), passthrough_request(), proxy_handler() (+10 more)

### Community 21 - "_post_messages"
Cohesion: 0.20
Nodes (10): _post_messages(), POST /v1/messages to the ASGI app and return the response., QG-04: text content_block_delta events reach the client immediately., Issue #1: max_tokens already at/above the floor is left untouched., P-1/QG-02: two requests in one session route via Ollama only once., P-3: upstream connect timeout -> clean SSE error, no hang, bounded retries., test_max_tokens_above_floor_preserved(), test_routing_runs_once_per_session() (+2 more)

### Community 22 - "csmart - Claude Smart Local Routing"
Cohesion: 0.14
Nodes (13): 1. Routing Result (`RoutingResult` - pydantic), 2. Gate Result (`GateResult` - pydantic), 3. Final Report (`CsmartReport` - pydantic), Arsitektur (Pipeline Pattern), Aturan untuk AI Coding Tools (CLAUDE.md ini dibaca sebelum edit), CLI Usage, Contoh Output Verified, csmart - Claude Smart Local Routing (+5 more)

### Community 23 - "_run"
Cohesion: 0.18
Nodes (14): Run local routing: AST scan (cached) -> Ollama scoring -> gate. Async and non-…, run_local_routing(), Run a coroutine to completion with a fresh event loop., P-5 MAJOR: an oversized chunked body aborts early, never full-buffers., run_local_routing hands Ollama a skeleton capped to the env budget., P-0: session-less requests with the SAME prompt route via Ollama once., FIX #2: the session-less TTL cache key includes the prompt, so a different…, P-0: TTL=0 disables reuse — every session-less request re-routes. (+6 more)

### Community 24 - "test_report.py"
Cohesion: 0.11
Nodes (27): aggregate_reports(), load_report(), Aggregated statistics across multiple CsmartReport files., Load a CsmartReport from a JSON file. FileNotFoundError and…, Aggregate multiple report files into a StatsSummary. Skips any path that is…, StatsSummary, _make_report(), Hermetic unit tests for report.py (schema, create_report, aggregate). These… (+19 more)

### Community 25 - "dispatcher.py"
Cohesion: 0.15
Nodes (17): middleware, _allow_external(), _consume_token(), extract_last_user_prompt(), _get_or_scan_ast(), _header_allowlist(), _is_loopback(), _origin_loopback() (+9 more)

### Community 26 - "TASKS.md - hemat-token-router (csmart.py)"
Cohesion: 0.18
Nodes (10): Kontrak bersama (Task 1 deliverable - field names EXACT, jangan diganti), Phase 1: Eksplorasi lingkungan, Phase 2: Desain & ADR, Phase 3: Implementasi, Phase 4: Verifikasi akhir (setelah semua task merge), Tasks, TASKS.md - hemat-token-router (csmart.py), Wave 0-3 — Execution Log (2026-08-27/28) (+2 more)

### Community 27 - "ADR - hemat-token-router (csmart.py)"
Cohesion: 0.22
Nodes (8): ADR-1: Dependency AST - tree-sitter-language-pack (bukan tree-sitter-languages), ADR-2: Modular monolith + pipeline pattern, ADR-3: Confidence gate dengan fallback chain (fail-open default, strict opt-in), ADR-4: Budget cap dengan whole-chunk drop (bukan byte truncation), ADR-5: Report JSON selalu dibuat; --json hanya mengontrol stdout, ADR-6: Dispatch Claude Code CLI via stdin, single-shot, ADR - hemat-token-router (csmart.py), Exit codes (kontrak global)

### Community 28 - "CONTRACTS.md — Inter-track Contracts (frozen)"
Cohesion: 0.25
Nodes (7): 1. `router/safe_path.py` — anti path-traversal (dibuat Wave 0), 2. `router/logger.py` — StructuredLogger (Track D), 3. `router/tool_shadow.py` — exploration tool executor (Track E), 4. `router/dispatcher.py` public API (Wave 2 — proxy engine), 5. `router/cli_dispatch.py` (Wave 2 — CLI subprocess), 6. Ownership & Rules, CONTRACTS.md — Inter-track Contracts (frozen)

### Community 29 - "_cap_skeleton"
Cohesion: 0.25
Nodes (8): _cap_skeleton(), Cap the AST skeleton sent to Ollama while keeping every file header. Lines…, A skeleton already under the cap is returned byte-identical., Over budget: every // header is kept, the longest - signatures go first., Even a path-only skeleton over an absurdly small budget keeps the first N., test_cap_skeleton_path_only_fits_by_trimming_headers(), test_cap_skeleton_preserves_headers_drops_longest_signatures(), test_cap_skeleton_under_budget_unchanged()

### Community 30 - "test_shadow_rounds_bounded_at_three"
Cohesion: 0.50
Nodes (4): A full round with ``count`` consecutive GrepTool tool_use blocks., N-4/OD-3: with 5 exploration tool_use, <= 3 are held, the rest pass through., _sse_n_tool_uses(), test_shadow_rounds_bounded_at_three()

### Community 31 - "CSmartParser"
Cohesion: 0.38
Nodes (4): CSmartParser, ArgumentParser that routes ``start``/``status`` to subparsers while letting any…, Return the first positional token in ``argv``, skipping flags and the value…, Namespace

### Community 32 - "Development Environment"
Cohesion: 0.29
Nodes (6): Development Environment, DRIP — Read Layer, Multi-Agent SDLC Rules, Quick Start, RTK — Command Layer, Verify the Tooling

### Community 33 - "verify.sh"
Cohesion: 0.67
Nodes (6): cmd_all(), cmd_smoke(), cmd_test(), cmd_typecheck(), verify.sh script, usage()

### Community 34 - "_asgi_request"
Cohesion: 0.29
Nodes (7): _asgi_request(), Request, Convert an httpx.Request into a Starlette Request (scope + receive). Used for…, P-5: read_full_body catches the chunked/no-content-length oversized path., S-1: _build_upstream_headers forwards only allowlisted headers., test_read_full_body_rejects_oversized(), test_upstream_headers_whitelist()

### Community 35 - "_import_candidates"
Cohesion: 0.33
Nodes (6): _import_candidates(), _module_candidates(), Map a dotted module name to absolute candidate paths (may not exist). ``mod``…, Split a ``from ... import <names>`` clause into module names. Each comma-…, Collect local module paths imported at the top level of *source*. Absolute…, _split_import_names()

### Community 36 - "_truncate_routing_prompt"
Cohesion: 0.33
Nodes (6): Keep the TAIL of a routing prompt so cold prefill stays small (P-2). The…, _truncate_routing_prompt(), Long prompts are cut to the TAIL (the task statement lives at the end)., A short prompt is returned unchanged., test_truncate_routing_prompt_keeps_tail(), test_truncate_routing_prompt_short_unchanged()

### Community 37 - "test_proxy_server.py"
Cohesion: 0.19
Nodes (13): Hermetic server tests for the csmart proxy engine (``router.dispatcher``).…, A full round: message envelope + one tool_use block., TTL cache reads CSMART_ROUTING_TTL from environment when using default provider., QG-03: an exploration tool_use is held + resolved locally, not forwarded., QG-04: Edit/Write tool_use is forwarded immediately, never shadowed., Issue #1: partial_json that never parses is flagged truncated_input., A single content-block SSE fragment (no message envelope)., _sse_tool_use() (+5 more)

### Community 39 - "test_max_tokens_clamped_to_floor"
Cohesion: 0.33
Nodes (6): _min_max_tokens(), Floor for ``max_tokens`` (mirrors ark Smart Gate). Env-overridable., Issue #1: max_tokens below the floor is raised to the floor upstream., Issue #1: absent max_tokens is defaulted to the floor., test_max_tokens_clamped_to_floor(), test_max_tokens_defaulted_when_missing()

### Community 40 - "test_empty_tool_input_defensive_error"
Cohesion: 0.33
Nodes (6): A tool_use block that streams NO input_json deltas (input stays {})., A full round: message envelope + one tool_use block with empty input., Issue #1: a tool_use with no streamed args yields an actionable error…, _sse_tool_use_empty_input(), _sse_tool_use_empty_round(), test_empty_tool_input_defensive_error()

## Knowledge Gaps
- **142 isolated node(s):** `A/B Test: request-count vs output correctness (2026-08-28)`, `Added`, `Added`, `Changed`, `Fixed` (+137 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RoutingResult` connect `RoutingResult` to `test_logs_viewer.py`, `test_proxy_server.py`, `test_cli.py`, `test_ollama_scorer.py`, `apply_gate`, `LRURoutingCache`, `_post_messages`, `_run`, `test_report.py`, `dispatcher.py`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `summarize_exploration()` connect `test_tool_shadow.py` to `dispatcher.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `RoutingResult` (e.g. with `create_report()` and `CsmartReport`) actually correct?**
  _`RoutingResult` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `A/B Test: request-count vs output correctness (2026-08-28)`, `Added`, `Added` to the rest of the system?**
  _142 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_tool_shadow.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05331510594668489 - nodes in this community are weakly interconnected._
- **Should `resolve_under_base` be split into smaller, more focused modules?**
  _Cohesion score 0.07205513784461152 - nodes in this community are weakly interconnected._
- **Should `mock_upstream` be split into smaller, more focused modules?**
  _Cohesion score 0.10461538461538461 - nodes in this community are weakly interconnected._