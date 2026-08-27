# ADR - hemat-token-router (csmart.py)

## ADR-1: Dependency AST - tree-sitter-language-pack (bukan tree-sitter-languages)

- **Konteks**: Environment pakai Python 3.14. `tree-sitter-languages` tidak menyediakan wheel untuk 3.14 (harus compile dari source, gagal). Explorer mengonfirmasi service Ollama jalan normal, jadi blocker satu-satunya adalah dependency ini.
- **Keputusan**: Gunakan `tree-sitter-language-pack` (pin `>=0.7,<1.0`). Import: `from tree_sitter_language_pack import get_parser, get_language`.
- **Alasan**: Wheel ABI3 (`cp38-abi3`) sehingga compatible dengan Python 3.14 tanpa compile; API drop-in compatible dengan `tree-sitter-languages` (fungsi `get_parser(name)` / `get_language(name)`); actively maintained.
- **Konsekuensi**: Pin major version karena nama fungsi sama tapi versi language grammar bisa bergeser antar release. Semua akses grammar harus lewat satu modul (`router/ast_extractor.py`) agar swap dependency di masa depan hanya menyentuh satu file.

## ADR-2: Modular monolith + pipeline pattern

- **Konteks**: csmart.py adalah CLI tool dengan alur: parse args -> ekstraksi kandidat konteks (AST) -> scoring (Ollama lokal) -> gate -> dispatch (Claude Code CLI) -> report.
- **Keputusan**: Package `router/` dengan satu modul per stage + `router/models.py` sebagai kontrak dataclass bersama. `csmart.py` hanya entrypoint (argparse + orkestrasi), maksimal ~150 baris.
- **Alasan**: Anti-god-function; tiap modul bisa di-test independent dengan mock; builder bisa kerja paralel tanpa file overlap karena boundary = file.
- **Konsekuensi**: Ada file kontrak (`models.py`) yang harus dibuat duluan (Task 1) sebelum task lain merge. Signature drift dicegah lewat kontrak tertulis di TASKS.md + type hints + pyright.

## ADR-3: Confidence gate dengan fallback chain (fail-open default, strict opt-in)

- **Konteks**: Bug arsitektur ditemukan explorer: routing failure tetap mendispatch context kosong ke Claude secara diam-diam, dan tidak ada confidence threshold.
- **Keputusan**: Gate 3 state:
  1. `pass` - Ollama scoring sukses DAN `confidence >= threshold` (default 0.65) -> dispatch dengan context terpilih, marker `confidence="high"`.
  2. `fallback` - Ollama error / JSON invalid / confidence < threshold -> coba heuristic keyword scoring. Bila heuristic menghasilkan >= 1 chunk match -> dispatch dengan context heuristic, marker `confidence="fallback"` + `gate_reason` di report. Heuristic confidence dibatasi 0.5 (selalu di bawah threshold 0.65) supaya tidak pernah dianggap setara Ollama.
  3. `blocked` - heuristic juga kosong. Default (fail-open): dispatch TANPA context dengan marker eksplisit `CONTEXT_NONE` di prompt + `gate_result="blocked"` di report. Dengan flag `--strict`: abort, exit code 2, tidak dispatch.
- **Alasan**: Tujuan tool hemat token, bukan correctness-critical; silent empty context berbahaya karena Claude tidak tahu konteks pernah dicoba. Marker eksplisit = transparan. Strict mode untuk workflow yang mau fail-closed.
- **Konsekuensi**: Report schema butuh field `routing.gate_result` + `gate_reason`. Exit code 2 harus didokumentasikan.

## ADR-4: Budget cap dengan whole-chunk drop (bukan byte truncation)

- **Konteks**: Tidak ada token/byte cap pada context yang di-inject - risiko prompt bengkak.
- **Keputusan**: Budget default 16.000 token, estimasi `bytes // 4` (4 char/token). Sort chunk by score desc, akumulasi sampai budget; chunk yang tidak muat di-drop UTUH (tidak pernah truncate di tengah symbol). Field `budget` di report mencatat selected/dropped/estimated.
- **Alasan**: Chunk = symbol hasil tree-sitter; memotong byte di tengah symbol menghasilkan konteks rusak yang lebih menyesatkan daripada tidak ada.
- **Konsekuensi**: Kapasitas efektif bisa < budget (sisa space tidak cukup untuk chunk berikutnya). Test harus assert invariant: estimated_tokens <= budget.

## ADR-5: Report JSON selalu dibuat; --json hanya mengontrol stdout

- **Konteks**: Bug ditemukan explorer: JSON report hanya di-print saat `--json` ada, sehingga mode default tidak meninggalkan artefak verifikasi.
- **Keputusan**: Report schema v1 SELALU dibangun dan ditulis ke `.csmart/last-report.json` (override via `--report-path`) di setiap run termasuk error/abort. Flag `--json` hanya menambah print report ke stdout. Tanpa `--json`, stdout/stderr menampilkan human summary ringkas.
- **Alasan**: Requirement asli: structured JSON output untuk verification/reporting. Artefak file memungkinkan audit post-mortem tanpa mengubah output default.
- **Konsekuensi**: Directory `.csmart/` harus dibuat (exist_ok). Report juga ditulis saat exit code != 0 (best effort).

## ADR-6: Dispatch Claude Code CLI via stdin, single-shot

- **Konteks**: Perlu mode single-shot edit ke Claude Code CLI dengan context ter-inject; explorer menandai "perlu proper Claude CLI flags".
- **Keputusan**: `subprocess.run(["claude", "-p", "--output-format", "json"], input=prompt, ...)` - prompt dikirim via stdin (hindari arg length limit + quoting), list args tanpa shell, timeout default 600s, output JSON diparse untuk `session_id` / `cost_usd` / `is_error`. Flag `--dry-run` menyusun prompt + report lengkap tanpa spawn proses (untuk verifikasi tanpa burn token).
- **Alasan**: `-p` = non-interactive single-shot; `--output-format json` memberi struktur biaya/session untuk report; stdin menghindari batas panjang argumen OS.
- **Konsekuensi**: Exit code Claude bukan 0 / timeout / JSON invalid -> `status="dispatch_error"`, exit code tool 3. Prompt berisi task + context blocks berlabel file/symbol + confidence marker.

## Exit codes (kontrak global)

| Code | Makna |
|------|-------|
| 0 | Sukses (dispatch selesai, gate pass atau fallback) |
| 2 | Gate blocked + `--strict` (tidak ada dispatch) |
| 3 | Dispatch error (Claude CLI non-zero / timeout / output invalid) |
| 4 | Environment error (Ollama down, model belum dipull, context-dir kosong) |
