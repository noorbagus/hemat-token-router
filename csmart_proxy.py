#!/usr/bin/env python3
"""csmart v3 — standalone local optimizer proxy (single file).

Pipeline: sanitizer -> DLP/secret-vault -> guardrails -> reversible CCR ->
3-region prefix aligner -> heuristic model router -> SSE streaming -> keepalive.

Prioritas: sanitasi key/credential agar TIDAK bocor ke upstream, ke disk, maupun
ke log. Standalone — tidak mengimpor ``router/``; pola ditiru dari v2.1.0
(``shadow_loop``, ``sse_stream``, ``safe_path``, ``logger``).

Cara pakai:
    export UPSTREAM_BASE_URL="https://api.deepseek.com/anthropic"
    export UPSTREAM_API_KEY="sk-..."        # atau ANTHROPIC_AUTH_TOKEN dari PrivateLink .env
    python3.14 csmart_proxy.py
    export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"; export ANTHROPIC_API_KEY="dummy"
    claude
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from cryptography.fernet import Fernet as _Fernet
except ImportError:  # pragma: no cover
    _Fernet = None


# =====================================================================
# ENV LOADING (mirror router/cli_dispatch.py:36-37,130-131)
# =====================================================================
def _load_gateway_env() -> None:
    """Load the PrivateLink gateway env files so ANTHROPIC_AUTH_TOKEN is found
    even when only the proxy script is started (no prior env export)."""
    for path in (
        "/Volumes/Xugab/LAB/PrivateLink/credentials/.env",
        "/Volumes/Xugab/LAB/PrivateLink/.env.local",
    ):
        if load_dotenv is not None and os.path.exists(path):
            load_dotenv(path, override=False)


_load_gateway_env()

# =====================================================================
# CONFIGURATION & CONSTANTS
# =====================================================================
UPSTREAM_BASE_URL = (
    os.getenv("ANTHROPIC_UPSTREAM_URL")
    or os.getenv("UPSTREAM_BASE_URL")
    or "https://api.deepseek.com/anthropic"
)
UPSTREAM_API_KEY = os.getenv("UPSTREAM_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN", "")
PROXY_HOST = os.getenv("CSMART_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("CSMART_PORT", "8080"))
DB_PATH = os.getenv("CSMART_DB", "csmart_state.db")

FLASH_MODEL = os.getenv("CSMART_FLASH_MODEL", "deepseek-chat")
FLAGSHIP_MODEL = os.getenv("CSMART_FLAGSHIP_MODEL", "deepseek-reasoner")
UPSTREAM_TIMEOUT = float(os.getenv("CSMART_UPSTREAM_TIMEOUT", "120"))
MAX_TOKENS_FLOOR = int(os.getenv("CSMART_MIN_MAX_TOKENS", "4096"))
MAX_ROUNDS = int(os.getenv("CSMART_MAX_SHADOW_ROUNDS", "5"))

# Sanitizer (noise reduction)
ANSI_ESCAPE_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SANITIZE_TRUNCATE_BYTES = int(os.getenv("CSMART_SANITIZE_MAX_BYTES", "2048"))
SANITIZE_TRUNCATE_LINES = int(os.getenv("CSMART_SANITIZE_MAX_LINES", "40"))

# Reversible CCR
CCR_MIN_BYTES = int(os.getenv("CSMART_CCR_MIN_BYTES", "3072"))
CCR_PREVIEW_LINES = int(os.getenv("CSMART_CCR_PREVIEW_LINES", "10"))

# DLP
DLP_ALLOW = [w for w in os.getenv("CSMART_DLP_ALLOW", "").split(",") if w]

# Secret vault at-rest
VAULT_PERSIST = os.getenv("CSMART_VAULT_PERSIST", "0") == "1"
VAULT_KEY = os.getenv("CSMART_VAULT_KEY", "")

# Keepalive (jaga KV-cache TTL provider, biasanya 5 menit)
KEEPALIVE_TICK = int(os.getenv("CSMART_KEEPALIVE_TICK", "30"))
KEEPALIVE_WINDOW_START = int(os.getenv("CSMART_KEEPALIVE_WINDOW_START", "270"))
KEEPALIVE_WINDOW_END = int(os.getenv("CSMART_KEEPALIVE_WINDOW_END", "300"))

# Heuristic router triggers (flagship tier)
_COMPLEX_TRIGGERS = [
    t.strip()
    for t in os.getenv(
        "CSMART_ROUTE_FLAGSHIP_KEYWORDS",
        "architecture,refactor whole system,security audit,database migration,redesign,multi-file refactor",
    ).split(",")
    if t.strip()
]

# OpenAI-native model detection and endpoints
OPENAI_MODEL_PATTERNS = [
    t.strip()
    for t in os.getenv(
        "CSMART_OPENAI_PATTERNS",
        "gpt-,o1-,o3-,muse-,opencode-,text-,davinci-,curie-",
    ).split(",")
    if t.strip()
]
OPENAI_BASE_URL = os.getenv(
    "CSMART_OPENAI_BASE_URL",
    os.getenv("OPENAI_BASE_URL", "https://api.opencode.com/v1").rstrip("/")
)
OPENAI_CHAT_COMPLETIONS_PATH = os.getenv(
    "CSMART_OPENAI_CHAT_PATH", "/chat/completions"
)
OPENAI_RESPONSES_PATH = os.getenv(
    "CSMART_OPENAI_RESPONSES_PATH", "/responses"
)

# System Prompt Steering for OpenAI-native models
# Instructs model to follow Claude Code tool use format exactly
SYSTEM_STEERING_PROMPT = """You are a Claude Code agent that follows EXACTLY the Claude Code tool use format:
- You MUST format tool calls as a JSON array in the tool_use block.
- You MUST NOT add extra preamble, explanations, or thinking outside the content block.
- You MUST use the provided tool definitions when the user asks to take action.
- You MUST follow the input_schema exactly when generating tool_use calls.
"""

# Logging
LOG_DIR = os.getenv("CSMART_LOG_DIR", "")
VERBOSE = os.getenv("CSMART_VERBOSE", "0") == "1"

# =====================================================================
# REDACTED LOGGING — key tidak pernah masuk log
# =====================================================================
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "x-api-key",
    "token",
    "password",
    "secret",
    "real_secret",
    "client_secret",
    "access_key",
    "private_key",
}


def _redact(value: Any) -> Any:
    """Blank sensitive values by key name (never prints credentials)."""
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() in _SENSITIVE_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _log(event: str, **fields: Any) -> None:
    """Emit one redacted JSONL event. Never raises; never logs secrets."""
    try:
        rec = _redact({"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields})
        if LOG_DIR:
            Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
            path = Path(LOG_DIR) / f"session_{datetime.now().strftime('%Y%m%d')}.jsonl"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        elif VERBOSE:
            sys.stderr.write(json.dumps(rec) + "\n")
    except Exception:  # logging must never break the proxy
        pass


def _banner() -> None:
    sys.stderr.write(
        f"[csmart] proxy http://{PROXY_HOST}:{PROXY_PORT} -> {UPSTREAM_BASE_URL} "
        f"(flash={FLASH_MODEL}, flagship={FLAGSHIP_MODEL})\n"
    )


# =====================================================================
# DATABASE INITIALIZATION
# =====================================================================
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS context_blobs (
                ref_id TEXT PRIMARY KEY,
                payload_type TEXT,
                raw_content TEXT,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS secret_vault (
                mask_id TEXT PRIMARY KEY,
                real_secret TEXT,          -- NULL kecuali CSMART_VAULT_PERSIST=1 (terenkripsi)
                pattern_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()


# =====================================================================
# 1. DLP & BIDIRECTIONAL SECRET VAULT
# =====================================================================
# Gitleaks-inspired high-precision patterns: (regex, label). Group 1, bila ada,
# adalah nilai secret yang akan di-mask (bukan pembungkus assignment).
SECRET_REGEXES: List[Tuple[str, str]] = [
    (r"(?i)\bsk-[A-Za-z0-9_-]{20,}", "openai_key"),
    (r"(?i)\bsk-ant-[A-Za-z0-9_-]{20,}", "anthropic_key"),
    (r"(?i)\bghp_[A-Za-z0-9]{36}", "github_token"),
    (r"(?i)\bgithub_pat_[A-Za-z0-9_]{20,}", "github_pat"),
    (r"(?i)\bglpat-[A-Za-z0-9_-]{20,}", "gitlab_token"),
    (r"(?i)\bxox[baprs]-[A-Za-z0-9-]{10,}", "slack_token"),
    (r"(?i)\bsk_live_[A-Za-z0-9]{16,}", "stripe_live"),
    (r"(?i)\bsk_test_[A-Za-z0-9]{16,}", "stripe_test"),
    (r"(?i)\bAIza[0-9A-Za-z_-]{20,}", "gcp_api_key"),
    (r"(?i)\bya29\.[0-9A-Za-z_-]+", "google_oauth"),
    (r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", "aws_access_key"),
    (r"\bey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}", "jwt_token"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private_key"),
    (r"(?i)\Brpk_[A-Za-z0-9]{16,}", "rpk"),
    (r"(?i)\bnvapi-[A-Za-z0-9_-]{20,}", "nvidia_token"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", "bearer_token"),
    (
        r"(?i)\b(?:password|passwd|secret|token|api_key|apikey|access_key|client_secret|private_key)\s*[:=]\s*[\"']?([^\"'\s\n,;]+)",
        "generic_secret",
    ),
]
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX_RE = re.compile(r"[0-9a-fA-F]{28,}")


def _shannon_entropy(s: str) -> float:
    """Shannon entropy in bits per character (base 2)."""
    if not s:
        return 0.0
    length = len(s)
    counts: Dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    entropy = 0.0
    for cnt in counts.values():
        p = cnt / length
        entropy -= p * math.log2(p)
    return entropy


def _b64url_key(key: str) -> bytes:
    """Derive a Fernet-compatible URL-safe b64 key (32 bytes) from an env key."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SecretVault:
    """Two-tier masking + bidirectional restore.

    At-rest (default): real secrets live ONLY in process memory — tabel
    ``secret_vault.real_secret`` tetap NULL. Persist terenkripsi (Fernet)
    opsional via ``CSMART_VAULT_PERSIST=1`` + ``CSMART_VAULT_KEY``.
    """

    def __init__(self) -> None:
        self.mem_cache: Dict[str, str] = {}   # mask_id -> real_secret
        self.reverse_cache: Dict[str, str] = {}  # real_secret -> mask_id
        self._fernet: Any = None
        if VAULT_PERSIST:
            if _Fernet is None or not VAULT_KEY:
                _log(
                    "VAULT_CONFIG",
                    error="CSMART_VAULT_PERSIST=1 but cryptography/CSMART_VAULT_KEY missing; falling back to in-memory",
                )
            else:
                self._fernet = _Fernet(_b64url_key(VAULT_KEY))
        self._load_persisted()

    def _load_persisted(self) -> None:
        if self._fernet is None:
            return
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT mask_id, real_secret, pattern_type FROM secret_vault WHERE real_secret IS NOT NULL"
                ).fetchall()
            for row in rows:
                mask_id = row["mask_id"]
                secret = self._fernet.decrypt(row["real_secret"].encode("utf-8")).decode("utf-8")
                self.mem_cache[mask_id] = secret
                self.reverse_cache[secret] = mask_id
        except Exception as exc:  # stale key / corrupt row -> ignore
            _log("VAULT_LOAD", error=str(exc))

    def get_or_create_mask(self, secret: str, pattern_type: str) -> str:
        existing = self.reverse_cache.get(secret)
        if existing:
            return existing
        hash_id = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]
        mask_id = f"__CSMART_SEC_{hash_id}__"
        self.mem_cache[mask_id] = secret
        self.reverse_cache[secret] = mask_id
        try:
            with get_db() as conn:
                if self._fernet is not None:
                    enc = self._fernet.encrypt(secret.encode("utf-8")).decode("utf-8")
                    conn.execute(
                        "INSERT OR REPLACE INTO secret_vault (mask_id, real_secret, pattern_type) VALUES (?, ?, ?)",
                        (mask_id, enc, pattern_type),
                    )
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO secret_vault (mask_id, real_secret, pattern_type) VALUES (?, NULL, ?)",
                        (mask_id, pattern_type),
                    )
                conn.commit()
        except Exception as exc:
            _log("VAULT_PUT", error=str(exc))
        return mask_id

    def mask_text(self, text: str) -> str:
        """Two-tier masking: high-precision regex, then selective entropy pass."""
        if not text:
            return text
        # Tier 1: known secret formats.
        for pattern, ptype in SECRET_REGEXES:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                val = groups[0] if groups and groups[0] else match.group(0)
                if isinstance(val, str) and len(val) >= 8:
                    text = text.replace(val, self.get_or_create_mask(val, ptype))
        # Tier 2: entropy safety net for unknown-but-likely-secret tokens.
        for word in text.split():
            clean = word.strip("\"'()[]{}<>,;:")
            if self._looks_like_secret(clean):
                text = text.replace(clean, self.get_or_create_mask(clean, "high_entropy"))
        return text

    def unmask_text(self, text: str) -> str:
        """Restore secrets on the client-bound path ONLY (never sent upstream)."""
        if not text or "__CSMART_SEC_" not in text:
            return text
        for mask_id, real in list(self.mem_cache.items()):
            text = text.replace(mask_id, real)
        return text

    def _looks_like_secret(self, token: str) -> bool:
        """Conservative heuristic so legit code (hashes, paths, UUIDs) is not masked."""
        if len(token) <= 28 or _shannon_entropy(token) <= 4.5:
            return False
        if token.startswith(("__CSMART_", "ref_", "sha256:", "0x", "http", "www.")):
            return False
        if "/" in token:  # path-like
            return False
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", token):
            return False
        if _UUID_RE.fullmatch(token) or _HEX_RE.fullmatch(token):
            return False
        if re.fullmatch(r"[A-Za-z_]+[A-Za-z_0-9]*", token) and not any(c.isdigit() for c in token):
            return False  # plain identifier (camel/snake) tanpa digit
        if not any(c.isupper() for c in token):
            return False
        has_digit = any(c.isdigit() for c in token)
        has_sep = "-" in token or "_" in token or "." in token
        if not (has_digit or has_sep):
            return False
        for allow in DLP_ALLOW:
            if allow and allow in token:
                return False
        return True


