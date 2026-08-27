# GAP_ANALYSIS.md — Baseline v1.0 → Target v2.0 (csmart)

> **Tanggal**: 2026-08-27 · **Repositori**: `/Volumes/Xugab/LAB/Tria/hemat-token-router`
> **Dokumen dibandingkan**:
> - **Baseline (kondisi saat ini)**: `arsitektur/CODEBASE_ANALYSIS.md`
> - **Target (plan refactor)**: `arsitektur/arsitektur-v2.0-sdlc.md`
>
> **Tujuan**: memetakan jarak antara kode yang ada dan arsitektur yang diinginkan, lalu menyusun plan perbaikan yang terukur.

---

## 1. Ringkasan Eksekutif (Verdict)

Fondasi baseline **sudah benar secara konsep** (prepass + context injection jalan), tetapi:

| Dimensi | Status |
|---|---|
| **Entrypoint** | 🔴 Mati total — 2 bug P0 (syntax error + entrypoint `main` tidak ada) → tool tidak bisa dijalankan sama sekali |
| **Fitur inti v2.0** | 🔴 100% belum ada — `logger.py`, `tool_shadow.py`, SSE parsing, tool shadowing **tidak ada di kode** |
| **Quality Gates** | ❌ QG-01 (logging) & QG-03 (shadowing) **FAIL**; QG-02 (latency) **FAIL** (37 s vs target 1.8 s); QG-04 **partial** |
| **Yang sudah ada & benar** | ✅ AST extractor (defensive), Ollama routing + fallback heuristic, confidence gate + budget cap, injection |
| **Testing** | ⚠️ AST + gate hermetic ✓ · proxy **tidak hermetic** (butuh Ollama + network live) |

**Kesimpulan**: ini bukan refactor kecil — **60% pekerjaan adalah implementasi fitur baru** (observability + shadowing), **20% perbaikan bug kritis**, **20% hardening/perf**.

---

## 2. Gap Matrix per Komponen Target

| Komponen target | Status baseline | Gap | Tipe pekerjaan | Prioritas |
|---|---|---|---|---|
| `router/logger.py` | ❌ Tidak ada | Implementasi penuh | **Baru** | P1 |
| `router/tool_shadow.py` | ❌ Tidak ada | Implementasi penuh | **Baru** | P1 |
| `router/dispatcher.py` (proxy engine) | ⚠️ Ada tapi = CLI dispatch; proxy ada di `proxy.py` | Refactor + absorbsi (OD-1) | **Refactor** | P1 |
| `router/ast_extractor.py` | ✅ Ada | Perbaikan kecil: `max_sigs` config, cache | **Perbaikan** | P2 |
| `router/ollama_scorer.py` | ⚠️ Ada | Model hardcode → env; async; heuristic bug (F-12); cap confidence (F-11) | **Perbaikan** | P2 |
| `router/gate.py` | ✅ Ada | Hapus duplikat `GateResult` (F-06) | **Perbaikan** | P1 |
| `router/report.py` | ⚠️ Ada | Metric salah label (F-13); jadi aggregator `stats` | **Perbaikan** | P2 |
| `csmart.py` (CLI daemon) | ❌ Ada tapi rusak | Fix F-01..F-06; subparsers; `logs`/`stats` | **Fix + Baru** | P0/P1 |
| `tests/` | ⚠️ Partial | + logger, + tool_shadow, + proxy hermetic (F-10) | **Baru** | P1 |
| Eksternal (Ollama/upstream) | ✅ Berfungsi | — | — | — |

---

## 3. Mapping Requirement Target → Status Baseline

### 3.1 Functional Requirements

| ID | Requirement target | Status baseline | Keterangan gap |
|---|---|---|---|
| FR-1 | Intercept `POST /v1/messages` + AST | ✅ Ada | Tanpa telemetry; blocking sync |
| FR-2 | Ollama scoring + inject konteks | ✅ Ada | Tanpa cache; re-run tiap turn (F-07) |
| FR-3 | Parse SSE, deteksi `tool_use` | ❌ Tidak ada | Raw passthrough `aiter_raw()` |
| FR-4 | Eksekusi lokal tool eksplorasi | ❌ Tidak ada | `tool_shadow.py` belum ada |
| FR-5 | Summarize Qwen + `tool_result` sintetis | ❌ Tidak ada | Fitur inti v2.0 |
| FR-6 | Stream text/Edit/Write real-time | ⚠️ Partial | Semua di-stream, tanpa klasifikasi |
| FR-7 | JSONL telemetry | ❌ Tidak ada | Tidak ada `logger.py` |
| FR-8 | CLI `start/logs/stats` | ⚠️ Partial | `start`/`status` rusak (F-03); `logs`/`stats` belum ada |
| FR-9 | Trace consistency | ❌ Tidak ada | Tidak ada trace_id |

