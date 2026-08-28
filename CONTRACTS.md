# CONTRACTS.md — Inter-track Contracts (frozen)

> **Status**: FROZEN at Wave 0. Semua builder Wave 1 WAJIB baca file ini sebelum mulai.
> Jangan ubah signature di sini tanpa update SEMUA consumer. Perubahan = update + bump.

## 1. `router/safe_path.py` — anti path-traversal (dibuat Wave 0)

```python
class PathTraversalError(ValueError): ...

def resolve_under_base(path: str | Path, base_dir: str | Path = ".") -> Path
    # symlink-aware (Path.resolve); path '..' / absolute-outside / symlink-outside → PathTraversalError
    # file tak ada di dalam base tetap resolve (bukan error)

def is_within(path: str | Path, base_dir: str | Path = ".") -> bool
    # True jika resolve dalam base; TIDAK pernah raise
```

Consumers: Track C (`router/proxy.py` inject_context), Track E (`router/tool_shadow.py` execute_local_tool).

## 2. `router/logger.py` — StructuredLogger (Track D)

```python
def __init__(self, log_dir: str | Path | None = None)          # default ~/.csmart/logs
def log(self, event: str, **fields) -> None                     # non-blocking; tiap line {ts, trace_id, event, **fields}
def set_trace_id(self, trace_id: str) -> None                   # per-turn UUID
def redact(self, value: str) -> str                             # mask value bila key sensitif

logger  # module singleton; gunakan di Wave 2 via `from router.logger import logger`
```

Event constants (wajib sama persis — dipakai tester & Wave 2):

```python
INBOUND_REQUEST = "INBOUND_REQUEST"
AST_SCANNED = "AST_SCANNED"
OLLAMA_TRIAGE = "OLLAMA_TRIAGE"
TOOL_SHADOW_INTERCEPT = "TOOL_SHADOW_INTERCEPT"
TOOL_LOCAL_EXEC = "TOOL_LOCAL_EXEC"
SSE_STREAM_COMPLETE = "SSE_STREAM_COMPLETE"

# Wave 3 — source-level events (tiap service function emit di titik keputusannya)
AST_CACHE_HIT = "AST_CACHE_HIT"
ROUTING_CACHE_HIT = "ROUTING_CACHE_HIT"
ROUTING_CACHE_MISS = "ROUTING_CACHE_MISS"
ROUTING_CACHE_EXPIRED = "ROUTING_CACHE_EXPIRED"
ROUTING_CACHE_PUT = "ROUTING_CACHE_PUT"
OLLAMA_FALLBACK = "OLLAMA_FALLBACK"
GATE_APPLIED = "GATE_APPLIED"
IMPORT_EXPANSION = "IMPORT_EXPANSION"
CONTEXT_INJECTED = "CONTEXT_INJECTED"
TOOL_SUMMARIZE = "TOOL_SUMMARIZE"
CLI_DISPATCH = "CLI_DISPATCH"
SERVER_START = "SERVER_START"
SERVER_STOP = "SERVER_STOP"
# Operational events (health / passthrough / retry)
PASSTHROUGH = "PASSTHROUGH"
UPSTREAM_HEALTH = "UPSTREAM_HEALTH"
OLLAMA_HEALTH = "OLLAMA_HEALTH"
UPSTREAM_RETRY = "UPSTREAM_RETRY"
```

**Event → emitter (1 record per keputusan, Wave 3):**

