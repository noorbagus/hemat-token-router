# TASKS.md - hemat-token-router (csmart.py)

> Pipeline: `parse -> extract (AST) -> score (Ollama) -> gate -> dispatch (Claude CLI) -> report`
> Desain lengkap + alasan keputusan: `docs/ADR.md`. TASKS.md ini adalah single source of truth kontrak antar builder.

## Phase 1: Eksplorasi lingkungan

- [x] Verifikasi Ollama service (jalan normal di localhost:11434)
- [x] Verifikasi model `qwen2.5-coder:7b` (BELUM ter-pull, ~4.7GB - provisioning masuk Task 1)
- [x] Identifikasi blocker dependency: `tree-sitter-languages` gagal di Python 3.14 -> ganti `tree-sitter-language-pack` (ADR-1)
- [x] Temuan arsitektur: tanpa confidence gate, tanpa token cap, JSON report hanya saat `--json`, Claude CLI flags belum benar (ADR-3 s/d ADR-6)

## Phase 2: Desain & ADR

- [x] Arsitektur pipeline modular (ADR-2)
- [x] Keputusan dependency (ADR-1)
- [x] Confidence gate + fallback chain (ADR-3)
- [x] Budget cap whole-chunk drop (ADR-4)
- [x] Report selalu tertulis (ADR-5)
- [x] Dispatch via stdin single-shot (ADR-6)

## Phase 3: Implementasi

**Urutan**: Task 1 duluan (kontrak `models.py`). Task 2-5 paralel setelahnya. Task 6 mulai paralel dengan mock, done setelah semua merge.
**Aturan**: type hints wajib, pyright clean per modul, max 4 parameter per fungsi (pakai dataclass kontrak kalau lebih), jangan edit file milik task lain.

### Kontrak bersama (Task 1 deliverable - field names EXACT, jangan diganti)

```python
# router/models.py
@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    timeout_s: int = 120

@dataclass
class Chunk:
    file: str          # path relatif terhadap context-dir
    symbol: str        # nama symbol, atau "" untuk whole-file
    kind: str          # "function" | "class" | "method" | "file"
    text: str
    start_line: int
    end_line: int
    score: float = 0.0

@dataclass
class RoutingResult:
    method: str        # "ast_ollama" | "ast_heuristic" | "none"
    confidence: float
    chunks: list[Chunk]
    gate_result: str   # "pass" | "fallback" | "blocked"
    gate_reason: str
    chunks_dropped: int = 0
    estimated_tokens: int = 0

@dataclass
class DispatchResult:
    ok: bool
    exit_code: int
    duration_ms: int
    prompt_chars: int
    claude_json: dict | None   # parse dari --output-format json, None jika error/dry-run
    error: str | None = None
```

```python
# Signature tiap modul (max 4 params):
# router/ast_extractor.py
SUPPORTED_EXTS: dict[str, str]        # ".py"->"python", ".js"->"javascript", ".ts"->"typescript", ".go"->"go", dst
def extract_chunks(files: list[Path], max_bytes_per_chunk: int = 8000) -> list[Chunk]

# router/ollama_client.py
class OllamaError(Exception): ...
def check_model(config: OllamaConfig) -> None          # raise OllamaError jika service/model tidak ada
def chat_json(config: OllamaConfig, system: str, user: str) -> str   # POST /api/chat, format=json, temperature 0

# router/scoring.py
def score_chunks(chunks: list[Chunk], task: str, config: OllamaConfig) -> RoutingResult
def heuristic_score(chunks: list[Chunk], task: str) -> RoutingResult

# router/gate.py
def apply_gate(result: RoutingResult, threshold: float, budget_tokens: int, strict: bool) -> RoutingResult

# router/dispatcher.py
def build_prompt(task: str, result: RoutingResult) -> str
def dispatch(prompt: str, timeout_s: int, dry_run: bool) -> DispatchResult

# router/report.py
def build_report(task: str, result: RoutingResult, dispatch: DispatchResult, cli: dict) -> dict
def write_report(report: dict, path: Path) -> None
```

### Tasks

