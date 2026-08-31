Always respond directly and concisely. Never show internal reasoning, thinking steps, or interpretation process before answering.

# Format Komunikasi
- **Ringkas** - jawab langsung, tanpa basa-basi.
- **Tabel** untuk perbandingan, status, langkah, checklist.
- **Bold** untuk kata penting / judul.
- **Istilah teknis pakai bahasa Inggris** - JANGAN diterjemahkan kalau ambigu/membingungkan: **deploy**, **monitoring**, **observability**, **dependency**, **testing/debugging**. Bahasa Indonesia hanya untuk kata umum yang terjemahannya jelas & alami (mis. "buka website", "login", "upload"). Kalau ragu, pakai istilah Inggris + penjelasan singkat dalam kurung saat pertama muncul.

# Keamanan Credential — WAJIB (berlaku semua credential)

Berlaku untuk **semua jenis credential**: env var, API key, access key, token, JWT, password, secret, passphrase, cookie sesi, koneksi string. **Bukan cuma AWS.**

1. **JANGAN pernah print/cetak isi credential** di chat, log, output command, atau file — isi apapun jenisnya.
2. **Selalu mask saat menampilkan**: tampilkan hanya `panjang`, `prefix` (4-6 char), dan `suffix` (last 4) — contoh `sk-ws-...dWpg`, `LTAI5t...`, `***MASKED***`. Nilai penuh tidak boleh muncul.
3. **Credential hanya boleh hidup di env / secret store / keychain**, tidak di source code, chat, atau git.
4. **Saat test/verify kredensial** (curl/CLI ke API): gunakan output **mask**, sertakan cuma status (`HTTP 200` / `401` / error) tanpa body rahasia. Jangan echo key, jangan print header Authorization.
5. **`.env` & file key WAJIB di `.gitignore`** — cek sebelum commit.
6. **Locate (dimana) = boleh disebut; isi (valuenya) = TIDAK boleh.** Kalau user minta "cari login/credential", jawab *lokasi + format + status valid*, JANGAN berikan isi.
7. **AccessKey vs API key itu beda**: AccessKey (RAM/IAM) scope akun cloud penuh; API key (mis. `DASHSCOPE_API_KEY`) scope workspace/layanan. Jangan pakai yang satu untuk keperluan yang lain.
8. **WAJIB fail-safe mask — output = derived, bukan echoed** untuk perintah apa pun yang menyentuh file credential (AWS, Tencent, Google/GCP, Azure, Alibaba/Aliyun, DigitalOcean, Hetzner, dan SaaS lain). **JANGAN pernah `cat`/`grep`/`head`/`awk`/`tail`/`sed` non-fail-safe langsung** ke `~/.aws/credentials`, `~/.aws/config`, `~/.config/gcloud/*`, `~/.tencentcloud/*`, file `.csv` access-key, `.env`, atau file credential lain. Prinsip: tiap baris output di-mask ATAU jadi placeholder — **TIDAK ada pass-through** (`sed` yang cuma mask baris match = bahaya, baris tak-match lolos mentah). Value hanya hidup di variable/file/internal, tidak pernah di output, history, atau chat. Berlaku juga untuk perintah read-only ("cek profile" / "list config") — file credential selalu mengandung secret plaintext.

   **Pola aman READ (output cuma turunan — hash/length/prefix-suffix/status):**
   ```bash
   # Metadata aja (paling aman — 0% bocor)
   shasum -a 256 path/to/.env
   stat -c "%a %s bytes" path/to/.env          # linux (mac: stat -f "%Sp %z bytes")

   # Key name saja (value tidak pernah disentuh)
   grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' .env | tr -d '='

   # Kehadiran key (boolean)
   grep -q '^DATABASE_URL=' .env && echo present || echo missing

   # Length per key (tanpa isi)
   awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{v=substr($0,length($1)+2); print $1" len="length(v)}' .env

   # FAIL-SAFE preview (prefix+suffix+len) — pengganti sed pass-through
   awk -F= '
     /^[A-Za-z_][A-Za-z0-9_]*=/{
       v=substr($0,length($1)+2);
       printf "%s=%s...%s (%d chars)\n", $1, substr(v,1,6), substr(v,length(v)-3,4), length(v);
       next
     } {print "[MASKED]"}
   ' .env

   # Round-trip compare file vs Secret Store (value TIDAK pernah keluar)
   # Linux: secret-tool (libsecret) / pass / keepassxc-cli; mac: security (Keychain)
   cmp -s <(grep -m1 '^KEY=' .env | cut -d= -f2-) \
          <(secret-tool lookup service "name") \
     && echo MATCH || echo MISMATCH

   # AWS — native mask, aman bawaan
   aws configure list --profile <name>
   aws sts get-caller-identity --profile <name>
   aws iam list-access-keys --user-name <user> --profile <name>   # access key ID = bukan rahasia

   # Service account JSON — field non-rahasia + hash saja, JANGAN jq '.private_key'
   jq '{type, project_id, client_email}' path/to/sa.json
   shasum -a 256 path/to/sa.json

   # Verify live — status saja, token via env var (bukan inline di command)
   set -a; source <(grep '^KEY=' .env); set +a
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $KEY" https://api.example.com/verify
   ```

   **Pola aman WRITE/UPDATE/DELETE (value tak pernah lewat chat/history):**
   ```bash
   # Secret store yang dipakai (Linux):
   #   secret-tool   — libsecret/GNOME Keyring (paling umum)
   #   pass          — passwordstore, file GPG-encrypted
   #   keepassxc-cli — KeePassXC (bisa pakai keyfile/db)
   #   systemd-ask-password — wrapper untuk service systemd
   # Pilih 1 dan konsisten; pada mac pakai `security` (Keychain).

   # File → Secret Store (value dibaca di dalam command, tak pernah tampil)
   # secret-tool store --label="<label>" service "name" user "$USER" \
   #   <<< "$(grep -m1 '^KEY=' .env | cut -d= -f2-)"
   # pass insert -f "name" \
   #   <<< "$(grep -m1 '^KEY=' .env | cut -d= -f2-)"

   # Secret Store → file / server (langsung, tanpa lewat chat)
   secret-tool lookup service "name" > /tmp/x && chmod 600 /tmp/x && mv /tmp/x ./secret
   secret-tool lookup service "name" | ssh -i key.pem user@host "umask 077; cat > /app/.env"

   # Input manual — tidak masuk history
   read -s SECRET && printf 'KEY=%s\n' "$SECRET" >> .env && chmod 600 .env && unset SECRET

   # Update 1 key (rewrite via var, bukan ketik value)
   v=$(secret-tool lookup service "name")
   grep -v '^KEY=' .env > .env.tmp && printf 'KEY=%s\n' "$v" >> .env.tmp && mv .env.tmp .env && chmod 600 .env && unset v

   # Delete 1 key / dari Secret Store
   grep -v '^OLD_KEY=' .env > .env.tmp && mv .env.tmp .env && chmod 600 .env
   secret-tool clear service "name"           # atau: pass rm "name"
   ```

   **⛔ DILARANG (bocor otomatis ke output):**
   | Perintah | Alasan |
   |----------|--------|
   | `cat`/`head`/`tail` file credential | value penuh keluar |
   | `printenv` / `env` | dump SEMUA secret |
   | `sed` non-fail-safe | baris tak-match pass-through |
   | `docker inspect` / `compose config` mentah | env + secret ikut keluar |
   | `curl -H "Authorization: ..."` inline | token ke history + ps |
   | `jq .` file JSON penuh | semua field termasuk private_key |
   | `grep -A/-B` context di credential | context lines = value |
   | `echo $SECRET` | value ke output |

   Kalau lupa dan secret sempat tercetak: anggap **terekspos**, segera laporkan ke user + masukkan ke daftar rotasi.

