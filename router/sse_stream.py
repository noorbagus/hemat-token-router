"""SSE (Server-Sent Events) line parsing for the csmart proxy (N-3).

Pure parsing: turns an httpx streaming response into ``(event_name, payload)``
tuples. No proxy/shadow logic lives here — extracted from
``router/dispatcher.py`` so the shadow loop can iterate a clean SSE source.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx


def _parse_sse_data(data_lines: List[str]) -> Dict[str, Any]:
    """Join ``data:`` lines and JSON-decode them into a payload dict."""
    raw = "\n".join(data_lines)
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
        return {
            "type": "error",
            "error": {"type": "invalid_payload", "message": raw[:200]},
        }
    except json.JSONDecodeError:
        return {
            "type": "error",
            "error": {"type": "invalid_json", "message": raw[:200]},
        }


async def _iter_sse_events(
    resp: httpx.Response,
) -> AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None]:
    """Parse an httpx streaming response into ``(event_name, payload)`` tuples."""
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