| Event | Emitter | Fields kunci |
|---|---|---|
| `INBOUND_REQUEST` | `dispatcher.handle_messages_request` | path, prompt_len, session |
| `AST_SCANNED` | `ast_extractor.scan_project_codebase` | root_dir, scanned_files_count, files_encountered, parse_failures, duration_ms |
| `AST_CACHE_HIT` | `dispatcher._get_or_scan_ast` | context_dir, scanned_files_count, cache_size |
| `ROUTING_CACHE_HIT/MISS/EXPIRED/PUT` | `routing_cache.LRU/TTL.get/.put` | cache(lru\|ttl), key, size, ttl_seconds, age_ms, evicted |
| `OLLAMA_TRIAGE` | `ollama_scorer.route_target_files` (`source="ollama"`) / `_keyword_heuristic` (`source="heuristic"`) | model, source, confidence, selected_files, reasoning, duration_ms |
| `OLLAMA_FALLBACK` | `ollama_scorer._keyword_heuristic` | model, error(≤200), keywords_count, matched_files, confidence, duration_ms |
| `GATE_APPLIED` | `gate.apply_gate` | status, candidates, selected_files, selected_count, selected_bytes, estimated_tokens, dropped_count, threshold, budget_tokens, confidence, reason |
| `IMPORT_EXPANSION` | `dispatcher._expand_selected_with_imports` | base_dir, selected_count, appended_count, expanded_count, dropped_by_budget, budget_tokens, total_bytes |
| `CONTEXT_INJECTED` | `dispatcher.inject_context_to_messages` | files_requested, files_injected, skipped_count, bytes_injected, base_dir |
| `TOOL_SHADOW_INTERCEPT` | `dispatcher._execute_held` | action_taken, tool_name |
| `TOOL_LOCAL_EXEC` | `tool_shadow._execute_local_tool_sync` | tool_name, status(ok\|error), chars, duration_ms |
| `TOOL_SUMMARIZE` | `tool_shadow.summarize_exploration` | tool_name, raw_chars, decision(passthrough_short\|passthrough_reader\|summarize\|fallback_truncated), result_chars, model, duration_ms |
| `SSE_STREAM_COMPLETE` | `dispatcher._ShadowStreamer` | duration_ms, rounds, shadow_used, status |
| `CLI_DISPATCH` | `cli_dispatch.dispatch_claude` | files_count, prompt_len, gate_status, dry_run, exit_code, duration_ms, cost_usd, session_id, error |
| `SERVER_START` / `SERVER_STOP` | `csmart.cmd_start` | host, port, upstream_base_url, ollama_model, context_dir |
| `PASSTHROUGH` | `dispatcher.passthrough_request` | path, method, status_code, duration_ms |
| `UPSTREAM_HEALTH` | `dispatcher.check_upstream_health` | ok, status_code, duration_ms |
| `OLLAMA_HEALTH` | `dispatcher.check_ollama_health` | ok, model, error |
| `UPSTREAM_RETRY` | `dispatcher._request_upstream` | attempt, max_retries, error |

**Re-homing (Wave 3):** `AST_SCANNED`, `OLLAMA_TRIAGE`, `TOOL_LOCAL_EXEC` dipindah dari dispatcher ke source-nya. `OLLAMA_TRIAGE` kehilangan `session`/`cache_hit`/`selected_files` — info itu pindah ke `ROUTING_CACHE_*.key` + `GATE_APPLIED`.

**`trace_id`** scoped per async task via `contextvars.ContextVar` (bukan global lock) — `asyncio.to_thread` membawa context ke worker thread, jadi event source-level (route_target_files, apply_gate, _execute_local_tool_sync, summarize, scan) tercoret trace yang sama dengan turn-nya. `log()` tetap bisa di-override eksplisit lewat kwarg `trace_id=`.

Redaksi key: `authorization`, `api_key`, `x-api-key`, `token` (value → `[REDACTED]`).

## 3. `router/tool_shadow.py` — exploration tool executor (Track E)

```python
TOOL_NAMES: tuple[str, ...] = ("GlobTool", "GrepTool", "View", "LS", "read_file", "FileRead")

async def execute_local_tool(tool_name: str, tool_input: dict, base_dir: str | Path = ".") -> str
    # jalankan via asyncio.to_thread; validasi SEMUA path via resolve_under_base
    # return text output (file list / grep hits / file content / dir listing)

async def summarize_exploration(tool_name: str, raw_output: str) -> str
    # ringkas via qwen HANYA bila len(raw_output) > 4000; else return raw
```

## 4. `router/dispatcher.py` public API (Wave 2 — proxy engine)

```python
app: FastAPI
handle_messages_request(...)    # inbound interception
forward_streaming_request(...)  # outbound SSE streaming + shadow loop
check_ollama_health(...) -> bool
check_upstream_health(...) -> bool
```

## 5. `router/cli_dispatch.py` (Wave 2 — CLI subprocess)

```python
dispatch_claude(files, prompt, gate_info, dry_run=False, timeout: float = 600.0) -> DispatchResult
# gate_info bertipe router.gate.GateResult; pakai .status / .reason (BUKAN .message)
```

## 6. Ownership & Rules

| File | Owner Wave 1 | Wave 2 |
|---|---|---|
| `csmart.py` (import lines `from router.proxy import ...`, `from router.dispatcher import dispatch_claude`) | Track A — JANGAN sentuh import lines | ganti import |
| `router/proxy.py` | Track C (edit inject_context SAJA) | dihapus (diabsorbsi) |
| `router/logger.py` + `tests/test_logger.py` | Track D | konsumen |
| `router/tool_shadow.py` + `tests/test_tool_shadow.py` | Track E | konsumen |

Rules:
- **Satu track = satu file ownership.** Tidak ada dua builder menulis file yang sama.
- Builder TIDAK pernah `git add/commit/push` — orchestrator yang git-write.
- Test baru WAJIB hermetic (patch `ollama.chat`, `httpx.MockTransport`/`ASGITransport`).
- Semua path yang dibaca dari input eksternal WAJIB lewat `resolve_under_base`.