### Command Equivalents: macOS → Linux

| Fungsi | macOS | Linux |
|--------|-------|-------|
| Sudo + GUI auth popup | `osascript -e 'do shell script "sudo <cmd>" with administrator privileges'` | `pkexec <cmd>` (PolicyKit GUI prompt) |
| Popup input field (teks) | `osascript -e 'display dialog "..." default answer ""'` | `zenity --entry --text "..."` (GTK) / `kdialog --inputbox "..."` (KDE) |
| Popup password field | `osascript -e 'display dialog "..." with hidden answer'` | `zenity --password` / `kdialog --password` |
| Popup file picker | `osascript -e 'choose file'` | `zenity --file-selection` / `kdialog --getopenfilename` |
| Clipboard | `pbcopy` / `pbpaste` | `xclip` / `xsel` (X11) / `wl-copy` / `wl-paste` (Wayland) |

Catatan:
- `pkexec` butuh PolicyKit (polkit) terpasang dan sesi GUI aktif (tidak jalan di headless/SSH tanpa `DISPLAY`/`WAYLAND_DISPLAY`). Di headless pakai `sudo -v` + `read -s` manual, atau `systemd-ask-password`.
- Output `zenity`/`kdialog` = nilai dari field → jangan di-echo; langsung pipe ke file/store yang 600, atau assign ke variabel lalu `unset`.
- Contoh input field aman (value tak pernah lewat chat):
   ```bash
   # mac: osascript -e 'display dialog "KEY?" default answer ""' | ...
   # linux (GTK):
   secret=$(zenity --entry --title "KEY" --text "Masukkan value KEY" --hide-text)
   printf 'KEY=%s\n' "$secret" >> .env && chmod 600 .env && unset secret
   ```

# Karpathy Guidelines (LLM coding pitfalls)

_Sumber: https://github.com/forrestchang/andrej-karpathy-skills_