vault = SecretVault()

# =====================================================================
# 2. SANITIZER & GUARDRAIL
# =====================================================================
BLOCKED_PATH_PATTERNS = [
    r"\.env(?:\..+)?$",                        # .env, .env.local (akhir path)
    r"id_(?:rsa|ed25519|dsa|ecdsa)(?:\.pub)?",
    r"\.pem$",
    r"\.p12$",
    r"\.pfx$",
    r"\.key$",
    r"\.git/config$",
    r"credentials\.(?:json|csv)$",
    r"(?:service[_\-]account)[\w\-]*\.json$",
    r"client_secret[\w\-]*\.json$",
    r"\.kube/config$",
    r"[\\/]\.ssh[\\/]",
    r"[\\/]\.aws[\\/]",
    r"[\\/]\.config[\\/]gcloud[\\/]",
]
BLOCKED_COMMAND_PATTERNS = [
    r"^\s*(?:printenv|env|export\s+-p)\b",
    r"security\s+find-generic-password",
    r"aws\s+configure\s+(?:get|list)",
    r"gcloud\s+auth\s+",
    r"(?:cat|less|more|head|tail|sed|awk|grep|base64|strings)\s+.*(?:\.env|id_rsa|id_ed25519|\.pem|\.key|credentials)",
    r"(?:source|\.)\s+[~/]?[\w/]*\.env\b",
]
# Hanya mask pattern glob (bukan path literal) yang menunjuk file secret.
_BLOCKED_GLOB_MARKERS = (".env", "id_rsa", "id_ed25519", ".pem", ".key", "credentials")