- [ ] [builder] **Task 1: Scaffold + kontrak data + env setup**
  file: `pyproject.toml`, `router/__init__.py`, `router/models.py`, `scripts/setup_env.sh`, `.gitignore`
  done when:
  - `pyproject.toml` pin `tree-sitter-language-pack>=0.7,<1.0`, `httpx>=0.27`, dev-group `pytest>=8`; project name `hemat-token-router`, requires-python `>=3.12`
  - `python -c "from tree_sitter_language_pack import get_parser, get_language"` sukses di Python 3.14
  - `scripts/setup_env.sh` idempotent: buat/aktifkan venv `.venv`, `pip install -e ".[dev]"`, `ollama pull qwen2.5-coder:7b`, verifikasi model muncul via `curl -s localhost:11434/api/tags` (fail dengan pesan jelas kalau Ollama down)
  - `models.py` berisi 4 dataclass di atas dengan field names EXACT (builder lain meng-compile terhadap kontrak ini)
  - `.gitignore` memuat `.venv/`, `.csmart/`

- [ ] [builder] **Task 2: AST extractor**
  file: `router/ast_extractor.py`, `tests/test_ast_extractor.py`
  done when:
  - `extract_chunks()` memakai `get_parser(lang)` dari `tree_sitter_language-pack`; walk `function_definition` / `class_definition` (python), `function_declaration` / `class_declaration` (js/ts/go) -> satu `Chunk` per symbol, `text` diambil via `node.start_byte`/`end_byte` slice dari source bytes
  - Ekstensi tidak dikenal / bahasa tidak ada di pack -> satu `Chunk` `kind="file"` whole-file
  - File > `max_bytes_per_chunk` dan tidak punya symbol -> dipecah jadi Chunk `kind="file"` per ~`max_bytes_per_chunk` baris utuh
  - File kosong / binary (berisi NUL) -> dilewati, tidak raise
  - Test: fixture .py + .js di `tests/fixtures/`, assert jumlah/kind/symbol; test ekstensi unknown; test file besar; semua hijau

- [ ] [builder] **Task 3: Ollama client + scorer**
  file: `router/ollama_client.py`, `router/scoring.py`, `tests/test_scoring.py`
  done when:
  - `check_model()` GET `/api/tags`; service down ATAU model absent -> raise `OllamaError` dengan pesan berisi nama model + petunjuk `ollama pull`
  - `chat_json()` POST `/api/chat` body `{"model", "messages":[system,user], "stream": false, "format": "json", "options": {"temperature": 0.0}}`, return `message.content`
  - `score_chunks()`: kirim maksimal 40 kandidat (pre-filter heuristic top-40 bila lebih) berupa metadata ringkas (file, symbol, kind, 200 char pertama text); minta JSON `{"selection": [{"file", "symbol", "relevance": 0.0-1.0}], "confidence": 0.0-1.0}`; match balik ke `Chunk` via (file, symbol); `confidence` diambil dari response
  - Ollama error / JSON invalid / selection kosong / field hilang -> return hasil `heuristic_score()`
  - `heuristic_score()`: tokenisasi task (lowercase, kata >= 3 char, bukan stopword EN/id dasar); `Chunk.score` = jumlah kata task unik yang muncul di `symbol`/`file`/`text` dibagi total kata; chunk score > 0 dipakai, sort desc; `confidence` = 0.5 jika ada >= 1 match, else 0.0; `method="ast_heuristic"`
  - Test: mock httpx (transport handler) untuk sukses / HTTP 500 / JSON invalid; test heuristic dengan kata kunci pasti; semua hijau TANPA Ollama live

- [ ] [builder] **Task 4: Confidence gate + budget cap**
  file: `router/gate.py`, `tests/test_gate.py`
  done when:
  - `apply_gate()` mengimplementasikan ADR-3 persis:
    - `gate_result="pass"` hanya jika `method=="ast_ollama"` dan `confidence >= threshold`
    - `method=="ast_heuristic"` dengan >= 1 chunk -> `gate_result="fallback"` (confidence tidak pernah dinaikkan)
    - `method=="none"` / heuristic kosong -> `gate_result="blocked"`; jika `strict=True` raise `GateBlocked` (subclass `Exception`, definisikan di `gate.py`)
    - `method=="ast_ollama"` tapi `confidence < threshold` -> turunkan jadi `fallback` bila ada chunk heuristic di list, else `blocked` (scoring sudah menaruh fallback chunks; gate cukup set state)
  - Budget (setelah gate state): sort chunks by `score` desc, akumulasi `len(text.encode()) // 4` per chunk; chunk yang membuat total > `budget_tokens` di-drop UTUH; isi `chunks_dropped` + `estimated_tokens`; invariant `estimated_tokens <= budget_tokens`
  - `budget_tokens=0` -> semua chunk drop (context kosong legal, bukan error)
  - Test: confidence tepat di threshold (>=), di bawah, blocked strict, blocked non-strict, budget overflow drop chunk terendah, budget 0; semua hijau

