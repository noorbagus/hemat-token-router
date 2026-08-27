"""Local Reverse Proxy for Anthropic API with context injection.

Intercepts requests from Claude Code CLI to /v1/messages,
runs local AST + Ollama routing, injects pre-selected file context,
then forwards modified request to upstream gateway and streams response back.
"""

import os
import json
import logging
import httpx
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from router.ast_extractor import scan_project_codebase
from router.ollama_scorer import route_target_files, RoutingResult
from router.gate import apply_gate, GateResult
from router.safe_path import resolve_under_base, PathTraversalError

logger = logging.getLogger("csmart.proxy")


# Default configuration from environment
UPSTREAM_BASE_URL = os.environ.get("ANTHROPIC_UPSTREAM_URL", "https://ark.talaga.my.id")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
CONFIDENCE_THRESHOLD = float(os.environ.get("CSMART_THRESHOLD", "0.65"))
DEFAULT_BUDGET_TOKENS = int(os.environ.get("CSMART_BUDGET", "16000"))
DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", ".next",
    "venv", ".venv", ".dart_tool", "coverage", ".turbo", ".cache",
    "__pycache__", ".pytest_cache",
}

app = FastAPI(title="csmart local reverse proxy", version="1.0")


async def read_full_body(request: Request) -> Dict[str, Any]:
    """Read and parse full JSON request body."""
    body = await request.body()
    return json.loads(body)


def inject_context_to_messages(
    messages: List[Dict[str, Any]],
    selected_files: List[str],
) -> List[Dict[str, Any]]:
    """Inject pre-loaded file context into the last user message.

    Path-safety (F-09): every path in ``selected_files`` is validated through
    :func:`router.safe_path.resolve_under_base` before being read. Paths that
    escape the base dir (``..``, absolute-outside, symlink-outside) or that do
    not exist are skipped with a warning; only files resolving inside ``.``
    (CWD) are read.
    """
    if not selected_files:
        return messages

    # Read all selected files, skipping any that fail path validation
    context_blocks: List[str] = []
    for file_path in selected_files:
        try:
            resolved = resolve_under_base(file_path, ".")
        except PathTraversalError:
            logger.warning("skipping path traversal attempt in selected file: %r", file_path)
            continue
        if not resolved.is_file():
            logger.warning("skipping selected file (missing or not a regular file): %r", file_path)
            continue
        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as exc:
            logger.warning("skipping unreadable selected file %r: %s", file_path, exc)
            continue
        context_blocks.append(f"--- FILE START: {file_path} ---\n{content}\n--- FILE END ---\n")

    if not context_blocks:
        return messages

    # Find last user message
    injected_context = "\n".join([
        "[PRE-LOADED CONTEXT - The following files contain the relevant source code you need to modify. DO NOT run grep/find/ls tool calls because the full content is already below.]\n\n",
        *context_blocks,
        "\nNow complete the user request above using this pre-loaded context. Modify the files directly.\n",
    ])

    # Modify the last user message
    new_messages = messages.copy()
    for i in reversed(range(len(new_messages))):
        if new_messages[i]["role"] == "user":
            original_content = new_messages[i]["content"]
            if isinstance(original_content, str):
                new_content = f"{original_content}\n\n{injected_context}"
                new_messages[i]["content"] = new_content
            break

    return new_messages


def run_local_routing(prompt: str) -> GateResult:
    """Run full local routing: AST scan → Ollama scoring → gate filtering."""
    # Scan current working directory (where Claude Code is running)
    skeletons = scan_project_codebase(".", DEFAULT_IGNORE_DIRS)
    full_skeleton = "\n".join(skeletons)

    # Route with Ollama
    routing_result = route_target_files(full_skeleton, prompt)

    # Apply gate and budget
    budget_bytes = DEFAULT_BUDGET_TOKENS * 4  # 4 bytes ≈ 1 token
    return apply_gate(routing_result, CONFIDENCE_THRESHOLD, budget_bytes)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_handler(request: Request, path: str) -> Response:
    """Wildcard proxy handler - intercepts all requests and forwards."""

    # Handle CORS preflight
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    # For /v1/messages (messages endpoint), we need to intercept and inject context
    if "/messages" in path and request.method == "POST":
        return await handle_messages_request(request)

    # All other requests: passthrough untouched
    return await passthrough_request(request, path)


async def handle_messages_request(request: Request) -> Response:
    """Intercept /v1/messages, inject context, forward to upstream."""
    # Parse incoming request
    try:
        body = await read_full_body(request)
    except json.JSONDecodeError as e:
        return Response(f"Invalid JSON: {e}", status_code=400)

    # Extract last user prompt
    messages = body.get("messages", [])
    last_user_prompt = ""
    for msg in reversed(messages):
        if msg["role"] == "user" and isinstance(msg.get("content"), str):
            last_user_prompt = msg["content"]
            break

    # Run local routing
    gate_result = run_local_routing(last_user_prompt)

    # Inject selected files into messages
    modified_messages = inject_context_to_messages(messages, gate_result.selected_files)
    body["messages"] = modified_messages

    # Forward modified request to upstream with streaming
    return await forward_streaming_request(request, body)


async def forward_streaming_request(request: Request, body: Dict[str, Any]) -> Response:
    """Forward streaming request to upstream and stream response back."""
    # Build upstream URL
    upstream_path = request.url.path
    upstream_url = f"{UPSTREAM_BASE_URL}{upstream_path}"

    # Copy headers, remove host/content-length that will be regenerated
    headers = {}
    for name, value in request.headers.items():
        name_lower = name.lower()
        if name_lower not in ("host", "content-length"):
            headers[name] = value

    # Add authorization from original request
    # (Claude Code adds Authorization header already)

    # Create async httpx client with streaming
    async with httpx.AsyncClient() as client:
        request = client.build_request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            json=body,
        )

        response = await client.send(request, stream=True)

        # Stream response back to client
        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get("content-type", "text/event-stream"),
        )


async def passthrough_request(request: Request, path: str) -> Response:
    """Passthrough request untouched to upstream."""
    upstream_url = f"{UPSTREAM_BASE_URL}/{path}"
    query_params = dict(request.query_params)

    # Read body for non-GET requests
    body: Optional[bytes] = None
    if request.method not in ("GET", "HEAD"):
        body = await request.body()

    # Copy headers
    headers = {}
    for name, value in request.headers.items():
        name_lower = name.lower()
        if name_lower not in ("host", "content-length"):
            headers[name] = value

    async with httpx.AsyncClient() as client:
        req = client.build_request(
            method=request.method,
            url=upstream_url,
            params=query_params,
            headers=headers,
            content=body,
        )
        resp = await client.send(req, stream=True)

        return StreamingResponse(
            resp.aiter_raw(),
            status_code=resp.status_code,
            headers=dict(resp.headers),
            media_type=resp.headers.get("content-type"),
        )


async def check_upstream_health() -> bool:
    """Check if upstream gateway is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{UPSTREAM_BASE_URL}/v1/models")
            return resp.status_code < 500
    except Exception:
        return False


def check_ollama_health() -> bool:
    """Check if Ollama is running and model is available."""
    import ollama
    try:
        # Check model exists
        ollama.show(OLLAMA_MODEL)
        return True
    except Exception:
        return False
