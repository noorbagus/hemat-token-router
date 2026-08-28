# Graph Report - hemat-token-router  (2026-08-28)

## Corpus Check
- 40 files · ~40,800 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 817 nodes · 1435 edges · 45 communities (43 shown, 2 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 32 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1dd92be0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_tool_shadow.py
- resolve_under_base
- test_proxy_server.py
- SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing
- StructuredLogger
- test_report.py
- CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)
- test_ast_extractor.py
- test_cli.py
- csmart.py
- logs_viewer.py
- test_ollama_scorer.py
- RoutingResult
- TTLRoutingCache
- Any
- dispatcher.py
- [2.0.0] — 2026-08-28
- GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)
- A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct
- LRURoutingCache
- handle_messages_request
- test_proxy.py
- csmart - Claude Smart Local Routing
- run_local_routing
- aggregate_reports
- _security_middleware
- TASKS.md - hemat-token-router (csmart.py)
- ADR - hemat-token-router (csmart.py)
- CONTRACTS.md — Inter-track Contracts (frozen)
- _cap_skeleton
- load_report
- CSmartParser
- Development Environment
- verify.sh
- _asgi_request
- _import_candidates
- _truncate_routing_prompt
- test_non_exploration_tool_use_passed_through
- _hermetic
- _clamp_max_tokens
- _sse_tool_use_empty_round
- drip-refresh.sh
- csmart

