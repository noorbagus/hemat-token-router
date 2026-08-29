# csmart-lite Comparison — Gap Dua Arah (fork partner)

> **Status**: catatan perbandingan (2026-08-30). Repo partner: `https://github.com/trivnv-at/csmart-lite` (exclude bagian Ollama, buat laptop tua).
> Metode: `diff -u csmart_proxy.py csmart-lite/csmart_proxy.py` → **466 insertions / 140 deletions** (dua file ~80% identik, fork dari base yang sama). Kolom Stream/Non-stream = apakah gap aktif di mode itu (❌ = tidak relevan, bukan fixed).

---

## 1. Kesimpulan

csmart-lite = **fork dari `csmart_proxy.py` kita**. Dua-duanya sudah punya **chat path** + **responses path**. Tapi **divergen dua arah** — tidak ada yang superset:

- **Kita punya fix SSE/tool-calling** (C1/C2/T3/W2/W3/N4) yang csmart-lite TIDAK punya.
- **csmart-lite punya chat tool-history fix + reasoning→thinking + cache_read + steering** yang kita TIDAK punya.
- **10 gap shared** (X-3..X-10, W1, f/g) bolong di kedua repo.

---

## 2. Gap di kita (csmart-lite sudah punya) — 10

| # | Gap | Path | Stream | Non-stream |
|---|-----|------|:------:|:----------:|
| **K1** | Chat history drop `tool_use`/`tool_result` — converter lama return `Dict`, cuma text; `_convert_anthropic_message_to_openai` harus List (tool_calls + role:tool) | chat | ✅ | ✅ |
| **K2** | Reasoning → thinking block TIDAK ada — 4 titik: SSE chat (`reasoning_content`), SSE responses (`reasoning_summary_text.delta`), JSON non-stream responses (`itype=="reasoning"`), JSON non-stream chat (`reasoning_content`) | chat+resp | ✅ | ✅ |
| **K3** | `cache_read_input_tokens` TIDAK di-emit — 4 titik: SSE chat (`prompt_tokens_details.cached_tokens`), SSE responses (`input_tokens_details.cached_tokens`), JSON non-stream chat, JSON non-stream responses | chat+resp | ✅ | ✅ |
| **K4** | Fallback incomplete-stream `saw_terminal_event` tidak ada di chat SSE (upstream mati tanpa message_stop → client gantung) | chat | ✅ | ❌ |
| **K5** | Token clamp cuma floor global 4096, tanpa per-model floor/ceil + tanpa event `TOKEN_CLAMP` (requested/applied/floor/ceil/action) | all | ✅ | ✅ |
| **K6** | Steering **append** + prompt pendek tanpa anti-fabrication; harus PREPEND (posisi pertama biar tidak tenggelam di belakang prompt agent) | all | ✅ | ✅ |
| **K7** | Tanpa `x-api-key` header (upstream Anthropic `/v1/messages` butuh) | all | ✅ | ✅ |
| **K8** | Tanpa local `.env` loading relatif ke script | env | ✅ | ✅ |
| **K9** | Tanpa observability `_tool_names`/`_message_roles`/`_count_tool_use` di log `INBOUND_REQUEST` | log | ✅ | ✅ |
| **K10** | Tanpa cap `reasoning_effort` di chat path (`CSMART_REASONING_EFFORT` default "low") — deepseek CoT bakar token + potensi 400 | chat | ✅ | ✅ |

## 3. Gap di csmart-lite (kita sudah punya) — 5

| # | Gap | Path | Stream | Non-stream |
|---|-----|------|:------:|:----------:|
| **C1** | `function_call_arguments.done` + guard `tool_args_streamed` **dihapus** — hanya handle `.delta`; provider emit args final via `.done` → tool `input` tetap `{}` | responses | ✅ | ❌ |
| **C2** | tool_result dict → revert ke text-only join (`"".join(p.get("text",""))`) — dict/list non-text jadi rusak; harus `json.dumps` | responses | ✅ | ✅ |
| **T3** | `output_text.done` **dihapus** — provider no-delta yang kirim text final via `.done` → text hilang | responses | ✅ | ❌ |
| **W2** | Tanpa `break` setelah error yield di incomplete branch — error stream dilanjutkan completion events | responses | ✅ | ❌ |
| **W3** | Log `message=str(err.get("message",""))[:300]` mentah — **security regression** (body upstream bisa leak); harus `error_type` saja | log | ✅ | ✅ |