def _canonicalize_path(p: str) -> str:
    """Expand ~ and resolve symlinks/.. so pattern checks cannot be bypassed."""
    return os.path.realpath(os.path.expanduser(p))


def check_security_guardrails(tool_name: str, tool_input: Any) -> Optional[str]:
    """Return a violation message if *tool_input* touches credentials, else None."""
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool_name in ("bash", "execute_command", "command", "run_command"):
        cmd = str(tool_input.get("command") or tool_input.get("cmd") or "")
        for pattern in BLOCKED_COMMAND_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return f"command memuat akses credential sensitif (diblokir): {cmd[:120]}"
    candidates: List[str] = []
    for key in ("path", "file_path", "filepath", "cwd", "root", "subpath"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            candidates.append(val)
    for key in ("view", "edit", "read", "glob"):
        sub = tool_input.get(key)
        if not isinstance(sub, dict):
            continue
        for k2 in ("file_path", "path", "pattern"):
            val = sub.get(k2)
            if not isinstance(val, str) or not val:
                continue
            if k2 == "pattern" and not any(m in val for m in _BLOCKED_GLOB_MARKERS):
                continue  # glob umum (mis. "**/*.py") bukan file secret
            candidates.append(val)
    for path in candidates:
        canon = _canonicalize_path(path)
        for pattern in BLOCKED_PATH_PATTERNS:
            if re.search(pattern, canon, re.IGNORECASE):
                return f"akses file '{path}' dicegat (kandungan credential sensitif)"
    return None


def sanitize_raw_logs(text: str) -> str:
    """Strip ANSI escapes and head-tail truncate logs > 2KB."""
    if not isinstance(text, str) or not text:
        return text
    text = ANSI_ESCAPE_REGEX.sub("", text)
    if len(text.encode("utf-8")) > SANITIZE_TRUNCATE_BYTES:
        lines = text.splitlines()
        if len(lines) > SANITIZE_TRUNCATE_LINES:
            head = "\n".join(lines[:20])
            tail = "\n".join(lines[-20:])
            snipped = len(lines) - (SANITIZE_TRUNCATE_LINES)
            text = f"{head}\n\n... [CSMART SNIPPED {snipped} LINES] ...\n\n{tail}"
    return text


def _mask_dict(value: Dict[str, Any]) -> Dict[str, Any]:
    """Mask every string leaf of a (small) nested dict — e.g. tool_use.input."""
    return {
        k: (_mask_dict(v) if isinstance(v, dict) else (vault.mask_text(v) if isinstance(v, str) else v))
        for k, v in value.items()
    }


def _mask_text_block(value: Any) -> Any:
    """Sanitize + mask a text block (dict with 'text' / string)."""
    if isinstance(value, dict):
        out = dict(value)
        if isinstance(out.get("text"), str):
            out["text"] = vault.mask_text(sanitize_raw_logs(out["text"]))
        return out
    if isinstance(value, str):
        return vault.mask_text(sanitize_raw_logs(value))
    return value


def sanitize_payload(body: Dict[str, Any]) -> None:
    """In-place: sanitize + mask system and message content, block tool_use.input."""

    def _walk_content(content: Any) -> Any:
        if isinstance(content, str):
            return vault.mask_text(sanitize_raw_logs(content))
        if isinstance(content, list):
            out: List[Any] = []
            for block in content:
                if not isinstance(block, dict):
                    out.append(block)
                    continue
                b = dict(block)
                btype = b.get("type")
                if btype in ("text", "input_text", "output_text"):
                    b = _mask_text_block(b)
                elif btype == "tool_result":
                    c = b.get("content")
                    if isinstance(c, str):
                        b["content"] = vault.mask_text(sanitize_raw_logs(c))
                    elif isinstance(c, list):
                        b["content"] = [_mask_text_block(x) for x in c]
                elif btype == "tool_use":
                    inp = b.get("input")
                    if isinstance(inp, dict):
                        b["input"] = _mask_dict(inp)
                out.append(b)
            return out
        return content

    sysval = body.get("system")
    if isinstance(sysval, str):
        body["system"] = vault.mask_text(sanitize_raw_logs(sysval))
    elif isinstance(sysval, list):
        body["system"] = [_mask_text_block(s) for s in sysval]
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                msg["content"] = _walk_content(msg.get("content"))


def clamp_max_tokens(body: Dict[str, Any]) -> Dict[str, Any]:
    mt = body.get("max_tokens")
    if isinstance(mt, int) and mt < MAX_TOKENS_FLOOR:
        body["max_tokens"] = MAX_TOKENS_FLOOR
    return body


# =====================================================================
# 3. REVERSIBLE CONTEXT STORAGE (CCR)
# =====================================================================
EXPAND_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "csmart_expand_symbol",
    "description": "Mengambil isi payload/file utuh yang sebelumnya dipadatkan oleh proxy csmart CCR.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ref_id": {"type": "string", "description": "ID referensi context, e.g. 'ref_8a1f4b2c'"}
        },
        "required": ["ref_id"],
    },
}