## God Nodes (most connected - your core abstractions)
1. `RoutingResult` - 45 edges
2. `_run()` - 29 edges
3. `_run()` - 26 edges
4. `mock_upstream()` - 24 edges
5. `main_cli()` - 22 edges
6. `resolve_under_base()` - 22 edges
7. `execute_local_tool()` - 21 edges
8. `build_parser()` - 20 edges
9. `StructuredLogger` - 20 edges
10. `_sse_text()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `main_cli()` --uses--> `PathTraversalError`  [INFERRED]
  csmart.py → router/safe_path.py
- `test_triage_model_env_override()` --calls--> `triage_model()`  [EXTRACTED]
  tests/test_ollama_scorer.py → router/ollama_scorer.py
- `_hermetic()` --uses--> `RoutingResult`  [INFERRED]
  tests/test_proxy.py → router/ollama_scorer.py
- `_hermetic()` --uses--> `RoutingResult`  [INFERRED]
  tests/test_proxy_server.py → router/ollama_scorer.py
- `test_write_load_roundtrip()` --uses--> `CsmartReport`  [INFERRED]
  tests/test_report.py → router/report.py

## Import Cycles
- None detected.

## Communities (45 total, 2 thin omitted)

### Community 0 - "test_tool_shadow.py"
Cohesion: 0.05
Nodes (75): parametrize, _bounded(), execute_local_tool(), _execute_local_tool_sync(), _extract_message_content(), _get_path(), _normalize_tool_name(), Path (+67 more)

### Community 1 - "resolve_under_base"
Cohesion: 0.07
Nodes (54): _expand_selected_with_imports(), inject_context_to_messages(), Inject pre-loaded file context into the last user message. Path-safety (F-09):…, Total on-disk bytes of *relpaths* under *base_dir*; missing files count 0.…, Append top-level-imported local modules to the triage-selected files. FIX #3…, _sum_selected_bytes(), is_within(), PathTraversalError (+46 more)

### Community 2 - "test_proxy_server.py"
Cohesion: 0.09
Nodes (52): mock_upstream(), _post_messages(), Hermetic server tests for the csmart proxy engine (``router.dispatcher``).…, A full round with ``count`` consecutive GrepTool tool_use blocks., Install a MockTransport upstream; returns a list recording each request.…, POST /v1/messages to the ASGI app and return the response., QG-04: text content_block_delta events reach the client immediately., Run a coroutine to completion with a fresh event loop. (+44 more)

### Community 3 - "SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing"
Cohesion: 0.04
Nodes (46): 10. Observability & Metrics, 11. Rencana Implementasi (Phase-by-Phase), 12. Rencana Testing & Verification Matrix, 13.1 Dev Environment: RTK & DRIP Interference Handling (READ/WRITE), 13. Deployment & Standard Operating Environment (SOP), 14. Risiko & Mitigasi, 15. Open Decisions (item yang perlu dikonfirmasi), 16. Referensi (+38 more)

### Community 4 - "StructuredLogger"
Cohesion: 0.08
Nodes (26): Path, StructuredLogger for csmart — non-blocking, thread-safe JSONL audit logging.…, Serialize one record as a JSONL line. False if the lock could not be acquired., Coerce non-JSON-serializable values to str so the writer never chokes., Non-blocking structured logger backed by a bounded queue + one daemon writer…, Enqueue a record asynchronously. Never blocks the caller., Store the per-turn trace id stamped onto subsequent records., Mask a sensitive value. Always returns the fixed placeholder. (+18 more)

### Community 5 - "test_report.py"
Cohesion: 0.11
Nodes (32): DispatchResult, BaseModel, CLI subprocess dispatch for csmart (moved from ``router/dispatcher.py``). Wave…, Result of a Claude CLI dispatch invocation. Field names are frozen…, GateResult, BaseModel, Budget-aware gate that filters candidate files based on confidence and token…, Result of gate application after confidence and budget filtering. (+24 more)

### Community 6 - "CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)"
Cohesion: 0.06
Nodes (32): 1.1 Peran komponen, 1.2 Topologi makro, 2.1 Pydantic models / DTO (fakta dari kode), 2.2 Class & function signature utama, 2.3 Kontrak antar-stage (alur data), 3.1 Flow `POST /v1/messages` saat ini, 3.2 Detail transformasi payload per stage, 4.1 Status implementasi (fakta) (+24 more)

### Community 7 - "test_ast_extractor.py"
Cohesion: 0.11
Nodes (27): Node, extract_ast_skeleton(), _get_signature_first_line(), AST-based code skeleton extraction using tree-sitter. Extracts…, Scan a project directory recursively for supported source files, extracting AST…, Extract the first line of a node's signature from source bytes., Recursively traverse AST, collect signatures of target node types., Extract AST skeleton (function/class signatures) from a source file. Args:… (+19 more)

### Community 8 - "test_cli.py"
Cohesion: 0.11
Nodes (27): ArgumentParser, build_parser(), Build the CLI argument parser. Shared flags live on a single parent parser…, Hermetic unit tests for csmart CLI parser + main_cli routing (Track A). These…, `main_cli(["start"])` routes to cmd_start with default host/port., Ollama-chosen paths outside context_dir are skipped, never read/dispatched.…, `main_cli(["logs", ...])` routes to cmd_logs with parsed flags., Shared flags must be inherited by subparsers too. (+19 more)

### Community 9 - "csmart.py"
Cohesion: 0.11
Nodes (24): cmd_start(), cmd_status(), main_cli(), Check health of Ollama and upstream gateway., Start the local reverse proxy server., Entry point. Original CLI mode: direct dispatch to Claude Code with pre-routed…, dispatch_claude(), Read the full content of a file (utf-8). (+16 more)

### Community 10 - "logs_viewer.py"
Cohesion: 0.12
Nodes (24): cmd_logs(), cmd_stats(), _count_events(), _file_eof_offsets(), follow_log(), _format_stats_table(), _parse_line(), Read-only viewer for csmart JSONL audit logs (no new third-party deps).… (+16 more)

### Community 11 - "test_ollama_scorer.py"
Cohesion: 0.12
Nodes (22): _keyword_heuristic(), Robust fallback heuristic: weighted keyword matching per file from the…, Identify target files to modify based on user prompt using Ollama JSON output.…, route_target_files(), Hermetic tests for router/ollama_scorer.py (S-6 model env, T-4 heuristic).…, Short reasoning stays intact (no over-truncation)., T-4: a keyword hitting the real file's path must outrank the same keyword…, Regression: signature-only hits must attribute to the real file, never… (+14 more)

### Community 12 - "RoutingResult"
Cohesion: 0.16
Nodes (21): apply_gate(), Apply confidence threshold and token budget gate to routing result. Rules: 1.…, BaseModel, RoutingResult, Unit tests for gate.py budget-aware filtering., Test that confidence exactly equal to threshold passes., Test fallback when overall confidence below but some files pass? Actually all…, Test gate when routing returns no files. (+13 more)

### Community 13 - "TTLRoutingCache"
Cohesion: 0.10
Nodes (14): Return current effective TTL from environment or default., Lookup a cached entry, evicting if stale (older than TTL)., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing)., Thread-safe bounded TTL cache for RoutingResult keyed by context directory.…, Read TTL from environment variable CSMART_ROUTING_TTL if present., TTLRoutingCache (+6 more)

### Community 14 - "Any"
Cohesion: 0.17
Nodes (12): Any, _iter_sse_events(), _parse_sse_data(), Reassemble ``partial_json`` fragments into a tool input dict., Append the assistant tool_use + user tool_result turns., Join ``data:`` lines and JSON-decode them into a payload dict., Parse an httpx streaming response into ``(event_name, payload)`` tuples., Drives the outbound SSE stream with exploration tool-use shadowing. For each… (+4 more)

### Community 15 - "dispatcher.py"
Cohesion: 0.16
Nodes (18): AsyncClient, Exception, BodyTooLargeError, _build_upstream_headers(), _header_allowlist(), _max_body_bytes(), passthrough_request(), FastAPI reverse-proxy engine for csmart (absorbs ``router/proxy.py``). Wave 2… (+10 more)

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
Cohesion: 0.12
Nodes (11): LRURoutingCache, Thread-safe bounded caching for routing results with LRU and TTL variants. This…, Thread-safe bounded LRU cache for RoutingResult keyed by session key. Semantics…, Lookup a cached entry and bump its recency if present., Insert/replace an entry, evicting oldest if over capacity., Return current number of cached entries (for testing)., Clear all cached entries (for testing)., Get on an existing entry moves it to the end of the LRU order. (+3 more)

### Community 20 - "handle_messages_request"
Cohesion: 0.18
Nodes (15): api_route, Response, _context_dir(), extract_last_user_prompt(), forward_streaming_request(), handle_messages_request(), proxy_handler(), Request (+7 more)

### Community 21 - "test_proxy.py"
Cohesion: 0.17
Nodes (14): _hermetic(), fixture, Hermetic tests for the csmart reverse-proxy engine (``router.dispatcher``). No…, /v1/messages is intercepted and the mocked SSE upstream is streamed back., Run a coroutine to completion with a fresh event loop., Clear proxy caches + patch routing so no test touches Ollama/AST., CORS preflight OPTIONS allows a loopback Origin and echoes it., CORS preflight with a non-loopback Origin gets no allow-origin header. (+6 more)

### Community 22 - "csmart - Claude Smart Local Routing"
Cohesion: 0.14
Nodes (13): 1. Routing Result (`RoutingResult` - pydantic), 2. Gate Result (`GateResult` - pydantic), 3. Final Report (`CsmartReport` - pydantic), Arsitektur (Pipeline Pattern), Aturan untuk AI Coding Tools (CLAUDE.md ini dibaca sebelum edit), CLI Usage, Contoh Output Verified, csmart - Claude Smart Local Routing (+5 more)

### Community 23 - "run_local_routing"
Cohesion: 0.17
Nodes (12): _get_or_scan_ast(), Scan the project once per context_dir (cached). Non-blocking (P-2)., Run local routing: AST scan (cached) -> Ollama scoring -> gate. Async and non-…, run_local_routing(), run_local_routing hands Ollama a skeleton capped to the env budget., P-0: session-less requests with the SAME prompt route via Ollama once., FIX #2: the session-less TTL cache key includes the prompt, so a different…, P-0: TTL=0 disables reuse — every session-less request re-routes. (+4 more)

### Community 24 - "aggregate_reports"
Cohesion: 0.18
Nodes (12): aggregate_reports(), Aggregated statistics across multiple CsmartReport files., Aggregate multiple report files into a StatsSummary. Skips any path that is…, StatsSummary, Missing paths and garbage JSON files are skipped without raising., Empty input produces an empty summary with no exception., IsADirectoryError in a report path is skipped, not fatal., Aggregation sums injected bytes, tokens saved, and groups by status. (+4 more)

### Community 25 - "_security_middleware"
Cohesion: 0.20
Nodes (11): middleware, _allow_external(), _consume_token(), _is_loopback(), _origin_loopback(), _rate_limit_per_min(), True if ``host`` is a loopback IP (``127.0.0.0/8``, ``::1``, IPv4-mapped). Uses…, True if the ``Origin`` header's host is a loopback address. Used to gate CORS:… (+3 more)

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

### Community 30 - "load_report"
Cohesion: 0.25
Nodes (8): load_report(), Load a CsmartReport from a JSON file. FileNotFoundError and…, load_report lets JSONDecodeError propagate (aggregate handles it)., load_report lets FileNotFoundError propagate (aggregate handles it)., write_report then load_report returns an identical report., test_load_report_propagates_garbage_json(), test_load_report_propagates_missing_file(), test_write_load_roundtrip()

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

### Community 37 - "test_non_exploration_tool_use_passed_through"
Cohesion: 0.33
Nodes (6): A full round: message envelope + one tool_use block., QG-04: Edit/Write tool_use is forwarded immediately, never shadowed., A single content-block SSE fragment (no message envelope)., _sse_tool_use(), _sse_tool_use_round(), test_non_exploration_tool_use_passed_through()

### Community 38 - "_hermetic"
Cohesion: 0.40
Nodes (5): cwd_tmp(), _hermetic(), fixture, Clear caches + patch routing to hermetic fixtures for every test., chdir to tmp_path so inject's base '.' == tmp_path; restore afterwards.

### Community 39 - "_clamp_max_tokens"
Cohesion: 0.50
Nodes (4): _clamp_max_tokens(), _min_max_tokens(), Floor for ``max_tokens`` (mirrors ark Smart Gate). Env-overridable., Force ``body["max_tokens"]`` up to the floor, in place. Issue #1 fix: below the…

### Community 40 - "_sse_tool_use_empty_round"
Cohesion: 0.50
Nodes (4): A tool_use block that streams NO input_json deltas (input stays {})., A full round: message envelope + one tool_use block with empty input., _sse_tool_use_empty_input(), _sse_tool_use_empty_round()

## Knowledge Gaps
- **142 isolated node(s):** `csmart`, `drip-refresh.sh script`, `A/B Test: request-count vs output correctness (2026-08-28)`, `Performance (2026-08-28, issue #2 P0-P4)`, `Verified (live, 2026-08-28)` (+137 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RoutingResult` connect `RoutingResult` to `test_proxy_server.py`, `test_report.py`, `_hermetic`, `test_cli.py`, `test_ollama_scorer.py`, `TTLRoutingCache`, `dispatcher.py`, `LRURoutingCache`, `test_proxy.py`, `run_local_routing`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `summarize_exploration()` connect `test_tool_shadow.py` to `dispatcher.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `RoutingResult` (e.g. with `apply_gate()` and `create_report()`) actually correct?**
  _`RoutingResult` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `csmart`, `drip-refresh.sh script`, `A/B Test: request-count vs output correctness (2026-08-28)` to the rest of the system?**
  _142 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_tool_shadow.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05331510594668489 - nodes in this community are weakly interconnected._
- **Should `resolve_under_base` be split into smaller, more focused modules?**
  _Cohesion score 0.07205513784461152 - nodes in this community are weakly interconnected._
- **Should `test_proxy_server.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08925979680696662 - nodes in this community are weakly interconnected._