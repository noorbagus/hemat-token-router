# csmart - Claude Smart Local Routing

Token-optimized CLI proxy for Claude Code: Local AST scanning + Ollama-based routing selects only relevant context before dispatching to Claude Code. Reduces token usage by **60-90%** for large codebases.

## Arsitektur (Pipeline Pattern)

```
parse args → validate env → AST skeleton extraction → Ollama JSON routing
→ confidence gate + token budget cap → context bundling → Claude CLI dispatch
→ write structured JSON report
```

## Daftar File

| File | Tanggung Jawab |
|------|----------------|
| **`csmart.py`** | CLI entrypoint, main orchestrator |
| **`pyproject.toml`** | Dependencies + project metadata |
| **`router/ast_extractor.py`** | Tree-sitter: extract function/class signatures from source |
| **`router/ollama_scorer.py`** | Ollama client: JSON-based file relevance scoring |
| **`router/gate.py`** | Confidence threshold + token budget cap |
| **`router/dispatcher.py`** | FastAPI reverse-proxy engine (routing + SSE shadow loop) |
| **`router/cli_dispatch.py`** | Claude CLI subprocess invocation (`dispatch_claude`) |
| **`router/routing_cache.py`** | LRU + TTL cache untuk hasil routing |
| **`router/logger.py`** | `StructuredLogger` JSONL (trace_id, redaksi, non-blocking) |
| **`router/logs_viewer.py`** | `csmart logs` / `csmart stats` viewer |
| **`router/report.py`** | Structured JSON report schema + serialization |
| **`tests/`** | Unit tests |

## Structured JSONL Logging

Semua service function emit **structured JSON** di titik keputusannya sendiri (JSONL ke `~/.csmart/logs/session_<date>.jsonl`). AI coding tools membaca event ini untuk menelusuri pipeline per turn:

| Event | Emitter |
|---|---|
| `INBOUND_REQUEST` | `dispatcher.handle_messages_request` |
| `AST_SCANNED` | `ast_extractor.scan_project_codebase` |
| `AST_CACHE_HIT` | `dispatcher._get_or_scan_ast` |
| `ROUTING_CACHE_HIT/MISS/EXPIRED/PUT` | `routing_cache.LRU/TTL.get/.put` |
| `OLLAMA_TRIAGE` / `OLLAMA_FALLBACK` | `ollama_scorer.route_target_files` / `_keyword_heuristic` |
| `GATE_APPLIED` | `gate.apply_gate` |
| `IMPORT_EXPANSION` | `dispatcher._expand_selected_with_imports` |
| `CONTEXT_INJECTED` | `dispatcher.inject_context_to_messages` |
| `TOOL_SHADOW_INTERCEPT` | `dispatcher._execute_held` |
| `TOOL_LOCAL_EXEC` / `TOOL_SUMMARIZE` | `tool_shadow._execute_local_tool_sync` / `summarize_exploration` |
| `SSE_STREAM_COMPLETE` | `dispatcher._ShadowStreamer` |
| `CLI_DISPATCH` | `cli_dispatch.dispatch_claude` |
| `SERVER_START` / `SERVER_STOP` | `csmart.cmd_start` |
| `PASSTHROUGH` / `UPSTREAM_HEALTH` / `OLLAMA_HEALTH` / `UPSTREAM_RETRY` | `dispatcher` (ops) |

- **trace_id**: scoped per async task via `contextvars` — semua event dalam satu turn (termasuk yang via `asyncio.to_thread`) tercoret trace sama.
- **Redaksi**: key `authorization`/`api_key`/`x-api-key`/`token` → `[REDACTED]`.
- **Cara cek**: `csmart logs --follow` atau `csmart stats`.
- Daftar lengkap field per event: `CONTRACTS.md` §2.

## JSON Schema Contracts

### 1. Routing Result (`RoutingResult` - pydantic)
```python
class RoutingResult(BaseModel):
    target_files: list[str]      # 1-3 file paths to modify
    confidence: float           # 0.0 - 1.0
    reasoning: str              # short explanation
```

### 2. Gate Result (`GateResult` - pydantic)
```python
class GateResult(BaseModel):
    status: str                 # "pass" / "fallback" / "blocked"
    selected_files: list[str]   # after filtering/budget cap
    selected_bytes: int
    estimated_tokens: int
    dropped_count: int
    reason: str
```

### 3. Final Report (`CsmartReport` - pydantic)
```python
class CsmartReport(BaseModel):
    schema_version: str        # "1.0"
    status: str                 # "ok" / "gate_blocked" / "dispatch_error" / "env_error"
    timestamp: str              # ISO-8601 UTC
    task: str                   # original user prompt
    execution_metrics:
        ast_scan_ms: int
        local_routing_ms: int
        total_prepass_ms: int
        injected_files_count: int
        injected_bytes: int
    routed_context: RoutingResult
    gate_result: GateResult
    gateway_config:
        base_url: str
        primary_model: str
        opus_model: str
        fast_model: str
        effort_level: str
    claude_execution: Optional[DispatchResult]
    estimated_tokens_saved: Optional[int]
```

