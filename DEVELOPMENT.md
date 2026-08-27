# Development Environment

**RTK** (Rust Token Killer) and **DRIP** are part of this repo's dev environment. They intercept the file-access layer — RTK rewrites/summarizes Bash command output, DRIP substitutes `Read` tool results — and are transparent under normal conditions, but each has specific failure modes you must handle. The full specification is `arsitektur/arsitektur-v2.0-sdlc.md` §13.1; this file is the condensed operational reference.

## Quick Start

| Command | Purpose |
|---|---|
| `scripts/verify.sh test` | Run pytest with the RTK-safe interpreter (`rtk proxy python3.14 -m pytest`); extra args are forwarded, e.g. `scripts/verify.sh test tests/test_cli.py -q` |
| `scripts/verify.sh typecheck` | Run `pyright router/ csmart.py` (standalone binary) |
| `scripts/verify.sh smoke` | Run `csmart --dry-run --json` — no Claude dispatch; robust even if Ollama is down (falls back to keyword heuristic) |
| `scripts/verify.sh all` | Run test, then typecheck, then smoke; non-zero exit on any failure |
| `scripts/drip-refresh.sh <path> [path...]` | Refresh DRIP baselines — exactly one `drip refresh` call per file |

## RTK — Command Layer

| Symptom | Cause | Handling |
|---|---|---|
| Test fails `ModuleNotFoundError: urllib3` | Bare `pytest` resolves to a broken Python 3.9, not the project interpreter | Always `rtk proxy python3.14 -m pytest ...` — python3.14 is the interpreter with all deps |
| `grep`/`cat` output summarized (`N matches in M files`, `[+N more]`) | RTK hook summarizes shell output | For exact content use the `Read` tool; for raw shell output use `rtk proxy <cmd>` (bypasses the filter) |
| `python3.14 -m pyright` → `No module named pyright` | pyright is not a Python 3.14 module | Use the standalone `pyright` binary (node-based), never `-m pyright` |
| `rtk gain` fails | Name collision with `reachingforthejack/rtk` | Verify with `which rtk`; fall back to `rtk proxy` |

## DRIP — Read Layer

| Symptom | Cause | Handling |
|---|---|---|
| `Read` → `[DRIP: unchanged since last read]` 0 bytes, no content | Baseline was set by another session/subagent | `drip refresh <path>` (one file per call) → `Read` again |
| `Read` after your own `Edit` → `[DRIP: edit verified \| ...]` | PostToolUse:Edit DRIP | Trust the cert (touched ranges + hash); `drip refresh` for full content |
| Re-read of a changed file → unified diff (`--- old / +++ new`) | Delta-only read | Apply hunks mentally; do NOT re-read the whole file |
| Header `↔ unchanged` / `↕ changed: +N -M` (cross-session) | Cross-session registry | Header is honest; delivered content is current |
| `Edit` fails "must Read before editing" | DRIP-substituted first read skipped native Read, so the read-before-edit tracker is empty | `drip refresh` → `Read` native → then `Edit` |
| `[DRIP: full read \| ↺ compacted]` | After `/compact` / `/clear` / `--resume` | Normal; baseline reset, next read uses delta/unchanged |
| `DRIP_COMPRESS_FIRST_READ_MIN_BYTES` (opt-in) | Compresses big first read | Trade-off: first read is compressed and the Edit tracker is NOT populated |

> `<error>` wrapper containing a DRIP header = **SUCCESS** (transport via `permissionDecision: deny`), not an error. Do not re-request a file already substituted.

## Multi-Agent SDLC Rules

| Rule | Detail |
|---|---|
| **Sole git writer** | Only the orchestrator `git commit`/`push`. Subagents never commit. |
| **Explicit per-wave staging** | Parallel builders write different files in the same working tree, so `git status` mixes ownership. Use `git add <path...>` per wave, never `git add -A`. |
| **Subagent DRIP baseline gap** | A subagent's `Read` records its baseline in its own context, so the orchestrator's re-read appears "unchanged 0 bytes". Recovery: `drip refresh`. |
| **Edit tool = the only code-write path** | Do not `echo`/`tee` code from the shell (it bypasses the RTK rewrite you didn't need). Use the `Edit`/`Write` tools. |
| **Out-of-band write** | After `git pull` / manual edits, `drip refresh` first so the baseline is in sync, then `Read`. |

## Verify the Tooling

```bash
bash -n scripts/*.sh            # syntax check
chmod +x scripts/*.sh           # ensure executable
scripts/verify.sh smoke         # live smoke: dry-run routing report
```
