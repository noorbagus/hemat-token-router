"""StructuredLogger for csmart — non-blocking, thread-safe JSONL audit logging.

Contract: CONTRACTS.md §2 (Track D). Wave 2 consumes the module singleton via
``from router.logger import logger``.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

# --- Event constants (exact strings — used by Wave 2 + tests) ---
INBOUND_REQUEST = "INBOUND_REQUEST"
AST_SCANNED = "AST_SCANNED"
OLLAMA_TRIAGE = "OLLAMA_TRIAGE"
TOOL_SHADOW_INTERCEPT = "TOOL_SHADOW_INTERCEPT"
TOOL_LOCAL_EXEC = "TOOL_LOCAL_EXEC"
SSE_STREAM_COMPLETE = "SSE_STREAM_COMPLETE"

# Field keys (case-insensitive) whose values are redacted before logging.
_SENSITIVE_KEYS = frozenset({"authorization", "api_key", "x-api-key", "token"})

_QUEUE_MAXSIZE = 1000
_DROP_EVENT = "LOGGER_DROPPED"
_DROP_LOCK_TIMEOUT = 0.05  # seconds — bounded wait so log() never blocks indefinitely


class StructuredLogger:
    """Non-blocking structured logger backed by a bounded queue + one daemon writer thread.

    - ``log()`` enqueues a record via ``put_nowait`` and never blocks the caller.
    - Records are written as JSONL lines to ``<log_dir>/session_<local-date>.jsonl``.
    - Sensitive field values (``authorization``/``api_key``/``x-api-key``/``token``,
      case-insensitive) are replaced with ``[REDACTED]``.
    - ``close()`` drains the queue, stops the writer thread, and closes the file.
    """

    def __init__(self, log_dir: str | Path | None = None) -> None:
        if log_dir is None:
            self._log_dir: Path = Path.home() / ".csmart" / "logs"
        else:
            self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path: Path = self._log_dir / f"session_{datetime.now().date().isoformat()}.jsonl"

        self._queue: queue.Queue[dict[str, object] | None] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._file: TextIO = self._log_path.open("a", encoding="utf-8")
        self._file_lock = threading.Lock()
        self._trace_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._trace_id: str | None = None
        self._closed: bool = False

        self._writer = threading.Thread(
            target=self._writer_loop, name="csmart-logger", daemon=True
        )
        self._writer.start()

    # --- public API -------------------------------------------------

    def log(self, event: str, **fields: object) -> None:
        """Enqueue a record asynchronously. Never blocks the caller."""
        record: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": self._get_trace_id(),
            "event": event,
        }
        for key, value in fields.items():
            if key.lower() in _SENSITIVE_KEYS:
                record[key] = self.redact(str(value))
            else:
                record[key] = self._json_safe(value)
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self._write_drop_line()

    def set_trace_id(self, trace_id: str) -> None:
        """Store the per-turn trace id stamped onto subsequent records."""
        with self._trace_lock:
            self._trace_id = trace_id

    def redact(self, value: str) -> str:
        """Mask a sensitive value. Always returns the fixed placeholder."""
        return "[REDACTED]"

    def flush(self) -> None:
        """Block until all pending records have been written to disk."""
        self._queue.join()

    def close(self) -> None:
        """Flush, stop the writer thread, and close the log file. Idempotent."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._queue.put(None, timeout=5.0)  # sentinel → writer thread exits
        except queue.Full:
            pass
        self._queue.join()
        if self._writer.is_alive():
            self._writer.join(timeout=5.0)
        with self._file_lock:
            if not self._file.closed:
                self._file.close()

    # --- internals --------------------------------------------------

    def _writer_loop(self) -> None:
        while True:
            record = self._queue.get()
            try:
                if record is None:
                    break
                self._write_line(record)
            except Exception:
                # Never let the writer thread die; a broken record must not stop logging.
                print("csmart-logger: failed to write log record", file=sys.stderr)
            finally:
                self._queue.task_done()

    def _write_line(self, record: dict[str, object], *, timeout: float | None = None) -> bool:
        """Serialize one record as a JSONL line. False if the lock could not be acquired."""
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if timeout is None:
            acquired = self._file_lock.acquire()
        else:
            acquired = self._file_lock.acquire(timeout=timeout)
        if not acquired:
            return False
        try:
            if self._file.closed:
                return False
            self._file.write(line + "\n")
            self._file.flush()
            return True
        finally:
            self._file_lock.release()

    def _write_drop_line(self) -> None:
        record: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": self._get_trace_id(),
            "event": _DROP_EVENT,
        }
        try:
            if not self._write_line(record, timeout=_DROP_LOCK_TIMEOUT):
                print("csmart-logger: queue full, dropped record", file=sys.stderr)
        except Exception:
            print("csmart-logger: queue full, dropped record", file=sys.stderr)

    def _get_trace_id(self) -> str | None:
        with self._trace_lock:
            return self._trace_id

    @staticmethod
    def _json_safe(value: object) -> object:
        """Coerce non-JSON-serializable values to str so the writer never chokes."""
        if value is None or isinstance(value, (str, int, float, bool, list, dict)):
            return value
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)


# Module singleton — Wave 2 consumes it via `from router.logger import logger`.
logger = StructuredLogger()