def store_ccr_payload(payload_type: str, content: str) -> Tuple[str, str]:
    """Persist a large payload to SQLite, return (ref_id, compact stub)."""
    ref_id = f"ref_{hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]}"
    token_est = len(content) // 4
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO context_blobs (ref_id, payload_type, raw_content, token_count) VALUES (?, ?, ?, ?)",
                (ref_id, payload_type, content, token_est),
            )
            conn.commit()
    except Exception as exc:
        _log("CCR_PUT", error=str(exc))
    lines = content.splitlines()
    preview = "\n".join(lines[:CCR_PREVIEW_LINES]) if len(lines) > CCR_PREVIEW_LINES else content
    stub = (
        f"{preview}\n\n"
        f"[CSMART CCR: konten penuh ({token_est} tokens) tersimpan di {ref_id}. "
        f"Gunakan tool 'csmart_expand_symbol' dengan ref_id='{ref_id}' bila perlu isi lengkap.]"
    )
    return ref_id, stub


def get_ccr_payload(ref_id: str) -> Optional[str]:
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT raw_content FROM context_blobs WHERE ref_id = ?", (ref_id,)
            ).fetchone()
        if row:
            return row["raw_content"]
    except Exception:
        pass
    return None


# =====================================================================
# 4. 3-REGION PREFIX ALIGNER
# =====================================================================
def align_prefix_3_region(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Sort tools deterministically, register expand tool, stamp cache marker on
    the last immutable-prefix block. Deterministic for byte-identical cache."""
    system_prompts = payload.get("system", [])
    tools = list(payload.get("tools", []))
    messages = payload.get("messages", [])

    names = [t.get("name") for t in tools if isinstance(t, dict)]
    if "csmart_expand_symbol" not in names:
        tools.append(EXPAND_TOOL_SCHEMA)
    tools = sorted(tools, key=lambda t: t.get("name", ""))

    if tools:
        for t in tools:
            if isinstance(t, dict):
                t.pop("cache_control", None)
        if isinstance(tools[-1], dict):
            tools[-1]["cache_control"] = {"type": "ephemeral"}
    elif isinstance(system_prompts, list) and system_prompts:
        for s in system_prompts:
            if isinstance(s, dict):
                s.pop("cache_control", None)
        if isinstance(system_prompts[-1], dict):
            system_prompts[-1]["cache_control"] = {"type": "ephemeral"}

    payload["system"] = system_prompts
    payload["tools"] = tools
    payload["messages"] = messages
    return payload


# =====================================================================
# 5. HEURISTIC MODEL ROUTER (Flash vs Flagship, pinned per session)
# =====================================================================
_session_model: Dict[str, Tuple[str, float]] = {}


def _extract_last_text(payload: Dict[str, Any]) -> str:
    messages = payload.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content", "")
    if isinstance(content, str):
        return content
    parts: List[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in ("text", "input_text") and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif block.get("type") == "tool_result":
                c = block.get("content")
                if isinstance(c, str):
                    parts.append(c)
    return "\n".join(parts)


def route_model_tier(payload: Dict[str, Any], session_key: str) -> str:
    """Pick a model for this request. Pinned per session (cache stability)."""
    now = time.time()
    cached = _session_model.get(session_key)
    if cached and now - cached[1] < 3600:
        return cached[0]
    text = _extract_last_text(payload).lower()
    model = FLAGSHIP_MODEL if any(t in text for t in _COMPLEX_TRIGGERS) else FLASH_MODEL
    _session_model[session_key] = (model, now)
    return model


# =====================================================================
# 5.1 OPENAI NATIVE MODEL SUPPORT — Protocol Transformation
# =====================================================================


def is_openai_model(model_name: str) -> bool:
    """Detect if model is OpenAI-native (requires protocol transformation)."""
    lower_name = model_name.lower()
    return any(pattern.lower() in lower_name for pattern in OPENAI_MODEL_PATTERNS)


def detect_openai_endpoint_type(model_name: str) -> str:
    """Detect which OpenAI endpoint to use (chat_completions or responses)."""
    lower_name = model_name.lower()
    if "response" in lower_name or "responses" in lower_name:
        return "responses"
    # Default to chat completions for most OpenAI models
    return "chat_completions"


def _extract_system_text(system: Any) -> str:
    """Extract concatenated system text from Anthropic system format (str or list)."""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return " ".join(
            block.get("text", "") for block in system if isinstance(block, dict)
        )
    return str(system)


def _convert_anthropic_tool_to_openai(anthropic_tool: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Anthropic tool format (input_schema) → OpenAI tool format (parameters)."""
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool.get("description", ""),
            "parameters": anthropic_tool.get("input_schema", {}),
        },
    }


