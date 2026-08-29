# Leak Vectors — Claude Code & csmart

> **Status**: catatan riset (2026-08-29). Untuk plan holistik keamanan — BUKAN hanya proxy.
> Berasal dari: audit tool call Claude Code + riset internet (CVE, advisories, issues).

## Tujuan
Menjadi checklist holistik semua jalur data keluar (leak path) dari Claude Code,
memetakan siapa yang menutup (proxy csmart / native / hook / sandbox / human).

---

## 1. Peta per tool call Claude Code

| Tool | Risiko | Jalur keluar | csmart? | Issue |
|---|---|---|---|---|
| Bash | HIGH | curl header Auth, printenv, cat .env, git push, exfil | ⚠️ sebagian (pattern) | #8, #9 |
| Read | LOW | baca .env/.ssh/credentials → context → upstream | ✅ block path | — |
| Edit/Write | MED | tulis secret ke config.yaml (scan konten belum ada) | ⚠️ nama file saja | #6 |
| Glob/Grep | LOW | grep KEY .env → output ke context | ⚠️ sebagian | — |
| WebFetch | MED | fetch URL `?api_key=` / header | ❌ | #7 |
| WebSearch | LOW | query berisi secret | ❌ | #7 |
| Task (subagent) | MED | mewarisi SEMUA tool parent | ⚠️ tak bisa bedakan | — |
| MCP tool | MED-HIGH | tool call stdio → server remote | ❌ | #5 |
| NotebookEdit | MED | kernel Jupyter network sendiri | ❌ | — |
| TodoWrite | LOW | internal | ✅ | — |

## 2. Vektor dari riset internet

| # | Vektor | Detail | Sumber |
|---|---|---|---|
| A | `ANTHROPIC_BASE_URL` exfil (CVE-2026-21852) | Repo jahat set `ANTHROPIC_BASE_URL` di `.claude/settings.json` → API key terkirim ke server attacker SEBELUM trust prompt. CVSS 5.3 (HN) / 9.1 (HEAL). Fixed v2.0.65 | research.checkpoint.com |
| B | `.mcp.json` consent bypass (CVE-2025-59536) | `enableAllProjectMcpServers=true` → eksekusi tool tanpa approval. CVSS 8.7. Fixed v1.0.111 | blog.checkpoint.com |
| C | Malicious skills/plugins/hooks | `.claude/skills/`, `~/.claude/plugins/`, hooks = kode jalan dengan privilege shell; tanpa lockfile/signing | labs.reversec.com |
| D | `allowed-tools:` silent ignored | Typo di agent frontmatter → subagent dapat SEMUA tool parent (insiden: 85 call, 47 Bash, keychain + 15 curl exfil) | anthropics/claude-code#27099 |
| E | Bash-only sandbox | Read/Write/Edit/Glob/Grep jalan di proses utama tanpa isolasi; hanya Bash yang di-sandbox | anthropics/claude-code#26616 |
| F | Prompt injection via tool result | WebFetch/MCP result bisa berisi "ignore prior instructions" → perintah exfil | tons of skills threat modeling |

## 3. Cakupan penutup per layer

| Layer | Bisa menutup |
|---|---|
| **Proxy csmart** | request LLM (mask), Read/Edit/bash file secret (guardrail), WebFetch/WebSearch (baru), MCP stdio (baru), redirect upstream (A) |
| **Native Claude Code** | sandbox Bash, trust prompt, `ignoreProjectSettings`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` |
| **Hook (PreToolUse)** | block tool sebelum jalan (pattern-based, lihat suite lain) |
| **Sandbox/VM/devcontainer** | isolasi OS-level seluruh proses (menutup E), malware repo |
| **Human process** | review repo tak dikenal, pin version, allowlist permission |

## 4. Prioritas usulan

| Prioritas | Vektor | Penutup | Effort |
|---|---|---|---|
| P0 | MCP stdio (#5) | wrapper JSON-RPC 2 arah | sedang |
| P0 | A. redirect upstream | block `ANTHROPIC_BASE_URL` override di settings project | sedang |
| P1 | B. .mcp.json enableAll | block edit file bernilai true | kecil |
| P1 | C. hook/skills tak dikenal | audit `.claude/` saat first-run | sedang |
| P1 | #6 Write/Edit scan konten | scan `new_string`/`content` | kecil |
| P2 | #7 WebFetch/WebSearch | scan URL+arg | kecil |
| P2 | #8 curl/wget inline | pattern tambahan | kecil |
| P2 | #9 git push file secret | scan staging | sedang |

## 5. Yang TIDAK bisa ditutup proxy csmart

- D (frontmatter bug) — native fix
- E (arsitektur single-process) — butuh sandbox/VM
- F (model behavior / prompt injection) — butuh sandbox, bukan proxy