- [ ] [builder] **Task 5: Dispatcher Claude CLI**
  file: `router/dispatcher.py`, `tests/test_dispatcher.py`
  done when:
  - `build_prompt()` menghasilkan: blok `<task>`, blok `<context confidence="high|fallback|none" reason="...">` berisi `<file path="..." symbol="..." lines="a-b">` + isi chunk; gate blocked non-strict -> `<context confidence="none">` berisi baris `CONTEXT_NONE: routing gagal (alasan) - selesaikan task tanpa konteks ekstra`; fallback -> sertakan paragraf peringatan "konteks dipilih heuristik, verifikasi ulang"
  - `dispatch()` memanggil `subprocess.run(["claude", "-p", "--output-format", "json"], input=prompt, capture_output=True, text=True, timeout=timeout_s)`; parse stdout JSON -> `claude_json`; non-zero exit / `TimeoutExpired` / JSON invalid -> `DispatchResult(ok=False, error=...)`
  - `dry_run=True` -> tidak spawn subprocess sama sekali, `DispatchResult(ok=True, exit_code=-1, claude_json=None, error=None, duration_ms=0)` dengan `prompt_chars` terisi
  - `claude` binary tidak ditemukan (`FileNotFoundError`) -> `ok=False` + error jelas
  - Test: monkeypatch `subprocess.run` (sukses / exit 1 / timeout / FileNotFoundError); assert arg list exact tanpa shell; assert marker CONTEXT_NONE muncul saat blocked; semua hijau

- [ ] [builder] **Task 6: CLI entrypoint + report + e2e**
  file: `csmart.py`, `router/report.py`, `tests/test_e2e.py`
  done when:
  - Argparse: arg posisi `task` (atau `--task-file`), `--context-dir` (default `.`), `--json`, `--strict`, `--threshold` (default 0.65), `--budget` token (default 16000), `--report-path` (default `.csmart/last-report.json`), `--timeout` detik (default 600), `--dry-run`
  - Alur: kumpulkan file dari `--context-dir` (skip `.git`, `.venv`, `node_modules`, `.csmart`, binary) -> `extract_chunks` -> `check_model` (env error -> exit 4, report tetap ditulis `status="env_error"`) -> `score_chunks` -> `apply_gate` (GateBlocked + strict -> exit 2, report `status="gate_blocked"`) -> `build_prompt` + `dispatch` (error -> exit 3) -> `build_report` + `write_report` -> print human summary, atau report JSON penuh ke stdout jika `--json`
  - `csmart.py` hanya orkestrasi (<= ~150 baris); exit code sesuai tabel di `docs/ADR.md`
  - Report schema v1 (field names EXACT):
    ```json
    {
      "schema_version": "1.0", "timestamp": "<ISO-8601>", "status": "ok|gate_blocked|dispatch_error|env_error",
      "task": "...",
      "routing": {"method", "model", "confidence", "threshold", "gate_result", "gate_reason",
                   "candidates", "selected": [{"file","symbol","kind","score","bytes","lines"}]},
      "budget": {"max_tokens", "estimated_tokens", "bytes", "chunks_selected", "chunks_dropped"},
      "dispatch": {"cmd", "exit_code", "duration_ms", "session_id", "cost_usd", "is_error", "result_excerpt"},
      "error": null
    }
    ```
    Report SELALU ditulis walau exit != 0 (ADR-5); `--dry-run` -> `dispatch` berisi `"dry_run": true`
  - Test e2e: `--dry-run` dengan monkeypatch scoring (Ollama live BOLEH tapi opsional) + `dispatch` tidak dipanggil; assert file report tercipta, schema valid, exit code 0; test strict -> exit 2 tanpa file claude dipanggil; semua hijau

## Phase 4: Verifikasi akhir (setelah semua task merge)

- [ ] `bash scripts/setup_env.sh` bersih dari nol (fresh venv)
- [ ] `python -m pytest tests/ -v` semua hijau
- [ ] `python csmart.py --dry-run --json "refactor function X di router/gate.py"` -> stdout report JSON valid, `routing.method` terisi, `budget.estimated_tokens <= 16000`
- [ ] `python csmart.py --dry-run --strict --threshold 0.99 ...` -> exit 2, report `gate_blocked` tertulis
- [ ] Live smoke test (model sudah ter-pull): run nyata tanpa `--dry-run` pada task kecil, exit 0, `.csmart/last-report.json` berisi `session_id` + `cost_usd`
- [ ] pyright clean: `pyright router/ csmart.py`

