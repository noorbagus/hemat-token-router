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
| **`router/dispatcher.py`** | Claude CLI subprocess invocation |
| **`router/report.py`** | Structured JSON report schema + serialization |
| **`tests/`** | Unit tests |

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