### 3.2 Non-Functional Requirements

| ID | Requirement target | Status baseline | Keterangan gap |
|---|---|---|---|
| NFR-1 | Latency prepass ≤ 1.8 s | 🔴 **FAIL** | Realita ~37 s (baseline F-07) |
| NFR-2 | Streaming fidelity | ⚠️ Partial | Raw stream OK, tanpa SSE classification |
| NFR-3 | Reliability fallback | ⚠️ Partial | Ollama/AST graceful ✓; **upstream timeout/conn error tidak ditangani** → 500 polos |
| NFR-4 | Security | 🔴 **GAP** | Path traversal (F-09), header broad, tanpa auth, tanpa body cap |
| NFR-5 | Shadow loop bounded | ❌ Tidak ada | Fitur absent; loop bound belum ada |
| NFR-6 | Observability valid schema | ❌ Tidak ada | — |
| NFR-7 | Non-blocking event loop | 🔴 **GAP** | Ollama sync di async handler (F-07) |
| NFR-8 | Model config konsisten | 🔴 **GAP** | Hardcode `qwen2.5-coder:7b` (F-15) |

---

## 4. Plan Perbaikan Terperinci (Master Table)

Kolom: **ID** (referensi baseline) · **Perbaikan** · **Tipe** · **Target (FR/NFR/Fase)** · **Prioritas** · **Kriteria selesai**

### 4.1 Critical — Entrypoint & Runtime Bug (kerjakan paling dulu)

| ID | Perbaikan | Tipe | Target | Prio | Kriteria selesai |
|---|---|---|---|---|---|
| F-01 | Fix `SyntaxError` di `cmd_status()` (`csmart.py:27-28`) — string literal tak tertutup | Fix | Fase 0 | 🔴 P0 | `python3 -m py_compile csmart.py` hijau |
| F-02 | Entrypoint `csmart = "csmart:main"` → ganti ke fungsi yang ada (`main_cli`) | Fix | Fase 0 | 🔴 P0 | `csmart` command jalan setelah install |
| F-03 | Argparse: pakai **subparsers** utk `start`/`status`/`logs`/`stats` (pisah dari positional `prompt`) | Fix | Fase 0/4 | 🟠 P1 | `csmart start` menjalankan proxy, bukan ter-parse sebagai prompt |
| F-04 | Tambah `import json` di top-level `csmart.py` | Fix | Fase 0 | 🟠 P1 | Path `gate_blocked` tidak `NameError` |
| F-05 | Teruskan `--timeout` ke `dispatch_claude`; `subprocess.run(..., timeout=...)` | Fix | Fase 0 | 🟠 P1 | Tidak ada hang tanpa batas |
| F-06 | **Hapus duplikat `GateResult`** di `dispatcher.py`; satu schema dari `gate.py` | Fix | Fase 0 | 🟠 P1 | `dispatch_claude` tidak akses `message` yang tak ada |
| F-09 | Validasi path: `Path.resolve().is_relative_to(root)` sebelum baca file inject/shadow | Fix+Hardening | Fase 0/3 | 🟠 P1 | Path `../` ditolak |

### 4.2 Feature Baru — Observability & Shadowing (inti v2.0)

| ID | Perbaikan | Tipe | Target | Prio | Kriteria selesai |
|---|---|---|---|---|---|
| N-1 | Implement `router/logger.py`: `StructuredLogger` JSONL thread-safe, non-blocking, `trace_id` UUID, redaksi credential | **Baru** | FR-7, FR-9, Fase 1, QG-01 | 🟠 P1 | JSONL valid + trace konsisten; token/prompt tidak pernah di-log |
| N-2 | Implement `router/tool_shadow.py`: exec lokal 6 tool + Qwen summarizer | **Baru** | FR-4, FR-5, Fase 2, QG-03 | 🟠 P1 | `TOOL_SHADOW_INTERCEPT` tercatat; exec sukses |
| N-3 | Implement SSE parser asinkron di proxy (reassembly `partial_json`, deteksi `tool_use`) | **Baru** | FR-3, Fase 3 | 🟠 P1 | Chunk terpotong ter-handle; tool_use terklasifikasi |
| N-4 | Implement shadow loop: hold → exec → summarize → re-submit internal (bounded ≤ 3) | **Baru** | FR-5, NFR-5, Fase 3 | 🟠 P1 | Loop bound; passthrough saat gagal |
| N-5 | CLI `csmart logs` + `csmart stats` (visualisasi JSONL) | **Baru** | FR-8, Fase 4 | 🟡 P2 | Tabel real-time dari JSONL |