## Wave 3 — QG Verification (2026-08-28)
- pytest: 83 passed, 0 failed (hermetic, `-m "not live"`) — **84 after Wave-3 fix loop** (+1 regression test)
- QG-01 [PASS] — test_jsonl_file_exists_and_parseable, test_event_and_custom_fields_roundtrip, test_trace_id_propagation, test_redaction_sensitive_keys, test_redaction_x_api_key_and_token, test_redact_method
- QG-02 [PASS] — test_routing_runs_once_per_session
- QG-03 [PASS] — test_exploration_tool_use_intercepted_and_resubmitted, test_shadow_rounds_bounded_at_three, test_traversal_relative_rejected, test_traversal_absolute_rejected, test_view_reads_file, test_grep_returns_hits, test_glob_finds_nested_py
- QG-04 [PASS] — test_text_deltas_streamed_to_client, test_non_exploration_tool_use_passed_through
- Completed Features: F-01..F-06, F-09, S-4, S-5, N-1..N-4, R-1, P-1..P-3, T-3

## Wave 0-3 — Execution Log (2026-08-27/28)

| Wave | Scope | Verdict | Commit |
|------|-------|---------|--------|
| 0 | git init + remote `noorbagus/hemat-token-router` (private) + baseline; freeze `CONTRACTS.md`; `router/safe_path.py` + tests | ✅ | `687901e` (baseline, lint fixes) |
| 1 | Fase 0 entrypoint/config (A), proxy path safety (C), logger (D), tool_shadow (E) — 4 parallel builders | ✅ 83→84 tests | `687901e` (A) · `ff1310e` (C) · `af3a0a6` (D) · `cd95973` (E) |
| 2 | dispatcher.py rewrite: FastAPI proxy engine, SSE shadow loop, routing cache, cli_dispatch split | ✅ 83 tests, pyright 0 | `3c07b27` · `cf79c12` |
| 3 | reviewer → tester∥linter → changelog → **fix loop** (1 BLOCKER + 7 MAJOR + 2 MINOR) → final commit | ✅ 84 tests, pyright 0 | `b48d2c9` (review fixes) · `a1f3c5e` (release) |

**Wave-3 review fix loop (all findings verified against code before fixing):**
- **BLOCKER** — CLI Step 4 raw-read `gate_result.selected_files` (Ollama-chosen) and forwarded to dispatch_claude → exfiltration to upstream gateway. Fixed: every path validated via `resolve_under_base(file, context_dir)`; traversal/missing skipped; regression test `test_main_cli_skips_path_traversal_selected_files` added.
- **MAJOR** — budget passed as bytes-as-tokens (`* 4` → 4× too lenient) in both csmart.py and dispatcher.py → now passes tokens directly to `apply_gate`.
- **MAJOR** — `base_dir` never threaded → gate + `inject_context_to_messages` now resolve relative to `context_dir`.
- **MAJOR** — `_run_glob` absolute patterns raise `NotImplementedError` on Py3.11+ → rejected with ERROR string + added to except tuple.
- **MAJOR** — `_ROUTING_CACHE` unbounded → `OrderedDict` LRU capped at 128 under existing lock.
- **MAJOR** — mid-stream `httpx.TransportError` escaped → truncated client stream → caught, graceful SSE error, `_round_failed` flag.
- **MAJOR** — global `trace_id` race → `trace_id` threaded through `run_local_routing` + INBOUND_REQUEST/AST_SCANNED/OLLAMA_TRIAGE logs.
- **MINOR** — `os.makedirs(dirname(report_path))` crashed on dir-less `--report-path` → guarded both spots.
- **MINOR** — SSE_STREAM_COMPLETE logged `status="ok"` even after round error → `status="error"` when `_round_failed`.
- **Deferred (documented, non-blocking):** list-content injection in `inject_context_to_messages`, redaction depth (fields overwrite trace_id if passed), held-input reassembly seed, `round_had_held` dead var.

**Final state:** `pytest tests/ -q` = 84 passed · `pyright router/ csmart.py` = 0 errors · `csmart --dry-run` report `status: ok`, gate `pass`.
