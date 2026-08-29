# Graph Report - hemat-token-router  (2026-08-28)

## Corpus Check
- 41 files · ~46,460 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 918 nodes · 1650 edges · 46 communities (40 shown, 6 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c737a679`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_tool_shadow.py
- resolve_under_base
- test_proxy_server.py
- SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing
- StructuredLogger
- dispatcher.py
- CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)
- test_ast_extractor.py
- test_cli.py
- main_cli
- test_proxy_inject.py
- test_ollama_scorer.py
- test_gate.py
- RoutingResult
- Any
- _request_upstream
- [Unreleased]
- GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)
- A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct
- tool_shadow.py
- handle_messages_request
- test_proxy.py
- csmart - Claude Smart Local Routing
- run_local_routing
- test_report.py
- _security_middleware
- TASKS.md - hemat-token-router (csmart.py)
- ADR - hemat-token-router (csmart.py)
- CONTRACTS.md — Inter-track Contracts (frozen)
- ollama_scorer.py
- _read_body_bounded
- _iter_sse_events
- Development Environment
- verify.sh
- _asgi_request
- extract_last_user_prompt
- _truncate_routing_prompt
- test_full_chain_event_sequence
- _clamp_max_tokens
- BaseModel
- _sse_tool_use_empty_round
- drip-refresh.sh
- csmart
- RoutingResult

## God Nodes (most connected - your core abstractions)
1. `RoutingResult` - 50 edges
2. `_run()` - 32 edges
3. `_run()` - 30 edges
4. `StructuredLogger` - 28 edges
5. `mock_upstream()` - 25 edges
6. `execute_local_tool()` - 23 edges
7. `main_cli()` - 22 edges
8. `TTLRoutingCache` - 22 edges
9. `summarize_exploration()` - 21 edges
10. `_sse_text()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `main_cli()` --calls--> `create_report()`  [INFERRED]
  csmart.py → router/report.py
- `main_cli()` --calls--> `GatewayConfig`  [INFERRED]
  csmart.py → router/report.py
- `main_cli()` --calls--> `write_report()`  [INFERRED]
  csmart.py → router/report.py
- `main_cli()` --calls--> `resolve_under_base()`  [INFERRED]
  csmart.py → router/safe_path.py
- `_hermetic()` --uses--> `RoutingResult`  [INFERRED]
  tests/test_proxy.py → router/ollama_scorer.py

## Import Cycles
- None detected.

## Communities (46 total, 6 thin omitted)

### Community 0 - "test_tool_shadow.py"
Cohesion: 0.06
Nodes (64): parametrize, execute_local_tool(), Execute a local exploration tool against a base_dir-scoped sandbox. Args:…, Summarize large non-reader tool output via Ollama; short output passes through.…, summarize_exploration(), capture_logger(), fixture, Hermetic tests for router.tool_shadow exploration tool executor. No live Ollama… (+56 more)

### Community 1 - "resolve_under_base"
Cohesion: 0.17
Nodes (23): Total on-disk bytes of *relpaths* under *base_dir*; missing files count 0.…, _sum_selected_bytes(), is_within(), PathTraversalError, Path, Path validation helpers for safe file access (anti path-traversal). Frozen…, Raised when a path resolves outside the allowed base directory., Resolve *path* to a real absolute path guaranteed inside *base_dir*. Symlink-… (+15 more)

### Community 2 - "test_proxy_server.py"
Cohesion: 0.08
Nodes (54): _min_max_tokens(), Floor for ``max_tokens`` (mirrors ark Smart Gate). Env-overridable., mock_upstream(), _post_messages(), Hermetic server tests for the csmart proxy engine (``router.dispatcher``).…, A full round with ``count`` consecutive GrepTool tool_use blocks., Install a MockTransport upstream; returns a list recording each request.…, POST /v1/messages to the ASGI app and return the response. (+46 more)

### Community 3 - "SDLC Specification v2.0 — csmart: Agentic Reverse Proxy & Local Shadowing"
Cohesion: 0.04
Nodes (46): 10. Observability & Metrics, 11. Rencana Implementasi (Phase-by-Phase), 12. Rencana Testing & Verification Matrix, 13.1 Dev Environment: RTK & DRIP Interference Handling (READ/WRITE), 13. Deployment & Standard Operating Environment (SOP), 14. Risiko & Mitigasi, 15. Open Decisions (item yang perlu dikonfirmasi), 16. Referensi (+38 more)

### Community 4 - "StructuredLogger"
Cohesion: 0.06
Nodes (35): Path, Serialize one record as a JSONL line. False if the lock could not be acquired., Coerce non-JSON-serializable values to str so the writer never chokes., Non-blocking structured logger backed by a bounded queue + one daemon writer…, Enqueue a record asynchronously. Never blocks the caller., Store the per-turn trace id stamped onto subsequent records., Mask a sensitive value. Always returns the fixed placeholder., Block until all pending records have been written to disk. (+27 more)

### Community 5 - "dispatcher.py"
Cohesion: 0.13
Nodes (16): CLI subprocess dispatch for csmart (moved from ``router/dispatcher.py``). Wave…, Read the full content of a file (utf-8)., read_file_content(), _get_or_scan_ast(), _import_candidates(), _module_candidates(), FastAPI reverse-proxy engine for csmart (absorbs ``router/proxy.py``). Wave 2…, Map a dotted module name to absolute candidate paths (may not exist). ``mod``… (+8 more)

### Community 6 - "CODEBASE_ANALYSIS.md — csmart v1.0 (Audit Kondisi Saat Ini)"
Cohesion: 0.06
Nodes (32): 1.1 Peran komponen, 1.2 Topologi makro, 2.1 Pydantic models / DTO (fakta dari kode), 2.2 Class & function signature utama, 2.3 Kontrak antar-stage (alur data), 3.1 Flow `POST /v1/messages` saat ini, 3.2 Detail transformasi payload per stage, 4.1 Status implementasi (fakta) (+24 more)

### Community 7 - "test_ast_extractor.py"
Cohesion: 0.09
Nodes (40): Node, extract_ast_skeleton(), _get_signature_first_line(), AST-based code skeleton extraction using tree-sitter. Extracts…, Scan a project directory recursively for supported source files, extracting AST…, Extract the first line of a node's signature from source bytes., Recursively traverse AST, collect signatures of target node types., Extract AST skeleton (function/class signatures) from a source file. Args:… (+32 more)

### Community 8 - "test_cli.py"
Cohesion: 0.06
Nodes (41): ArgumentParser, build_parser(), CSmartParser, Build the CLI argument parser. Shared flags live on a single parent parser…, ArgumentParser that routes ``start``/``status`` to subparsers while letting any…, Return the first positional token in ``argv``, skipping flags and the value…, Namespace, Hermetic unit tests for csmart CLI parser + main_cli routing (Track A). These… (+33 more)

### Community 9 - "main_cli"
Cohesion: 0.13
Nodes (22): cmd_start(), cmd_status(), main_cli(), Check health of Ollama and upstream gateway., Start the local reverse proxy server., Entry point. Original CLI mode: direct dispatch to Claude Code with pre-routed…, dispatch_claude(), DispatchResult (+14 more)

### Community 10 - "test_proxy_inject.py"
Cohesion: 0.09
Nodes (39): _expand_selected_with_imports(), inject_context_to_messages(), Inject pre-loaded file context into the last user message. Path-safety (F-09):…, Append top-level-imported local modules to the triage-selected files. FIX #3…, capture_logger(), cwd_tmp(), _last_user_content(), fixture (+31 more)

### Community 11 - "test_ollama_scorer.py"
Cohesion: 0.13
Nodes (21): Identify target files to modify based on user prompt using Ollama JSON output.…, route_target_files(), Hermetic tests for router/ollama_scorer.py (S-6 model env, T-4 heuristic).…, Long reasoning is truncated to ≤120 chars (decode-latency win)., Short reasoning stays intact (no over-truncation)., Sanity: the scorer module exposes the fallback without import errors., Ollama success path logs exactly one OLLAMA_TRIAGE with source="ollama"., Fallback path logs OLLAMA_FALLBACK + OLLAMA_TRIAGE(source="heuristic"). (+13 more)

### Community 12 - "test_gate.py"
Cohesion: 0.11
Nodes (29): apply_gate(), Apply confidence threshold and token budget gate to routing result. Rules: 1.…, capture_logger(), _gate_applied_record(), fixture, Unit tests for gate.py budget-aware filtering., Test that confidence exactly equal to threshold passes., Test fallback when overall confidence below but some files pass? Actually all… (+21 more)

### Community 13 - "RoutingResult"
Cohesion: 0.07
Nodes (37): BaseModel, RoutingResult, LRURoutingCache, Thread-safe bounded caching for routing results with LRU and TTL variants. This…, Read TTL from environment variable CSMART_ROUTING_TTL if present., Return current effective TTL from environment or default., Lookup a cached entry, evicting if stale (older than TTL)., Insert/replace an entry, evicting oldest if over capacity. (+29 more)

### Community 14 - "Any"
Cohesion: 0.22
Nodes (8): Any, Execute each held exploration tool locally (parallel) and summarize. Defensive…, Reassemble ``partial_json`` fragments into a tool input dict., Append the assistant tool_use + user tool_result turns., Drives the outbound SSE stream with exploration tool-use shadowing. For each…, Yield SSE bytes to the client, looping internal shadow rounds., Stream one upstream round. Sets ``self._pending_held`` on exit., _ShadowStreamer

### Community 15 - "_request_upstream"
Cohesion: 0.22
Nodes (9): AsyncClient, Exception, BodyTooLargeError, Raised when the upstream gateway is unreachable after retries., Raised when a request body exceeds the configured byte cap., Send a request to upstream with bounded retry; return (client, resp). The…, _request_upstream(), _upstream_timeout() (+1 more)

### Community 16 - "[Unreleased]"
Cohesion: 0.10
Nodes (19): [2.0.0] — 2026-08-28, [2.1.0] — 2026-08-28, A/B Test: request-count vs output correctness (2026-08-28), Added, Added, Changed, Changelog, Fixed (+11 more)

### Community 17 - "GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)"
Cohesion: 0.11
Nodes (17): 1. Ringkasan Eksekutif (Verdict), 2. Gap Matrix per Komponen Target, 3.1 Functional Requirements, 3.2 Non-Functional Requirements, 3. Mapping Requirement Target → Status Baseline, 4.1 Critical — Entrypoint & Runtime Bug (kerjakan paling dulu), 4.2 Feature Baru — Observability & Shadowing (inti v2.0), 4.3 Refactor — Proxy Engine & Ownership (+9 more)

### Community 18 - "A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct"
Cohesion: 0.11
Nodes (17): A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct, Akar masalah (atribusi), Baseline working tree (rusak sebelum uji), Caveat (kejujuran pengukuran), Detail direct S1 (definitif, MAX_ROUNDS=12), Detail direct S2 (gagal), Hasil, Hasil aplikasi (+9 more)

### Community 19 - "tool_shadow.py"
Cohesion: 0.14
Nodes (26): _bounded(), _execute_local_tool_sync(), _extract_message_content(), _get_path(), _normalize_tool_name(), Path, Exploration tool executor for the csmart shadow loop. Frozen contract at Wave 0…, Read a single file's text content (utf-8, lossy). (+18 more)

### Community 20 - "handle_messages_request"
Cohesion: 0.19
Nodes (16): api_route, Response, _build_upstream_headers(), _context_dir(), forward_streaming_request(), handle_messages_request(), _header_allowlist(), passthrough_request() (+8 more)

### Community 21 - "test_proxy.py"
Cohesion: 0.17
Nodes (14): _hermetic(), fixture, Hermetic tests for the csmart reverse-proxy engine (``router.dispatcher``). No…, /v1/messages is intercepted and the mocked SSE upstream is streamed back., Run a coroutine to completion with a fresh event loop., Clear proxy caches + patch routing so no test touches Ollama/AST., CORS preflight OPTIONS allows a loopback Origin and echoes it., CORS preflight with a non-loopback Origin gets no allow-origin header. (+6 more)

### Community 22 - "csmart - Claude Smart Local Routing"
Cohesion: 0.09
Nodes (21): 1. Routing Result (`RoutingResult` - pydantic), 2. Gate Result (`GateResult` - pydantic), 3. Final Report (`CsmartReport` - pydantic), Anti-Spaghetti Coding Rules, Arsitektur (Pipeline Pattern), Aturan untuk AI Coding Tools (CLAUDE.md ini dibaca sebelum edit), CLI Usage, Contoh Output Verified (+13 more)

### Community 23 - "run_local_routing"
Cohesion: 0.11
Nodes (18): _cap_skeleton(), Cap the AST skeleton sent to Ollama while keeping every file header. Lines…, Run local routing: AST scan (cached) -> Ollama scoring -> gate. Async and non-…, run_local_routing(), A skeleton already under the cap is returned byte-identical., Over budget: every // header is kept, the longest - signatures go first., Even a path-only skeleton over an absurdly small budget keeps the first N., run_local_routing hands Ollama a skeleton capped to the env budget. (+10 more)

### Community 24 - "test_report.py"
Cohesion: 0.05
Nodes (73): GateResult, BaseModel, Result of gate application after confidence and budget filtering., cmd_logs(), cmd_stats(), _count_events(), _file_eof_offsets(), follow_log() (+65 more)

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

### Community 29 - "ollama_scorer.py"
Cohesion: 0.22
Nodes (9): _keyword_heuristic(), Truncate an exception string to ``max_len`` chars, appending "..." when cut., Robust fallback heuristic: weighted keyword matching per file from the…, _truncate_error(), T-4: a keyword hitting the real file's path must outrank the same keyword…, Regression: signature-only hits must attribute to the real file, never…, test_keyword_heuristic_never_returns_signature_lines(), test_keyword_heuristic_no_keywords() (+1 more)

### Community 30 - "_read_body_bounded"
Cohesion: 0.40
Nodes (5): _max_body_bytes(), Read the request body, aborting early once the configured cap is exceeded. Uses…, Read and parse the full JSON request body (size-bounded)., _read_body_bounded(), read_full_body()

### Community 31 - "_iter_sse_events"
Cohesion: 0.50
Nodes (4): _iter_sse_events(), _parse_sse_data(), Join ``data:`` lines and JSON-decode them into a payload dict., Parse an httpx streaming response into ``(event_name, payload)`` tuples.

### Community 32 - "Development Environment"
Cohesion: 0.29
Nodes (6): Development Environment, DRIP — Read Layer, Multi-Agent SDLC Rules, Quick Start, RTK — Command Layer, Verify the Tooling

### Community 33 - "verify.sh"
Cohesion: 0.67
Nodes (6): cmd_all(), cmd_smoke(), cmd_test(), cmd_typecheck(), verify.sh script, usage()

### Community 34 - "_asgi_request"
Cohesion: 0.29
Nodes (7): _asgi_request(), Request, Convert an httpx.Request into a Starlette Request (scope + receive). Used for…, P-5: read_full_body catches the chunked/no-content-length oversized path., S-1: _build_upstream_headers forwards only allowlisted headers., test_read_full_body_rejects_oversized(), test_upstream_headers_whitelist()

### Community 36 - "_truncate_routing_prompt"
Cohesion: 0.33
Nodes (6): Keep the TAIL of a routing prompt so cold prefill stays small (P-2). The…, _truncate_routing_prompt(), Long prompts are cut to the TAIL (the task statement lives at the end)., A short prompt is returned unchanged., test_truncate_routing_prompt_keeps_tail(), test_truncate_routing_prompt_short_unchanged()

### Community 37 - "test_full_chain_event_sequence"
Cohesion: 0.20
Nodes (10): A single content-block SSE fragment (no message envelope)., The real pipeline logs every source event once, in order, one trace_id.…, A full round: message envelope + one tool_use block., QG-04: Edit/Write tool_use is forwarded immediately, never shadowed., Read every JSONL record written to a StructuredLogger in ``tmp_path``., _read_records(), _sse_tool_use(), _sse_tool_use_round() (+2 more)

### Community 40 - "_sse_tool_use_empty_round"
Cohesion: 0.17
Nodes (9): cwd_tmp(), fixture, TTL cache reads CSMART_ROUTING_TTL from environment when using default provider., A tool_use block that streams NO input_json deltas (input stays {})., A full round: message envelope + one tool_use block with empty input., chdir to tmp_path so inject's base '.' == tmp_path; restore afterwards., _sse_tool_use_empty_input(), _sse_tool_use_empty_round() (+1 more)

## Knowledge Gaps
- **150 isolated node(s):** `Structured JSONL logging — source-level events (Wave 3, 2026-08-28)`, `A/B Test: request-count vs output correctness (2026-08-28)`, `Performance (2026-08-28, issue #2 P0-P4)`, `Verified (live, 2026-08-28)`, `Fixed` (+145 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RoutingResult` connect `RoutingResult` to `test_proxy_server.py`, `dispatcher.py`, `test_cli.py`, `main_cli`, `test_ollama_scorer.py`, `test_gate.py`, `test_proxy.py`, `run_local_routing`, `test_report.py`, `ollama_scorer.py`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Why does `StructuredLogger` connect `StructuredLogger` to `test_tool_shadow.py`, `test_full_chain_event_sequence`, `dispatcher.py`, `test_proxy_inject.py`, `test_gate.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `main_cli()` connect `main_cli` to `resolve_under_base`, `test_ast_extractor.py`, `test_cli.py`, `test_ollama_scorer.py`, `test_gate.py`, `test_report.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `RoutingResult` (e.g. with `apply_gate()` and `create_report()`) actually correct?**
  _`RoutingResult` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `StructuredLogger` (e.g. with `logger()` and `test_module_singleton()`) actually correct?**
  _`StructuredLogger` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Structured JSONL logging — source-level events (Wave 3, 2026-08-28)`, `A/B Test: request-count vs output correctness (2026-08-28)`, `Performance (2026-08-28, issue #2 P0-P4)` to the rest of the system?**
  _150 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_tool_shadow.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06394230769230769 - nodes in this community are weakly interconnected._