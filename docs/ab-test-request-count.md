# A/B Test — ARK Request Count: Proxy (csmart inject + shadow) vs Direct

- **Tanggal**: 2026-08-28
- **Gateway**: `https://ark.talaga.my.id` · model `doubao-seed-2.0-lite` · streaming `/v1/messages?beta=true`
- **Repo state**: `main` + working tree (`M router/dispatcher.py`, `?? router/routing_cache.py`)

> ⚠️ **PEMBARUAN (verifikasi output, 2026-08-28):** seluruh angka di bawah
> mengukur **jumlah request**, **bukan kebenaran output**. Setelah output
> proxy diverifikasi, keduanya **tidak dapat digunakan** dan tidak memperbaiki
> baseline yang memang sudah rusak (15 test gagal di working tree). Savings
> request real (10→1, ≥12→2), tapi **value-nya nol pada sampel ini**. Detail:
> [Verifikasi Output](#verifikasi-output-2026-08-28).

## Tujuan

Mengukur berapa **request ARK** yang dibutuhkan satu turn refactor, dibandingkan
2 jalur:

| Jalur | Deskripsi | ARK calls dihitung dari |
|-------|-----------|--------------------------|
| **Proxy** | POST 1× ke `http://127.0.0.1:4000` (csmart: AST → Ollama triage → gate → inject → shadow loop) | field `rounds` di `SSE_STREAM_COMPLETE` (log JSONL) |
| **Direct** | POST langsung ke gateway, agent loop naif: jalankan `tool_use` lokal via `router.tool_shadow.execute_local_tool`, re-submit `tool_result`, ulang sampai selesai / `MAX_ROUNDS` | counter di loop |

Prompt sama per skenario, dikirim lewat kedua jalur. Tools yang didefinisikan:
`read_file`, `GlobTool`, `GrepTool`, `View` (semuanya masuk `TOOL_NAMES` proxy,
jadi di-shadow internal saat lewat proxy).

## Skenario

| # | Prompt | Butuh baca |
|---|--------|------------|
| **S1** single-file | Extract shared bounded-insert + eviction logic dari `_routing_ttl_lookup` / `_routing_ttl_store` (dispatcher.py) ke helper, rewire, pertahankan `CSMART_ROUTING_TTL` | 1 file |
| **S2** multi-file | Rewire dispatcher.py agar delegate ke `TTLRoutingCache` / `LRURoutingCache` dari routing_cache.py, hapus duplikat inline | 2 file |

## Hasil

| Skenario | Jalur | ARK calls | Tool_use ke client | Status |
|----------|-------|-----------|--------------------|--------|
| S1 single-file | **Proxy** | **1** | 0 | ✅ selesai |
| S1 single-file | **Direct** | **10** | 9 | ✅ selesai (round 10) |
| S2 multi-file | **Proxy** | **2** | 0 | ✅ selesai |
| S2 multi-file | **Direct** | **≥12** | 12 | ⛔ hit `MAX_ROUNDS`, tidak selesai |

*(Putaran awal dengan `MAX_ROUNDS=6`: proxy 1 vs direct 6 — 6 itu lower bound,
bukan angka asli. Setelah batas dibuka ke 12, direct S1 baru converge di round 10.)*

> ⚠️ "✅ selesai" di tabel = model berhenti meminta tool dan mengembalikan teks.
> **Bukan** berarti output valid/terverifikasi — lihat Verifikasi Output.

### Savings request

- **S1: 10 → 1 = 90%**
- **S2: ≥12 → 2 = ≥83%**

### Detail direct S1 (definitif, MAX_ROUNDS=12)

`View`×2 → `read_file`×3 → `GlobTool`×2 → `read_file`×2 → jawab di round 10.
Total `tool_use` = 9, ARK calls = 10.

### Detail direct S2 (gagal)

`View`×2 → `read_file`×10 → hit cap 12 tanpa jawaban akhir. Model buta struktur
lintas file, eksplorasi self-directed tidak converge.

## Trace proxy (dari `~/.csmart/logs/session_2026-08-28.jsonl`)

| trace_id | Skenario | routing | selected_files | rounds | shadow_used | status |
|----------|----------|---------|----------------|--------|-------------|--------|
| `7f8d0815-...` | S1 (prompt_len 408) | 6881ms, conf 1.0 | `[router/dispatcher.py]` | **1** | 0 | ok |
| `a70af994-...` | S2 (prompt_len 608) | 0ms **[HIT]** | `[router/dispatcher.py]` | **2** | **1** | ok |

- **S1**: triage inject `dispatcher.py` (conf 1.0) → model jawab langsung, 0 eksplorasi → 1 round.
- **S2**: triage **cache HIT** (hasil S1) → hanya `dispatcher.py` ter-inject, `routing_cache.py` **terlewat** → model minta baca `routing_cache.py`, shadow eksekusi lokal (`shadow_used=1`), re-submit → selesai di round 2.

## Interpretasi

1. **Injection adalah penentu utama.** Menyuntik isi file relevan menghapus eksplorasi
   sama sekali (S1: model tidak memanggil tool apa pun). Ini yang memangkas request
   10 → 1.
2. **Shadow adalah safety-net, bukan penghemat request.** Saat injection terlewat
   (S2, file kedua tidak terpilih triage), shadow menahan `tool_use`, mengeksekusi
   lokal, dan re-submit — biaya naik 1 round (2 ARK calls) tapi client tetap lihat
   1 request dan task "selesai" tanpa bocor `tool_use` ke client. ("Selesai" di sini
   hanya berarti model berhenti — output-nya justru rusak, lihat Verifikasi Output.)
3. **Routing cache HIT punya side-effect.** `routing=0ms [HIT]` berarti triage di-cache
   TTL dari request sebelumnya. Untuk `context_dir` yang sama, hasil triage identik
   diulang — kalau prompt berikutnya punya scope beda, injection bisa kurang tepat.
   Pertimbangan tuning `CSMART_ROUTING_TTL` / pembeda cache key.

## Caveat (kejujuran pengukuran)

- **Direct loop adalah agent naif**, bukan Claude Code asli. Angka 10/12 mewakili
  biaya eksplorasi self-directed tanpa konteks; agent yang lebih cerdas (grep dulu,
  baca sekali) bisa lebih murah. Perbandingan ini tetap sah untuk pertanyaan
  "berapa request yang dihemat injection + shadow" vs "model buta".
- **Count ≠ biaya token.** Tiap call ARK di jalur direct membawa seluruh riwayat
  percakapan yang menumpuk, jadi total token direct sebenarnya lebih mahal lagi
  per call seiring bertambahnya round.
- Prompt S2 menyebut `_ROUTING_CACHE` (LRU) yang belum diverifikasi posisinya di
  dispatcher; hasil numerik tidak terpengaruh karena yang diukur adalah jumlah
  round-trip, bukan kebenaran output.

## Verifikasi Output (2026-08-28)

Mengukur **apakah output proxy benar-benar dapat dipakai** — bukan cuma berapa
request-nya. Output S1/S2 di-capture penuh (`proxy_full_S{1,2}.txt`), di-apply ke
salinan repo terisolasi (`verify_s1/`, `verify_s2/`), lalu diuji.

### Baseline working tree (rusak sebelum uji)

Working tree saat pengukuran **sudah 15 test gagal** di
`tests/test_proxy_server.py` — WIP migrasi setengah jadi: test memonkeypatch
`_ROUTING_CACHE` / `_ROUTING_TTL_CACHE` dengan `LRURoutingCache` /
`TTLRoutingCache` (`tests/test_proxy_server.py:161-166`), tapi app code
(`run_local_routing`, `_routing_ttl_*`) masih dict-based → `TypeError:
'...RoutingCache' object does not support item assignment`.

Artinya tugas yang diminta ke model = **menyelesaikan migrasi yang rusak ini**.
Ukuran keberhasilan: apakah output model memperbaiki 15 test tersebut.

### Hasil aplikasi

| Output | Apply | Test proxy (`tests/test_proxy_server.py`) | Verdict |
|--------|-------|--------------------------------------------|---------|
| Baseline (tanpa model) | — | **15 fail, 19 pass** | WIP rusak |
| **S1** (blok kode) | ✅ berhasil | **15 fail, 19 pass** (2 error berubah jadi `AttributeError: no attribute 'lookup'`) | ❌ tidak memperbaiki |
| **S2** (unified diff) | ❌ **patch malformed** — `patch` gagal: body kosong di `def _routing_ttl_seconds` | 15 fail, 19 pass (copy tidak berubah) | ❌ tidak bisa di-apply |

Masalah API spesifik:

- **S1** membuat `BoundedTTLCache` / `RoutingTTLCache` paralel yang **tidak tahu
  `routing_cache.py` sudah ada** → duplikasi. Method `.lookup/.store` tidak cocok
  dengan `TTLRoutingCache.get/.put` yang di-inject test.
- **S2** memakai constructor fiktif `LRURoutingCache(max_size=128)` &
  `TTLRoutingCache(..., env_ttl_key="CSMART_ROUTING_TTL")` — API asli adalah
  `max_entries=` / `ttl_seconds_provider=`. Bahkan kalau patch-nya apply,
  instansiasi langsung `TypeError: unexpected keyword argument`.

### Akar masalah (atribusi)

1. **Injection incomplete.** Triage cuma inject `dispatcher.py`; `routing_cache.py`
   (di-import langsung di baris 50) tidak ikut. S1 menyelesaikan tugas tanpa tahu
   file itu ada → solusi duplikat.
2. **Shadow summarization menghancurkan detail API.** `summarize_exploration`
   (`tool_shadow.py`) meneruskan output ≤4000 char apa adanya, tapi
   `routing_cache.py` = 5035 char → **diringkas qwen2.5-coder:7b** sebelum
   re-submit (trace S2: `TOOL_LOCAL_EXEC View chars=5035`). Model kerja dari
   ringkasan, bukan file asli; signature `max_entries` / `ttl_seconds_provider`
   bisa hilang → model mengisi dengan tebakan (`max_size`, `env_ttl_key`).
3. **Tidak ada feedback loop.** Proxy return 1-shot (1-2 rounds); model tidak
   pernah menjalankan test. Untuk refactor, hemat request tanpa verifikasi =
   hemat di output yang belum tentu benar.

### Implikasi

- **Savings request real**: 10→1 (S1), ≥12→2 (S2).
- **Value-nya nol pada sampel ini** — kedua output rusak dan tidak memperbaiki
  baseline yang memang sudah rusak.
- Menegaskan caveat di atas: angka `rounds` hanya mengukur round-trip, bukan
  kebenaran. A/B yang lebih bermakna memakai ukuran keberhasilan = **test pass**,
  bukan "model berhenti".
- Fix csmart yang disarankan: (a) triage ikut sertakan file yang di-import target;
  (b) jangan summarize file `.py` yang butuh presisi signature (atau pertahankan
  `def`/signature saat summarize); (c) tambah post-verify (syntax / pyright /
  test) sebelum mengklaim selesai.

## Reproduksi

```bash
# skenario 1 (single-file) dan 2 (multi-file)
set -a; source "/Volumes/Xugab/LAB/PrivateLink/credentials/.env"; set +a
python3 ~/.claude/jobs/8558d158/tmp/ab_test.py direct 1   # → ARK calls direct S1
python3 ~/.claude/jobs/8558d158/tmp/ab_test.py proxy 1    # → client 0 tool_use; rounds di log
python3 ~/.claude/jobs/8558d158/tmp/ab_test.py direct 2
python3 ~/.claude/jobs/8558d158/tmp/ab_test.py proxy 2
```

Trace proxy (field `rounds`):

```bash
grep SSE_STREAM_COMPLETE ~/.csmart/logs/session_$(date +%F).jsonl | tail
```

## Referensi

- Script test: `~/.claude/jobs/8558d158/tmp/ab_test.py` (arg: `<proxy|direct> [1|2]`)
- Log proxy: `~/.csmart/logs/session_2026-08-28.jsonl`
- Module shadow: `router/tool_shadow.py` · streamer shadow: `router/dispatcher.py` (`_ShadowStreamer`)
- Cache TTL routing: `router/routing_cache.py` + `CSMART_ROUTING_TTL`