### 4.3 Refactor — Proxy Engine & Ownership

| ID | Perbaikan | Tipe | Target | Prio | Kriteria selesai |
|---|---|---|---|---|---|
| R-1 | Absorbsi `proxy.py` → `dispatcher.py` (satu file ownership, OD-1) | Refactor | Fase 3 | 🟠 P1 | Tidak ada dual path; `proxy.py` dihapus |
| R-2 | Pisahkan interception inbound & outbound dalam `dispatcher.py` | Refactor | Fase 3 | 🟠 P1 | Fungsi testable per stage |
| R-3 | `report.py` jadi aggregator per-sesi/harian untuk `stats`; fix metric F-13 | Perbaikan | FR-8, Fase 4 | 🟡 P2 | `estimated_tokens_saved` benar atau `None` |

### 4.4 Performance & Reliability

| ID | Perbaikan | Tipe | Target | Prio | Kriteria selesai |
|---|---|---|---|---|---|
| P-1 | Routing **sekali per sesi** (skip turn lanjutan) + cache AST | Perf | NFR-1, Fase 3 | 🟠 P1 | Prepass ≤ 1.8 s (QG-02) |
| P-2 | Jalankan Ollama/AST via `asyncio.to_thread` (jangan blok event loop) | Perf | NFR-7 | 🟠 P1 | Concurrent request tidak antri |
| P-3 | Tangani upstream timeout/conn error: retry terbatas + error JSON + log `ERROR` | Reliability | NFR-3 | 🟡 P2 | Tidak ada stream setengah terbuka |
| P-4 | `max_sigs` configurable + scan incremental | Perf | NFR-1 | 🟡 P2 | Tidak full `os.walk` tiap request |
| P-5 | Body size cap di `read_full_body` | Hardening | NFR-4 | 🟡 P2 | Request > cap → 413 |

### 4.5 Testing & Quality

| ID | Perbaikan | Tipe | Target | Prio | Kriteria selesai |
|---|---|---|---|---|---|
| T-1 | Test proxy **hermetic**: mock httpx transport + mock scorer (hapus dependensi live) | Fix | Fase 5 | 🟠 P1 | `pytest tests/` hijau tanpa Ollama/network |
| T-2 | `tests/test_logger.py` + `tests/test_tool_shadow.py` | **Baru** | Fase 1/2 | 🟠 P1 | Coverage logger & shadow |
| T-3 | `tests/test_proxy_server.py` dgn fixture SSE upstream (chunk terpotong, parallel tool_use) | **Baru** | Fase 3 | 🟠 P1 | Reassembly teruji |
| T-4 | Test heuristic fallback (fixture skeleton) — fix parsing F-12 | Fix | Fase 5 | 🟡 P2 | File asli terpilih, bukan key signature |
| T-5 | `pyright router/ csmart.py` clean | Quality | kontinu | 🟡 P2 | Tanpa type error |

### 4.6 Security & Hygiene

| ID | Perbaikan | Tipe | Target | Prio | Kriteria selesai |
|---|---|---|---|---|---|
| S-1 | Whitelist header forwarding (strip cookie/x-api-key tak perlu) | Hardening | NFR-4 | 🟡 P2 | Hanya header esensial |
| S-2 | Pertimbangkan auth lokal proxy (minimal loopback + rate limit) | Hardening | NFR-4 | 🟡 P2 | Proses lokal lain tidak bisa relay token |
| S-3 | Redaksi wajib di logger (test redaksi) | Hardening | NFR-4, NFR-6 | 🟡 P2 | Token/prompt tak pernah di log |
| S-4 | Pin `tree-sitter-language-pack <1.0` + dev-group `pytest` di pyproject | Hygiene | Fase 0 | 🟡 P2 | Dependency konsisten ADR-1 |
| S-5 | Bersihkan artefak stale (`csmart.egg-info/`, `debug_*.py`, `.pytest_cache/`) + `.gitignore` | Hygiene | Fase 0 | 🟡 P2 | Repo bersih |
| S-6 | Model dari env (`OLLAMA_TRIAGE_MODEL` / `OLLAMA_SUMMARY_MODEL`) — hapus hardcode | Perbaikan | NFR-8 | 🟡 P2 | Satu sumber config |