1. **Think Before Coding** - Jangan asumsi. State asumsi eksplisit, present tradeoffs, kalau tidak jelas berhenti & tanya.
2. **Simplicity First** - Kode minimal yang solve masalah. Tidak ada fitur spekulatif, abstraksi untuk 1 use, error handling untuk skenario mustahil.
3. **Surgical Changes** - Sentuh cuma yang perlu. Jangan "improve" kode sekeliling. Match style existing. Buang import/var yang jadi orphan karena perubahanmu.
4. **Goal-Driven Execution** - Transform task jadi verifiable goal: "Add validation" → "tulis test untuk invalid input, lalu buat pass". Loop sampai verified.

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
- Hardcoded gateway config (DeepSeek resmi, Anthropic-compatible endpoint):
  - `base_url: https://api.deepseek.com/anthropic`
  - `primary_model: deepseek-v4-flash`
  - `opus_model: deepseek-v4-pro`
  - `fast_model: deepseek-v4-flash`
  - `effort_level: low`
- Catatan: DeepSeek API key disimpan sebagai `ANTHROPIC_AUTH_TOKEN` di `/Volumes/Xugab/LAB/PrivateLink/.env.local` (bukan `credentials/.env`). Jalur CLI (`cli_dispatch.py`) load kedua file env. Upstream default proxy di-override via env `ANTHROPIC_UPSTREAM_URL`.

### OpenCode Go Multi-Model Routing (proxy `csmart_proxy.py`)

Proxy support full model set OpenCode Go lewat **3 endpoint** (dipilih per-request dari `body.model`):

| Endpoint | Model families | Env override |
|---|---|---|
| `/responses` (OpenAI Responses) | `grok-`, `gpt-5.6-`, `muse-` | `CSMART_RESPONSES_PATTERNS` |
| `/chat/completions` (OpenAI Chat) | `glm-`, `kimi-`, `longcat-`, `deepseek-`, `mimo-`, `hy3`, `hy4-`, `o1-`, `o3-`, `text-`, `davinci-`, `curie-`, `gpt-` | `CSMART_OPENAI_PATTERNS` |
| `/messages` (Anthropic-native, base yang sama) | `minimax-`, `qwen3` | `CSMART_ANTHROPIC_NATIVE_PATTERNS` |

⚠️ **JANGAN pakai `opencode-` sebagai pattern** — itu org prefix (`opencode-go/<id>`), bukan model family; semua id ber-prefix bakal ke-hijack ke `/responses` (bug `opencode-go/hy3` → 502). `hy3` tanpa dash sengaja (id-nya `hy3`).

- Key terpisah: `OPENAI_API_KEY` untuk `OPENAI_BASE_URL` (default `https://opencode.ai/zen/go/v1`); `ANTHROPIC_AUTH_TOKEN` untuk DeepSeek passthrough.
- Model id `opencode-go/<id>` di-strip prefix-nya (`clean_openai_model_name`) sebelum dikirim upstream.
- Model Anthropic-native (minimax/qwen) di-**passthrough mentah**: nama model dipertahankan (skip FLASH rewrite), tanpa protocol transform, butuh `x-api-key` (K7) + `OPENAI_API_KEY`.
- Alias id: `deepseek-chat`→`deepseek-v4-flash`, `deepseek-reasoner`→`deepseek-v4-pro` (id asli DeepSeek tidak ada di OpenCode Go → 401). Override via `CSMART_ALIAS_DEEPSEEK_CHAT[_TO]` / `CSMART_ALIAS_DEEPSEEK_REASONER[_TO]`.
- Satu port (default `8080`) layani semua model — verifikasi live: muse/deepseek/gpt-5.6-luna/minimax/qwen/glm semuanya 200.

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

### Perintah inti (urutan)

```bash
graphify god-nodes                          # 1. hub utama arsitektur
graphify explain "<node>"                   # 2. detail tiap hub (source, neighbors)
graphify path "<modulA>" "<modulB>"         # 3. alur antar modul
graphify query "<pertanyaan>"               # 4. tanya spesifik
```

Kalau graph belum ada: `graphify update .` (build graph, no LLM, code-only).

### Aturan

1. **Cek graph ada**: `[ -f graphify-out/graph.json ]` → kalau tidak ada, skip ke flow normal.
2. `explain` ambigu (label duplikat) → pakai **node id** (dari output `explain`), jangan tebak.
3. Catat `source_file:L` + tag `[EXTRACTED]`/`[INFERRED]` untuk tiap klaim. Node di `tests/` = test, bukan production.
4. **Read file source HANYA setelah** graph menunjuk file relevan — baca di line yang ditunjuk, bukan file utuh.

**Larangan:** jangan baca `graph.json` mentah (ledakkan context); jangan baca semua file untuk "paham konteks".

**Update graph:** `graphify update .` (no LLM) setelah edit code; `git pull` → `graphify update .`; auto per commit via `graphify hook install`.