def _convert_anthropic_message_to_openai(anth_msg: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Anthropic message format → OpenAI Chat Completions message."""
    role = anth_msg.get("role", "user")
    content = anth_msg.get("content", "")

    # Anthropic content is either str or list[blocks]
    if isinstance(content, str):
        text_content = content
    elif isinstance(content, list):
        # Concatenate all text blocks (ignore non-text for now)
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    text_parts.append(block["text"])
        text_content = "".join(text_parts)
    else:
        text_content = str(content)

    return {"role": role, "content": text_content}


def transform_anthropic_to_openai_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transform Anthropic Messages API payload → OpenAI Chat Completions API payload."""
    # Extract system prompt
    system_text = _extract_system_text(payload.get("system", ""))

    # Convert all messages
    messages: List[Dict[str, Any]] = []

    # Add system message first if non-empty
    if system_text.strip():
        messages.append({"role": "system", "content": system_text})

    # Add conversation messages
    for anth_msg in payload.get("messages", []):
        if isinstance(anth_msg, dict):
            messages.append(_convert_anthropic_message_to_openai(anth_msg))

    # Build OpenAI payload
    openai_payload: Dict[str, Any] = {
        "model": payload.get("model"),
        "messages": messages,
        "stream": True,
    }

    # Copy optional parameters if present
    if "max_tokens" in payload:
        openai_payload["max_tokens"] = payload["max_tokens"]
    if "temperature" in payload:
        openai_payload["temperature"] = payload["temperature"]
    if "top_p" in payload:
        openai_payload["top_p"] = payload["top_p"]

    # Convert tools if present
    anthropic_tools = payload.get("tools", [])
    if anthropic_tools:
        openai_tools = [
            _convert_anthropic_tool_to_openai(tool) for tool in anthropic_tools
        ]
        openai_payload["tools"] = openai_tools
        # Enable parallel tool calls by default (Anthropic-like behavior)
        openai_payload["parallel_tool_calls"] = True

    return openai_payload


def transform_anthropic_to_openai_responses(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transform Anthropic Messages API payload → OpenAI Responses API payload (stub).

    Can be extended later if Responses API support is needed.
    """
    # For now, stub implementation — most OpenAI-native models use chat/completions
    # This can be completed when needed for specific providers
    system_text = _extract_system_text(payload.get("system", ""))
    openai_payload: Dict[str, Any] = {
        "model": payload.get("model"),
        "instructions": system_text,
        "input": payload.get("messages", []),
        "stream": True,
    }
    if "max_tokens" in payload:
        openai_payload["max_output_tokens"] = payload["max_tokens"]
    return openai_payload


async def transform_openai_sse_to_anthropic(
    sse_events: AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None],
) -> AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None]:
    """Transform OpenAI Chat Completions SSE stream → Anthropic Messages SSE stream.

    OpenAI: data: {"choices": [{"delta": {"content": "..."}}]}
    Anthropic: event: content_block_delta\ndata: {"type": "content_block_delta", "delta": {"text": "..."}}\n\n
    """
    # Track if we've sent message_start yet
    sent_message_start = False
    # Accumulate tool call JSON for streaming
    tool_call_index = 0

    async for _, openai_event in sse_events:
        # OpenAI sends [DONE] at end of stream (marked as sentinel dict)
        if openai_event.get("__openai_done"):
            yield "message_stop", {"type": "message_stop"}
            break

        choices = openai_event.get("choices", [])
        if not choices:
            continue

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        # Send message_start on first chunk
        if not sent_message_start:
            yield "message_start", {
                "type": "message_start",
                "message": {
                    "role": "assistant",
                    "content": [],
                },
            }
            sent_message_start = True

        # Handle text content delta
        if "content" in delta and delta["content"] is not None:
            text = delta["content"]
            if text:
                yield "content_block_delta", {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text", "text": text},
                }

        # Handle tool call delta (streaming tool calls)
        if "tool_calls" in delta and delta["tool_calls"] is not None:
            for tool_call_delta in delta["tool_calls"]:
                # OpenAI streams tool_calls[].function.arguments incrementally
                if "function" in tool_call_delta and "arguments" in tool_call_delta["function"]:
                    args = tool_call_delta["function"]["arguments"]
                    if args:
                        yield "content_block_delta", {
                            "type": "content_block_delta",
                            "index": 1 + tool_call_index,
                            "delta": {
                                "type": "input_json",
                                "partial_json": args,
                            },
                        }
                if "name" in tool_call_delta:
                    # New tool call starts here — increment index
                    tool_call_index += 1

        # End of stream
        if finish_reason is not None:
            yield "message_stop", {"type": "message_stop"}
            break


# =====================================================================
# 6. STREAMING REDACTOR (split-marker-safe unmask)
# =====================================================================
_MARKER_RE = re.compile(r"__CSMART_SEC_[0-9a-f]{8}__")
_REDACTOR_TAIL = 64


class StreamingRedactor:
    """Unmask markers on the client-bound path without splitting them at chunk
    boundaries. A split marker stays masked (errs safe), never leaks a secret."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        combined = self._buf + chunk
        cut = max(0, len(combined) - _REDACTOR_TAIL)
        emit = combined[:cut]
        rest = combined[cut:]
        start = emit.rfind("__CSMART_SEC_")
        if start != -1 and not _MARKER_RE.search(emit[start:]):
            emit, rest = emit[:start], emit[start:] + rest
        self._buf = rest
        return vault.unmask_text(emit)

    def flush(self) -> str:
        out, self._buf = self._buf, ""
        return vault.unmask_text(out)


# =====================================================================
# 7. SSE SOURCE + SHADOW-STREAMER (expand + guardrail interception)
# =====================================================================
def _parse_sse_data(data_lines: List[str]) -> Dict[str, Any]:
    raw = "\n".join(data_lines)
    raw_stripped = raw.strip()
    # Special case for OpenAI end-of-stream marker
    if raw_stripped == "[DONE]":
        # Use a sentinel dict that transform_openai_sse_to_anthropic recognizes
        return {"__openai_done": True}
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {"type": "error", "error": {"type": "invalid_payload", "message": raw[:200]}}


async def _iter_sse_events(
    resp: httpx.Response,
) -> AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None]:
    data_lines: List[str] = []
    event_name: Optional[str] = None
    async for raw_line in resp.aiter_lines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                yield event_name, _parse_sse_data(data_lines)
                data_lines = []
                event_name = None
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if data_lines:
        yield event_name, _parse_sse_data(data_lines)


# Test seam (hermetic): inject ``httpx.MockTransport`` via this attr — pola yang
# sama dengan ``router/dispatcher._UPSTREAM_TRANSPORT``. ``None`` = jaringan asli.
_UPSTREAM_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


async def _sse_source(
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None]:
    """Open the upstream stream, canonical-serialize the body, yield SSE events."""
    payload_bytes = json.dumps(body, sort_keys=True).encode("utf-8")
    async with httpx.AsyncClient(transport=_UPSTREAM_TRANSPORT, timeout=UPSTREAM_TIMEOUT) as client:
        async with client.stream(method, url, headers=headers, content=payload_bytes) as resp:
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode("utf-8", errors="replace")[:400]
                yield "error", {
                    "type": "error",
                    "error": {"type": "upstream_error", "status_code": resp.status_code, "message": err_body},
                }
                return
            async for event_name, payload in _iter_sse_events(resp):
                yield event_name, payload


def _format_event(event_name: Optional[str], payload: Dict[str, Any]) -> bytes:
    etype = str(payload.get("type") or event_name or "message")
    return f"event: {etype}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


class ProxyStreamer:
    """Stream upstream SSE to the client, shadowing tool_use locally:
    - ``csmart_expand_symbol`` -> expand from CCR (reversible compression).
    - guardrail violation      -> blocked result (secrets never reach client/upstream).
    Other tool_use streams through unchanged (client executes it)."""

    def __init__(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        self.round = 1
        self.client_index = 0
        self._pending_held: List[Dict[str, Any]] = []

    async def run(self) -> AsyncGenerator[bytes, None]:
        for _ in range(MAX_ROUNDS):
            messages = self.body.get("messages", [])
            self._pending_held = []
            async for chunk in self._stream_round(messages):
                yield chunk
            held = self._pending_held
            if not held:
                return
            self.body = {**self.body, "messages": self._build_followup(messages, held)}
        yield _format_event(
            "error",
            {"type": "error", "error": {"type": "max_shadow_rounds", "message": "csmart: too many shadow rounds"}},
        )

    async def _stream_round(
        self, messages: List[Dict[str, Any]]
    ) -> AsyncGenerator[bytes, None]:
        held_indices: set[int] = set()
        held_by_index: Dict[int, Dict[str, Any]] = {}
        pending: Dict[int, List[Tuple[Optional[str], Dict[str, Any]]]] = {}
        client_index_map: Dict[int, int] = {}
        buffered_end: List[Tuple[Optional[str], Dict[str, Any]]] = []

        async for event_name, payload in _sse_source(
            self.method, self.url, self.headers, {**self.body, "messages": messages}
        ):
            etype = payload.get("type", "")

            if etype == "message_start":
                if self.round == 1:
                    yield _format_event(event_name, payload)
                continue

            if etype in ("message_delta", "message_stop"):
                buffered_end.append((event_name, payload))
                continue

            if etype == "content_block_start":
                index = payload.get("index")
                if not isinstance(index, int):
                    yield _format_event(event_name, payload)
                    continue
                cb = payload.get("content_block", {})
                if isinstance(cb, dict) and cb.get("type") == "tool_use":
                    pending[index] = [(event_name, payload)]
                    held_by_index[index] = {
                        "index": index,
                        "id": cb.get("id"),
                        "name": cb.get("name", ""),
                        "input_parts": [],
                    }
                    base_input = cb.get("input")
                    if isinstance(base_input, dict) and base_input:
                        held_by_index[index]["input_parts"].append(json.dumps(base_input))
                    continue
                new_index = self.client_index
                self.client_index += 1
                client_index_map[index] = new_index
                p = dict(payload)
                p["index"] = new_index
                yield _format_event(event_name, p)
                continue

            if etype == "content_block_delta":
                index = payload.get("index")
                if not isinstance(index, int):
                    yield _format_event(event_name, payload)
                    continue
                if index in pending:
                    pending[index].append((event_name, payload))
                    delta = payload.get("delta", {})
                    if isinstance(delta, dict) and isinstance(delta.get("partial_json"), str):
                        held_by_index[index]["input_parts"].append(delta["partial_json"])
                    continue
                new_index = client_index_map.get(index)
                if new_index is None:
                    continue
                p = dict(payload)
                p["index"] = new_index
                yield _format_event(event_name, p)
                continue

            if etype == "content_block_stop":
                index = payload.get("index")
                if not isinstance(index, int):
                    yield _format_event(event_name, payload)
                    continue
                if index in pending:
                    pending[index].append((event_name, payload))
                    info = held_by_index[index]
                    tool_input = self._join_input(info["input_parts"])
                    err = check_security_guardrails(info["name"], tool_input)
                    if info["name"] == "csmart_expand_symbol" or err:
                        if err:
                            info["blocked_reason"] = err
                        held_indices.add(index)
                        continue
                    # Normal tool_use -> replay buffered block to the client.
                    new_index = self.client_index
                    self.client_index += 1
                    client_index_map[index] = new_index
                    for en, pl in pending[index]:
                        p = dict(pl)
                        p["index"] = new_index
                        yield _format_event(en, p)
                    continue
                new_index = client_index_map.get(index)
                if new_index is None:
                    continue
                p = dict(payload)
                p["index"] = new_index
                yield _format_event(event_name, p)
                continue

            if etype == "ping":
                yield _format_event(event_name, payload)
                continue

            if etype == "error":
                yield _format_event(event_name, payload)
                return

            yield _format_event(event_name, payload)

        self.round += 1

        if held_indices:
            # Expand/guardrail resolution is synchronous (SQLite read + dict
            # build) — no gather needed.
            self._pending_held = [
                self._execute_held(held_by_index[i]) for i in sorted(held_indices)
            ]
            return

        for event_name, payload in buffered_end:
            yield _format_event(event_name, payload)

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _join_input(parts: List[str]) -> Dict[str, Any]:
        raw = "".join(parts)
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"_partial_json": raw}

    @staticmethod
    def _execute_held(block: Dict[str, Any]) -> Dict[str, Any]:
        tool_input = ProxyStreamer._join_input(block["input_parts"])
        if block.get("blocked_reason"):
            return {
                **block,
                "input": tool_input,
                "content": (
                    f"[CSMART SECURITY BLOCKED] {block['blocked_reason']}. "
                    "Eksekusi dicegat oleh proxy — jangan ulangi; gunakan tool lain."
                ),
            }
        if block["name"] == "csmart_expand_symbol":
            ref_id = (tool_input or {}).get("ref_id")
            if not ref_id:
                return {
                    **block,
                    "input": tool_input,
                    "content": "ERROR: csmart_expand_symbol memerlukan argumen string 'ref_id'.",
                }
            content = get_ccr_payload(str(ref_id))
            if content is None:
                return {
                    **block,
                    "input": tool_input,
                    "content": f"ERROR: ref_id {ref_id!r} tidak ditemukan di context store.",
                }
            return {**block, "input": tool_input, "content": content}
        return {**block, "input": tool_input, "content": ""}

    def _build_followup(
        self, messages: List[Dict[str, Any]], held: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        assistant_content: List[Dict[str, Any]] = []
        user_results: List[Dict[str, Any]] = []
        for block in held:
            assistant_content.append(
                {"type": "tool_use", "id": block["id"], "name": block["name"], "input": block.get("input", {})}
            )
            user_results.append(
                {"type": "tool_result", "tool_use_id": block["id"], "content": block.get("content", "")}
            )
        followup = list(messages)
        if assistant_content:
            followup.append({"role": "assistant", "content": assistant_content})
        followup.append({"role": "user", "content": user_results})
        return followup


# =====================================================================
# 8. BACKGROUND KEEPALIVE (jaga KV-cache TTL provider)
# =====================================================================
last_request_timestamp: float = time.time()
last_keepalive_ok: float = time.monotonic()
_prefix_snapshot: Optional[Dict[str, Any]] = None
_active_model: str = FLASH_MODEL


async def keepalive_worker() -> None:
    global last_request_timestamp, last_keepalive_ok
    while True:
        await asyncio.sleep(KEEPALIVE_TICK)
        elapsed = time.time() - last_request_timestamp
        if not (KEEPALIVE_WINDOW_START <= elapsed < KEEPALIVE_WINDOW_END):
            continue
        if not _prefix_snapshot or not UPSTREAM_API_KEY:
            continue
        now_mono = time.monotonic()
        if now_mono - last_keepalive_ok < 45:  # jangan spam saat retry
            continue
        payload: Dict[str, Any] = {
            "model": _active_model,
            "max_tokens": 1,
            "system": _prefix_snapshot.get("system", []),
            "tools": _prefix_snapshot.get("tools", []),
            "messages": [{"role": "user", "content": "ping"}],
        }
        headers = {
            "Authorization": f"Bearer {UPSTREAM_API_KEY}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(transport=_UPSTREAM_TRANSPORT, timeout=10.0) as client:
                resp = await client.post(
                    f"{UPSTREAM_BASE_URL}/v1/messages",
                    headers=headers,
                    content=json.dumps(payload, sort_keys=True).encode("utf-8"),
                )
            if resp.status_code < 400:
                last_request_timestamp = time.time()
                last_keepalive_ok = time.monotonic()
                _log("KEEPALIVE_PING", status_code=resp.status_code, model=_active_model)
        except Exception:
            pass


# =====================================================================
# 9. FASTAPI APP & ROUTES
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _log("SERVER_START", app_title=app.title)
    keepalive_task = asyncio.create_task(keepalive_worker())
    yield
    keepalive_task.cancel()


app = FastAPI(title="csmart Local Context Optimizer", lifespan=lifespan)


def _upstream_headers(request: Request) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {UPSTREAM_API_KEY}",
        "Content-Type": "application/json",
        "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
    }


@app.post("/v1/messages")
async def handle_messages(request: Request) -> StreamingResponse:
    global last_request_timestamp, _prefix_snapshot, _active_model
    last_request_timestamp = time.time()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    session_key = request.headers.get("x-csmart-session") or "default"
    if not UPSTREAM_API_KEY:
        _log("UPSTREAM_KEY_MISSING", warning=True)

    body = clamp_max_tokens(body)
    sanitize_payload(body)

    # -------------------------------------------------------------------------
    # Step 1: Detect OpenAI models BEFORE model tier routing overrides name
    # OpenAI detection is based on original model name from client request
    # -------------------------------------------------------------------------
    original_model = body.get("model", "")
    is_openai = is_openai_model(original_model)
    endpoint_type = detect_openai_endpoint_type(original_model) if is_openai else "anthropic"

    # -------------------------------------------------------------------------
    # Step 2: Heuristic model tier routing (flash vs flagship)
    # -------------------------------------------------------------------------
    routed_model = route_model_tier(body, session_key)
    _active_model = routed_model
    body["model"] = routed_model

    # -------------------------------------------------------------------------
    # Step 3: System Prompt Steering for OpenAI-native models
    # Inject before 3-region alignment so steering is part of the immutable prefix
    # -------------------------------------------------------------------------
    if is_openai:
        # Inject steering prompt into system (based on original detection)
        steering_block = {"type": "text", "text": SYSTEM_STEERING_PROMPT}
        current_system = body.get("system", "")
        if isinstance(current_system, str):
            # Convert string to list format and append
            if current_system.strip():
                body["system"] = [
                    {"type": "text", "text": current_system},
                    steering_block,
                ]
            else:
                body["system"] = [steering_block]
        elif isinstance(current_system, list):
            # Already list format, append
            body["system"] = current_system + [steering_block]
        else:
            # Fallback: convert to string and append
            body["system"] = f"{_extract_system_text(current_system)}\n\n{SYSTEM_STEERING_PROMPT}"

    # -------------------------------------------------------------------------
    # 3-region prefix alignment (includes steering now for cache stability)
    # -------------------------------------------------------------------------
    body = align_prefix_3_region(body)
    _prefix_snapshot = {"system": body.get("system", []), "tools": body.get("tools", [])}

    _log("INBOUND_REQUEST", model=routed_model, session=session_key, messages=len(body.get("messages", [])))

    if is_openai:
        # OpenAI endpoints don't need anthropic-version header
        headers = {
            "Authorization": f"Bearer {UPSTREAM_API_KEY}",
            "Content-Type": "application/json",
        }
        # Select endpoint and transform request
        if endpoint_type == "chat_completions":
            upstream_url = f"{OPENAI_BASE_URL}{OPENAI_CHAT_COMPLETIONS_PATH}"
            transformed_body = transform_anthropic_to_openai_chat(body)
        elif endpoint_type == "responses":
            upstream_url = f"{OPENAI_BASE_URL}{OPENAI_RESPONSES_PATH}"
            transformed_body = transform_anthropic_to_openai_responses(body)
        else:
            upstream_url = f"{OPENAI_BASE_URL}{OPENAI_CHAT_COMPLETIONS_PATH}"
            transformed_body = transform_anthropic_to_openai_chat(body)
    else:
        # Anthropic native endpoint includes anthropic-version header
        headers = _upstream_headers(request)
        upstream_url = f"{UPSTREAM_BASE_URL}/v1/messages"
        transformed_body = body

    # -------------------------------------------------------------------------
    # Step 3: Response transformation (OpenAI -> Anthropic format)
    # -------------------------------------------------------------------------
    async def generator() -> AsyncGenerator[bytes, None]:
        redactor = StreamingRedactor()

        if is_openai and endpoint_type == "chat_completions":
            # For OpenAI chat completions: we need to transform SSE format
            async for _event_name, anthropic_event in transform_openai_sse_to_anthropic(
                _sse_source("POST", upstream_url, headers, transformed_body)
            ):
                event_bytes = _format_event(_event_name, anthropic_event)
                out = redactor.feed(event_bytes.decode("utf-8", errors="replace"))
                if out:
                    yield out.encode("utf-8")
            final = redactor.flush()
            if final:
                yield final.encode("utf-8")
        else:
            # Anthropic native (or OpenAI responses with future support):
            # use existing ProxyStreamer which handles CCR/shadowing
            streamer = ProxyStreamer("POST", upstream_url, headers, transformed_body)
            async for chunk in streamer.run():
                out = redactor.feed(chunk.decode("utf-8", errors="replace"))
                if out:
                    yield out.encode("utf-8")
            final = redactor.flush()
            if final:
                yield final.encode("utf-8")

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_PASSTHROUGH_HEADERS = {"anthropic-version"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def passthrough(request: Request, path: str) -> StreamingResponse:
    """Forward non-messages endpoints (e.g. GET /v1/models, /v1/messages/count_tokens)."""
    target = f"{UPSTREAM_BASE_URL}/{path}"
    body_bytes = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
    headers: Dict[str, str] = {"Authorization": f"Bearer {UPSTREAM_API_KEY}"}
    for name, val in request.headers.items():
        if name.lower() in _PASSTHROUGH_HEADERS:
            headers[name.lower()] = val
    if body_bytes:
        headers.setdefault("Content-Type", "application/json")

    async def proxy_gen() -> AsyncGenerator[bytes, None]:
        async with httpx.AsyncClient(transport=_UPSTREAM_TRANSPORT, timeout=UPSTREAM_TIMEOUT) as client:
            req = client.build_request(request.method, target, headers=headers, content=body_bytes)
            resp = await client.send(req, stream=True)
            async for chunk in resp.aiter_bytes():
                yield chunk

    return StreamingResponse(proxy_gen(), media_type="application/json")


if __name__ == "__main__":
    import uvicorn

    _banner()
    uvicorn.run(app, host=PROXY_HOST, port=PROXY_PORT, log_level="warning")
