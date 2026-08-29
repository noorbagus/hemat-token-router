"""Shadow loop (N-4 / QG-03 / QG-04): drives the outbound SSE stream with
exploration tool-use shadowing.

Extracted from ``router/dispatcher.py`` so the loop is decoupled from the proxy
engine's transport/transport-hook globals. The upstream HTTP request + SSE
parsing are injected as a **SSE source** (``sse_source``), and the "is this
tool_use shadowable?" decision is injected as a **decision callback**
(``should_shadow``). The loop itself owns only the shadow/re-submit state
machine.

Behavior / event flow is frozen (CONTRACTS.md §2/§5): the source emits the same
SSE error payloads (``api_error`` / ``upstream_error``) that the old inline
request handling produced, and the loop forwards/holds tool_use blocks
identically.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from router.logger import (
    SSE_STREAM_COMPLETE,
    TOOL_SHADOW_INTERCEPT,
    logger,
)
from router.tool_shadow import execute_local_tool, summarize_exploration

# Async generator of ``(event_name, payload)`` SSE events produced from an
# upstream request. The concrete source (dispatcher's ``_sse_source``) owns the
# HTTP client, status>=400 handling and mid-stream transport error mapping.
SseSource = Callable[
    [str, str, Dict[str, str], Dict[str, Any]],
    AsyncGenerator[Tuple[Optional[str], Dict[str, Any]], None],
]
# Decision callback: ``(tool_name, shadow_used) -> hold?``. Injected so the loop
# does not import tool_shadow's name registry nor the shadow-round bound.
ShouldShadow = Callable[[str, int], bool]


class ShadowStreamer:
    """Drives the outbound SSE stream with exploration tool-use shadowing.

    For each internal upstream round it forwards text deltas and non-exploration
    tool_use to the client immediately (QG-04), holds exploration tool_use up to
    the bound enforced by ``should_shadow`` per request (QG-03), executes them
    locally, then re-submits the ``tool_result`` blocks upstream and continues
    with the new round. When no more exploration tool_use is held, the round's
    closing SSE events are flushed and the stream completes.
    """

    def __init__(
        self,
        sse_source: SseSource,
        should_shadow: ShouldShadow,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        session_key: Optional[str],
        context_dir: str = ".",
        trace_id: str | None = None,
    ) -> None:
        self.sse_source = sse_source
        self.should_shadow = should_shadow
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        self.session_key = session_key
        self.context_dir = context_dir
        self.trace_id = trace_id or str(uuid4())
        # Insurance: if the streamer is ever constructed outside the request task
        # that called logger.set_trace_id, stamp the trace id here so every
        # source-level event of the shadow loop shares it (contextvars propagate
        # into asyncio.to_thread worker threads and asyncio.gather child tasks).
        logger.set_trace_id(self.trace_id)
        self.round = 1
        self.shadow_used = 0
        self.client_index = 0
        self._pending_held: List[Dict[str, Any]] = []
        self._round_failed = False
        self._start_ts = time.monotonic()

    # -- public driver -------------------------------------------------

    async def run(self) -> AsyncGenerator[bytes, None]:
        """Yield SSE bytes to the client, looping internal shadow rounds."""
        while True:
            messages = self.body.get("messages", [])
            self._pending_held = []
            async for chunk in self._stream_round(messages):
                yield chunk
            held = self._pending_held
            if not held:
                break
            self.body = {
                **self.body,
                "messages": self._build_followup(messages, held),
            }
        logger.log(
            SSE_STREAM_COMPLETE,
            trace_id=self.trace_id,
            duration_ms=self._elapsed_ms(),
            # P-4: self.round is incremented at the END of each _stream_round,
            # so a single-round request reads 2 — log the actual upstream
            # call count.
            rounds=self.round - 1,
            shadow_used=self.shadow_used,
            status="error" if self._round_failed else "ok",
        )

    # -- per-round processing -------------------------------------------

    async def _stream_round(
        self, messages: List[Dict[str, Any]]
    ) -> AsyncGenerator[bytes, None]:
        """Stream one upstream round. Sets ``self._pending_held`` on exit.

        The injected ``sse_source`` owns the HTTP request, the ``>= 400`` status
        check and mid-stream transport error handling; any of those failures
        surface as a single ``error`` SSE event, which the ``etype == "error"``
        handler below marks as failed and stops the round — identical output to
        the pre-extraction inline handling.
        """
        held_indices: set[int] = set()
        held_by_index: Dict[int, Dict[str, Any]] = {}
        client_index_map: Dict[int, int] = {}
        buffered_end: List[Tuple[Optional[str], Dict[str, Any]]] = []

        async for event_name, payload in self.sse_source(
            self.method,
            self.url,
            self.headers,
            {**self.body, "messages": messages},
        ):
            etype = payload.get("type", "")

            if etype == "message_start":
                if self.round == 1:
                    yield self._format_event(event_name, payload)
                continue

            if etype in ("message_delta", "message_stop"):
                buffered_end.append((event_name, payload))
                continue

            if etype == "content_block_start":
                index = payload.get("index")
                if not isinstance(index, int):
                    yield self._format_event(event_name, payload)
                    continue
                cb = payload.get("content_block", {})
                is_tool_use = cb.get("type") == "tool_use"
                name = cb.get("name", "")
                if (
                    isinstance(index, int)
                    and is_tool_use
                    and self.should_shadow(name, self.shadow_used)
                ):
                    self.shadow_used += 1
                    held_indices.add(index)
                    base_input = cb.get("input")
                    held_by_index[index] = {
                        "index": index,
                        "id": cb.get("id"),
                        "name": name,
                        "input_parts": (
                            [json.dumps(base_input)] if isinstance(base_input, dict) and base_input else []
                        ),
                    }
                    logger.log(
                        TOOL_SHADOW_INTERCEPT,
                        trace_id=self.trace_id,
                        tool_name=name,
                        action_taken="hold",
                    )
                    continue
                new_index = self.client_index
                self.client_index += 1
                client_index_map[index] = new_index
                payload = dict(payload)
                payload["index"] = new_index
                yield self._format_event(event_name, payload)
                continue

            if etype == "content_block_delta":
                index = payload.get("index")
                if not isinstance(index, int):
                    yield self._format_event(event_name, payload)
                    continue
                if index in held_indices:
                    delta = payload.get("delta", {})
                    partial = delta.get("partial_json", "") if isinstance(delta, dict) else ""
                    if isinstance(partial, str):
                        held_by_index[index]["input_parts"].append(partial)
                    continue
                new_index = client_index_map.get(index)
                if new_index is None:
                    continue
                payload = dict(payload)
                payload["index"] = new_index
                yield self._format_event(event_name, payload)
                continue

            if etype == "content_block_stop":
                index = payload.get("index")
                if not isinstance(index, int):
                    yield self._format_event(event_name, payload)
                    continue
                if index in held_indices:
                    continue
                new_index = client_index_map.get(index)
                if new_index is None:
                    continue
                payload = dict(payload)
                payload["index"] = new_index
                yield self._format_event(event_name, payload)
                continue

            if etype == "ping":
                yield self._format_event(event_name, payload)
                continue

            if etype == "error":
                # Upstream (or the SSE source) reported a failure; forward and
                # stop the round.
                self._round_failed = True
                yield self._format_event(event_name, payload)
                return

            # Unknown event type: forward untouched.
            yield self._format_event(event_name, payload)

        self.round += 1

        if held_indices:
            self._pending_held = await self._execute_held(
                [held_by_index[i] for i in sorted(held_indices)]
            )
            return

        # No held blocks this round -> flush the closing SSE events.
        for event_name, payload in buffered_end:
            yield self._format_event(event_name, payload)

    # -- helpers ---------------------------------------------------------

    async def _execute_held(
        self, held_blocks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute each held exploration tool locally (parallel) and summarize.

        Defensive (issue #1): ``content_block_start`` from upstream models
        (doubao/glm/deepseek) always carries ``input={}`` and the real
        arguments arrive only via ``partial_json`` deltas. When those deltas
        are missing or truncated (empty input, or JSON that never parses), the
        block is NOT executed -- instead we log the condition explicitly and
        return an actionable ``tool_result`` so the model can re-issue with
        explicit arguments instead of silently re-feeding a bare "no path
        provided" error into a retry loop.
        """

        async def _exec(block: Dict[str, Any]) -> Dict[str, Any]:
            tool_input = self._join_input(block["input_parts"])
            if not tool_input:
                logger.log(
                    TOOL_SHADOW_INTERCEPT,
                    trace_id=self.trace_id,
                    tool_name=block["name"],
                    action_taken="empty_input",
                )
                return {
                    **block,
                    "input": {},
                    "content": (
                        f"ERROR: tool {block['name']!r} received an empty input "
                        f"(no arguments streamed). Re-issue the call with explicit "
                        f"arguments (e.g. file_path/path/pattern)."
                    ),
                }
            if "_partial_json" in tool_input:
                logger.log(
                    TOOL_SHADOW_INTERCEPT,
                    trace_id=self.trace_id,
                    tool_name=block["name"],
                    action_taken="truncated_input",
                )
                return {
                    **block,
                    "input": {},
                    "content": (
                        f"ERROR: tool {block['name']!r} input was truncated "
                        f"mid-stream (incomplete JSON). Re-issue the call with "
                        f"explicit arguments."
                    ),
                }
            raw = await execute_local_tool(block["name"], tool_input, self.context_dir)
            summarized = await summarize_exploration(block["name"], raw)
            return {**block, "input": tool_input, "content": summarized}

        return await asyncio.gather(*[_exec(b) for b in held_blocks])

    @staticmethod
    def _join_input(parts: List[str]) -> Dict[str, Any]:
        """Reassemble ``partial_json`` fragments into a tool input dict."""
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

    def _build_followup(
        self, messages: List[Dict[str, Any]], held: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Append the assistant tool_use + user tool_result turns."""
        assistant_content: List[Dict[str, Any]] = []
        user_results: List[Dict[str, Any]] = []
        for block in held:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "input": block.get("input", {}),
                }
            )
            user_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": block.get("content", ""),
                }
            )
        followup = list(messages)
        if assistant_content:
            followup.append({"role": "assistant", "content": assistant_content})
        followup.append({"role": "user", "content": user_results})
        return followup

    @staticmethod
    def _format_event(event_name: Optional[str], payload: Dict[str, Any]) -> bytes:
        etype = str(payload.get("type") or event_name or "message")
        return f"event: {etype}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start_ts) * 1000)