## 4. Gap shared (dua-duanya masih bolong) — 10

| # | Gap | Path | Stream | Non-stream |
|---|-----|------|:------:|:----------:|
| X-3 | Retry HTTP 429/5xx TIDAK ada | upstream | ✅ | ✅ |
| X-4 | First-chunk error buffer TIDAK ada — 4xx dibungkus 200 SSE | upstream | ✅ | ❌ |
| X-5 | 0 middleware (loopback/rate-limit/body-cap) — port dari `dispatcher.py:876` | global | ✅ | ✅ |
| X-6 | Health endpoint TIDAK ada | global | ✅ | ✅ |
| X-7 | Model fallback TIDAK ada — single point of failure | routing | ✅ | ✅ |
| X-8 | Sanitize silent — tidak log berapa secret di-mask | log | ✅ | ✅ |
| X-9 | Cost tracking TIDAK ada | log | ✅ | ✅ |
| X-10 | Credential validation TIDAK ada | global | ✅ | ✅ |
| **W1** | Index parallel tool salah attribusi (monotonic counter di responses path; csmart-lite chat sudah pakai map `openai_tool_index_to_block`) | responses | ✅ | ❌ |
| **f/g** | Non-streaming 400 — `reasoning.effort` variant `off`/`xhigh`/`minimal` ditolak upstream; `_resolve_reasoning_effort` identik dua-duanya | both | ❌ | ✅ |

**Pola**: gap **streaming-only** (✅/❌) = SSE event lifecycle (C1, T3, W2, K4, W1, X-4) — non-stream aman karena JSON response bawa data lengkap. Gap **request-side / log / global** = dua-duanya kena. Satu-satunya **non-stream only** = f/g (400).

---

## 5. Tool calling — fokus utama

| Aspek | Kita | csmart-lite |
|-------|------|-------------|
| Responses tool round-trip (`.delta` + `.done` + JSON result) | ✅ **Lengkap** (C1/C2) | ⚠️ cuma `.delta`, result text-only |
| Chat path tool history (multi-turn) | ❌ **Drop tool_use/tool_result** | ✅ **Fixed** (List converter) |
| Thinking block streaming | ❌ | ✅ |
| Index parallel tool | ⚠️ monotonic counter (W1 deferred) | ⚠️ chat: map; responses: counter |

---

## 6. Action items

| # | Aksi | Prioritas |
|---|------|-----------|
| 1 | **Adopsi K1** (chat tool-history) + **K2** (reasoning→thinking, 4 titik) + **K3** (cache_read, 4 titik) ke repo kita | 🔴 P1 — menutup gap T4 + chat multi-turn |
| 2 | **Kirim ke partner**: C1/C2/T3/W2/W3 — mereka harus tarik fix ini (W3 security regression wajib) | 🔴 P1 |
| 3 | **Adopsi K5** (per-model clamp) + **K6** (steering PREPEND anti-fabrication) + K10 (reasoning_effort cap) | 🟡 P2 |
| 4 | Pertimbangkan K7 (x-api-key), K8 (local .env), K9 (observability) | 🟡 P2 |
| 5 | Gap shared X-3..X-10 tetap di pipeline.md (tidak beda antar repo) | — |

## 7. Referensi

- Repo partner: `https://github.com/trivnv-at/csmart-lite` (doc gap mereka: `gap/gap-deepseek-chat-tool-history.md`, `gap/transform-gaps.md`)
- Diff file: 466 insertions / 140 deletions — verifikasi ulang via `diff -u csmart_proxy.py <path-csmart-lite>/csmart_proxy.py`
- Gap status Issue #4: https://github.com/noorbagus/hemat-token-router/issues/4 → C1/C2/T3 fixed di working tree (belum commit)
