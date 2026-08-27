"""Read-only viewer for csmart JSONL audit logs (no new third-party deps).

Consumes the record shape produced by ``router.logger``: one JSON object per
line with ``ts`` (ISO-8601 UTC), ``trace_id``, ``event``, plus arbitrary extra
fields. Files are ``<log_dir>/session_<local-date>.jsonl``.

This module has NO import-time side effects (no ``mkdir`` at module level) so
tests can import it hermetically.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from router.report import StatsSummary, aggregate_reports

#: Default log directory, overridable via ``CSMART_LOG_DIR``.
DEFAULT_LOG_DIR = os.environ.get("CSMART_LOG_DIR") or str(Path.home() / ".csmart" / "logs")


def _parse_line(line: str) -> dict | None:
    """Parse one JSONL line. Returns ``None`` for empty/malformed lines."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def read_log_records(
    log_dir: str, tail: int = 20, event: str | None = None
) -> list[dict]:
    """Read structured log records across all ``session_*.jsonl`` files.

    Files are combined in sorted-by-path order, then file order. Malformed
    lines are skipped. When ``event`` is given, only records whose ``event``
    field matches exactly are kept. Returns the last ``tail`` records
    (``tail <= 0`` means all records). Missing/unreadable log dir -> ``[]``.
    """
    records: list[dict] = []
    try:
        paths = sorted(Path(log_dir).glob("session_*.jsonl"))
    except OSError:
        return []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    rec = _parse_line(line)
                    if rec is None:
                        continue
                    if event is None or rec.get("event") == event:
                        records.append(rec)
        except OSError:
            continue
    if tail > 0:
        records = records[-tail:]
    return records


def render_records(records: list[dict]) -> str:
    """Render records as deterministic plain text, one per line.

    Each line is ``[<ts>] <EVENT>`` followed by every remaining field
    (everything except ``ts``/``event``) as `` key=value`` in record insertion
    order. ``None`` values are skipped. Output ends with a trailing newline.
    """
    lines: list[str] = []
    for rec in records:
        ts = rec.get("ts")
        event = rec.get("event")
        parts: list[str] = []
        for key, value in rec.items():
            if key in ("ts", "event") or value is None:
                continue
            parts.append(f"{key}={value}")
        suffix = " " + " ".join(parts) if parts else ""
        lines.append(f"[{ts}] {event}{suffix}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _read_new_records(
    log_dir: str, offsets: dict[str, int], event: str | None
) -> Iterator[dict]:
    """Yield records appended after the tracked byte offset per file.

    Newly created ``session_*.jsonl`` files are picked up on every poll (they
    default to offset 0). A trailing partial line (no newline yet, i.e. a
    record still being written) is left unread for the next poll.
    """
    try:
        paths = sorted(Path(log_dir).glob("session_*.jsonl"))
    except OSError:
        return
    for path in paths:
        key = str(path)
        offset = offsets.get(key, 0)
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(offset)
                while True:
                    line = f.readline()
                    if not line:
                        break
                    if not line.endswith("\n"):
                        # Partial line still being written — don't consume it.
                        f.seek(offset)
                        break
                    offsets[key] = f.tell()
                    rec = _parse_line(line)
                    if rec is None:
                        continue
                    if event is None or rec.get("event") == event:
                        yield rec
        except OSError:
            continue


def _file_eof_offsets(log_dir: str) -> dict[str, int]:
    """Record the current byte size of every session log file."""
    offsets: dict[str, int] = {}
    try:
        paths = sorted(Path(log_dir).glob("session_*.jsonl"))
    except OSError:
        return offsets
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                offsets[str(path)] = f.tell()
        except OSError:
            continue
    return offsets


def follow_log(
    log_dir: str,
    event: str | None = None,
    poll_interval: float = 0.5,
    tail: int = 0,
) -> Iterator[dict]:
    """Yield the last ``tail`` records (all when ``tail <= 0``), then poll for appends.

    With ``tail <= 0`` the initial dump and the offset bookkeeping share a
    single pass over the files, so a record appended mid-dump is never emitted
    twice. With ``tail > 0`` the initial dump is the last ``tail`` records and
    polling resumes at the files' current end. ``KeyboardInterrupt`` stops the
    poll loop cleanly.
    """
    if tail > 0:
        for rec in read_log_records(log_dir, tail=tail, event=event):
            yield rec
        offsets = _file_eof_offsets(log_dir)
    else:
        offsets = {}
        for rec in _read_new_records(log_dir, offsets, event):
            yield rec

    try:
        while True:
            time.sleep(poll_interval)
            for rec in _read_new_records(log_dir, offsets, event):
                yield rec
    except KeyboardInterrupt:
        return


def cmd_logs(
    log_dir: str, tail: int = 20, follow: bool = False, event: str | None = None
) -> None:
    """Print log records. Missing log dir -> short stderr message, no crash."""
    if not log_dir or not os.path.isdir(log_dir):
        print(f"csmart logs: log directory not found: {log_dir}", file=sys.stderr)
        return
    if follow:
        for rec in follow_log(log_dir, event=event, tail=tail):
            print(render_records([rec]), end="", flush=True)
    else:
        records = read_log_records(log_dir, tail=tail, event=event)
        print(render_records(records), end="", flush=True)


def _count_events(records: list[dict]) -> dict[str, int]:
    """Count occurrences of each ``event`` value (sorted by key)."""
    counts: dict[str, int] = {}
    for rec in records:
        event = rec.get("event")
        if event is not None:
            counts[event] = counts.get(event, 0) + 1
    return dict(sorted(counts.items()))


def _format_stats_table(summary: StatsSummary, event_counts: dict[str, int]) -> str:
    """Build the deterministic human-readable stats table."""
    status_str = ", ".join(f"{k}: {v}" for k, v in sorted(summary.status_counts.items()))
    reports_val = f"{summary.report_count}"
    if status_str:
        reports_val += f"  ({status_str})"
    avg_val = "-" if summary.avg_prepass_ms is None else f"{summary.avg_prepass_ms:g} ms"
    events_val = ", ".join(f"{k}={v}" for k, v in event_counts.items())
    lines = [
        "csmart stats",
        f"  reports:          {reports_val}",
        f"  avg prepass:      {avg_val}",
        f"  total injected:   {summary.total_injected_bytes} bytes",
        f"  tokens saved:     {summary.total_tokens_saved}",
        f"  events:           {events_val}",
    ]
    return "\n".join(lines) + "\n"


def cmd_stats(log_dir: str, report_dir: str = ".csmart", json_out: bool = False) -> None:
    """Aggregate report statistics and per-event log counts.

    Discovers ``*.json`` reports in ``report_dir`` (top-level only) and
    aggregates them via ``router.report.aggregate_reports``. Event counts come
    from all log records in ``log_dir``. With ``json_out``, prints a single
    JSON object (StatsSummary + ``event_counts``); otherwise prints a table.
    """
    report_paths = sorted(str(p) for p in Path(report_dir).glob("*.json"))
    summary = aggregate_reports(report_paths)
    event_counts = _count_events(read_log_records(log_dir, tail=0))

    if json_out:
        payload = dict(summary.model_dump())
        payload["event_counts"] = event_counts
        print(json.dumps(payload))
        return

    print(_format_stats_table(summary, event_counts), end="")