---

## 5. Roadmap Eksekusi (Urutan Wajib)

| Fase | Isi | Item | Gate keluar |
|---|---|---|---|
| **Fase 0 — Resusitasi** | Fix semua crash: F-01..F-06, F-09, S-4, S-5 | 8 item | `py_compile` hijau + `csmart start` jalan + `pytest` (hermetic) |
| **Fase 1 — Telemetry** | `logger.py` (N-1) + `test_logger` (T-2) | 2 item | QG-01 pass |
| **Fase 2 — Shadowing** | `tool_shadow.py` (N-2) + path validation (F-09) + `test_tool_shadow` (T-2) | 3 item | QG-03 pass |
| **Fase 3 — Proxy Engine** | Absorbsi (R-1), SSE parser (N-3), shadow loop (N-4), perf (P-1, P-2), reliability (P-3) | 7 item | QG-02 + QG-04 pass |
| **Fase 4 — CLI & Metrics** | Subparsers lengkap (F-03), `logs`/`stats` (N-5), report aggregator (R-3) | 3 item | FR-8 terpenuhi |
| **Fase 5 — Verification** | T-1..T-5, S-1..S-3, S-6 | 8 item | Full suite hijau + security review |

> **Dependency antar fase**: Fase 1 & 2 independen dan bisa paralel setelah Fase 0. Fase 3 bergantung pada Fase 1 (logger) dan 2 (shadow). Fase 4/5 menyusul.

---

## 6. Verifikasi Quality Gates (Before → After)

| Gate | Kriteria | **Before** | **After** (target) |
|---|---|---|---|
| QG-01 | Log JSONL valid, skema lolos Pydantic, trace konsisten | ❌ Tidak ada log | ✅ `logger.py` + `test_logger` |
| QG-02 | AST + Ollama ≤ 1.8 s | ❌ ~37 s | ✅ cache + async + routing sekali/sesi |
| QG-03 | Grep/Glob dicegat & selesai lokal | ❌ Tidak ada | ✅ `tool_shadow.py` + `TOOL_SHADOW_INTERCEPT` |
| QG-04 | Edit/Write/text stream real-time tanpa lag | ⚠️ Raw stream, tanpa klasifikasi | ✅ SSE classification + passthrough |

---

## 7. Open Decisions yang Mempengaruhi Gap

| OD (dari target) | Pengaruh ke plan perbaikan |
|---|---|
| **OD-1** Lokasi proxy engine | Menentukan R-1 (absorbsi `proxy.py` → `dispatcher.py`) |
| **OD-2** Model summarizer (7b vs 14b) | Menentukan S-6 (config env) + kebutuhan RAM |
| **OD-3** Shadow loop bound (=3) | Menentukan N-4 |
| **OD-4** HTTP MITM vs hooks | Alternatif: bila pilih hooks, N-3/N-4 diganti pendekatan settings.json hook (effort berbeda) |
| **OD-5** Routing sekali per sesi | Menentukan P-1 (perf QG-02) |
| **OD-6** CLI mode lama dipertahankan | Menentukan F-03 (subparsers harus dukung `csmart "prompt"`) |
| **OD-7** Log rotation | Menentukan N-1 (logger) |

---

## 8. Estimasi Pekerjaan (Relatif)

| Kategori | Jumlah item | Bobot |
|---|---|---|
| 🔴 Fix kritis (P0/P1) | 7 | 20% |
| 🟠 Feature baru | 5 | 40% |
| 🔧 Refactor proxy | 3 | 15% |
| ⚡ Perf & reliability | 5 | 15% |
| 🔒 Security & hygiene | 6 | 10% |

**Total: ~26 item** · Urutan pengerjaan mengikuti roadmap Fase 0 → 5.

---

*Dokumen ini adalah living roadmap — update setelah tiap fase selesai. Bandingkan ulang dengan `CODEBASE_ANALYSIS.md` bila kode baseline berubah.*
