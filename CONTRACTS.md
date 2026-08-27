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
```

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