## Default Configuration

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `--threshold` | 0.65 | Minimum confidence to pass gate |
| `--budget` | 16000 | Maximum token budget for injected context (≈ 64KB) |
| `--report-path` | `.csmart/last-report.json` | Where to persist JSON report |
| `DEFAULT_IGNORE_DIRS` | `.git`, `node_modules`, `dist`, `build`, `.next`, `venv`, `.venv`, `.dart_tool`, `coverage`, `.turbo`, `.cache`, `__pycache__` | Directories di-skip saat scan |

## CLI Usage

```bash
csmart [options] "your coding task prompt"

Options:
  --json            Print full JSON report to stdout
  --strict          Abort if confidence below threshold (fail-closed)
  --threshold FLOAT  Confidence threshold (default: 0.65)
  --budget INT       Max token budget (default: 16000)
  --report-path PATH  Report output path (default: .csmart/last-report.json)
  --timeout INT      Claude CLI timeout in seconds (default: 600)
  --dry-run          Compose everything but don't dispatch to Claude (testing)
  --context-dir PATH  Root directory to scan (default: .)
```

## Dependency Requirements

- Python >= 3.10
- `tree-sitter>=0.26.0`
- `tree-sitter-language-pack>=0.7.0` (**NOT** `tree-sitter-languages` - that one doesn't work on Python 3.14)
- `ollama>=0.6.2`
- `pydantic>=2.0.0`
- `python-dotenv>=1.0.0`
- Ollama running locally with `qwen2.5-coder:7b` pulled
- Claude Code CLI installed and authenticated

## Environment (Gateway Config)

Gateway credentials loaded from: `/Volumes/Xugab/LAB/PrivateLink/credentials/.env`

- `ANTHROPIC_AUTH_TOKEN` - required
- Hardcoded gateway config:
  - `base_url: https://ark.talaga.my.id`
  - `primary_model: doubao-seed-2.0-lite`
  - `opus_model: glm-5.3`
  - `fast_model: deepseek-v4-flash`
  - `effort_level: low`

## Aturan untuk AI Coding Tools (CLAUDE.md ini dibaca sebelum edit)

1. **JANGAN** ubah dependency dari `tree-sitter-language-pack` balik ke `tree-sitter-languages` - that's the Python 3.14 blocker we fixed
2. Pertahankan **modular structure**: satu file satu tanggung jawab (pipeline pattern)
3. JSON schema **harus** tetap valid untuk automation/CI parsing - jangan ubah struktur field tanpa upgrade schema_version
4. Pertahankan confidence gate + token budget cap - ini critical untuk token saving
5. Selalu `--dry-run` test sebelum dispatch ke Claude untuk verifikasi routing

## Contoh Output Verified

```
$ csmart --json --dry-run "Fix indentation error in csmart.py"
================================================== VERIFICATION REPORT (JSON) ==================================================
{
  "schema_version": "1.0",
  "status": "ok",
  "timestamp": "2026-08-27T15:41:14.724317+00:00",
  "task": "Fix the indentation error in csmart.py",
  "execution_metrics": {
    "ast_scan_ms": 140,
    "local_routing_ms": 37621,
    "total_prepass_ms": 37761,
    "injected_files_count": 1,
    "injected_bytes": 6679
  },
  "routed_context": {
    "target_files": ["csmart.py"],
    "confidence": 1.0,
    "reasoning": "..."
  },
  "gate_result": {
    "status": "pass",
    "selected_files": ["csmart.py"],
    ...
  }
}
```

---

# General Guidelines (dari global CLAUDE.md)

## Format Komunikasi
- **Ringkas** - jawab langsung, tanpa basa-basi.
- **Tabel** untuk perbandingan, status, langkah, checklist.
- **Bold** untuk kata penting / judul.
- **Istilah teknis pakai bahasa Inggris** - JANGAN diterjemahkan kalau ambigu/membingungkan: **deploy**, **monitoring**, **observability**, **dependency**, **testing/debugging**. Bahasa Indonesia hanya untuk kata umum yang terjemahannya jelas & alami (mis. "buka website", "login", "upload"). Kalau ragu, pakai istilah Inggris + penjelasan singkat dalam kurung saat pertama muncul.

## Anti-Spaghetti Coding Rules

Gejala spaghetti khas AI - waspadai:
1. **God function** - fungsi ratusan line karena "works"
2. **Function signature drift** - nambah parameter tanpa update semua caller
3. **Dual code path** - path baru aktif, path lama tidak dihapus
4. **Inconsistent guard logic** - guard di 1 fungsi, lupa di fungsi serupa
5. **Duplicate logic** - copy-paste pattern, bukan extract ke helper
6. **Import alias chaos** - import ulang di tiap fungsi (`import json as _jd`), bukan 1x di top-level
7. **Global mutable state** - var di module level, bukan dependency injection

Rules:
- **Arsitektur dulu, baru kode** - minta plan dulu, wajib untuk perubahan >3 file
- **Cek semua caller setelah edit fungsi** - pastikan signature match (verify via pyright)
- **Max 4 parameter per fungsi** - kalau lebih, refactor atau pakai dict/kwargs
- **No dual paths** - hapus path lama sebelum path baru aktif
- **Helper untuk pola berulang** - extract, jangan copy-paste
- **Guard harus system-wide** - cek semua fungsi dengan flow mirip
- **Type hints + pyright wajib sebelum commit** - jangan skip type error; signature drift sering muncul sebagai `Argument of type X is not assignable to parameter`
- **Pipeline pattern > monolithic** - decompose handler besar jadi stages: parse -> validate -> route -> execute -> respond

Target architecture: **Modular Monolith + Pipeline Pattern**
- Per domain/modul: folder sendiri; shared helpers di `common/`
- No global vars - pakai DI atau app.state
- Tiap modul bisa di-test independent

## Prompt Engineering - BROKE

| Huruf | Maksud | Contoh |
|-------|--------|--------|
| **B** | Background (konteks) | "Ini project FastAPI + asyncpg + Redis 7" |
| **R** | Role (persona) | "Kamu senior backend engineer" |
| **O** | Objective (tujuan) | "Refactor webhook_receive -> pipeline" |
| **K** | Key Constraints (batasan) | "Jangan ubah Redis key name / public API" |
| **E** | Examples / Expected Output | "Return format: diff minimal, bukan rewrite full file" |

Wajib di tiap prompt:
1. **Tech stack + versi** - "Python 3.11, FastAPI 0.110" - biar AI tidak pakai API deprecated
2. **Role persona** - hasil lebih terarah
3. **Constraint checklist** - apa yang BOLEH dan TIDAK boleh diubah
4. **Chain-of-Thought untuk debugging** - "Jelaskan analisis langkah demi langkah sebelum kode final"
5. **1 prompt = 1 tanggung jawab** - jangan gabung refactor + test + deploy

Teknik lanjutan:
- **Prompt chaining** - task besar dipecah: design -> implementasi -> testing, tiap phase prompt terpisah
- **Few-shot prompting** - kasih 1-2 contoh input-output
- **Negative constraints** - "Jangan tambah dependencies baru"
- **Atomic commits** - 1 task selesai -> commit, cegah regresi
- **Diff-only request** - "kirim diff minimal, jangan rewrite seluruh file"

## Type Checker - pyright (cegah signature drift)

```bash
pyright Project/src/
```

| Fitur | pyright | mypy |
|-------|---------|------|
| Presisi | ✅ Tangkap semua signature drift | ✅ Strict mode kuat |
| Kecepatan | ✅ Cepat (incremental) | ❌ Lambat di project besar |
| Integrasi editor | ✅ Pylance default di VS Code/Cursor | ⏳ Plugin |
| Setup | ✅ 1 command | ✅ 1 command |
| Strictness | ⚠️ Default medium | ✅ `--strict` |

Rekomendasi: **pyright untuk daily use** (cepat + presisi), mypy di CI untuk strict check tiap release.

Kebiasaan wajib:
- Type hints di tiap fungsi baru - biar pyright bisa deteksi drift
- Jalankan pyright setelah edit fungsi - cek semua caller
- Jangan skip type error

## Graphify First (wajib untuk AI coding tools)

**Rule: kalau project punya `graphify-out/graph.json`, baca graph DULU sebelum baca file source.**

1. **Cek graph ada**: `[ -f graphify-out/graph.json ]` → kalau tidak ada, skip ke flow normal.
2. **Orientasi arsitektur**: `graphify god-nodes` + `graphify explain "<file>"`
3. **Sebelum baca file source**, query graph dulu: `graphify query "<pertanyaan>"` / `graphify path "<A>" "<B>"` / `graphify explain "<symbol>"`
4. **Read file source HANYA setelah** graph menunjuk file relevan.

**Larangan:** jangan baca `graph.json` mentah (ledakkan context); jangan baca semua file untuk "paham konteks".

**Update graph:** `graphify update .` (no LLM) setelah edit code; `git pull` → `graphify update .`; auto per commit via `graphify hook install`.

## Karpathy Guidelines (LLM coding pitfalls)

_Sumber: https://github.com/forrestchang/andrej-karpathy-skills_

1. **Think Before Coding** - Jangan asumsi. State asumsi eksplisit, present tradeoffs, kalau tidak jelas berhenti & tanya.
2. **Simplicity First** - Kode minimal yang solve masalah. Tidak ada fitur spekulatif, abstraksi untuk 1 use, error handling untuk skenario mustahil.
3. **Surgical Changes** - Sentuh cuma yang perlu. Jangan "improve" kode sekeliling. Match style existing. Buang import/var yang jadi orphan karena perubahanmu.
4. **Goal-Driven Execution** - Transform task jadi verifiable goal: "Add validation" → "tulis test untuk invalid input, lalu buat pass". Loop sampai verified.
