"""FastAPI application — Anthropic-compatible bridge to OpenAI/DeepSeek endpoints.

Endpoints
---------
- GET / HEAD /
- GET /v1/models
- POST /v1/messages
- POST /v1/messages/count_tokens
- GET /v1/memory/inspect
"""

import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from .compaction import (
    compute_fingerprint,
    maybe_compact_messages,
    session_tracker,
    should_use_reasoning_safe,
    DEEPSEEK_RECOVERY_NOTICE as COMPACTION_RECOVERY_NOTICE,
)
from .config import settings
from .conversions import (
    build_upstream_body,
    convert_messages,
    convert_response,
    convert_system,
    convert_tools,
    is_dot_probe,
    sanitize_openai_tool_history,
    validate_openai_tool_history,
)
from .security import redact_secrets, verify_bearer
from .streaming import stream_anthropic_events
from .token_count import build_count_response

logger = logging.getLogger("zen_claude_bridge")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

app = FastAPI(
    title="Zen Claude Bridge",
    description="Anthropic-compatible API bridge to DeepSeek/OpenAI endpoints",
    version="0.1.0",
)

REQUEST_ID_PREFIX = "msg_"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request_id() -> str:
    return f"{REQUEST_ID_PREFIX}{uuid.uuid4().hex[:24]}"


def _resolve_model(requested: str) -> str:
    """Accept any known alias; fall back to configured model."""
    if requested in settings.model_aliases:
        return settings.deepseek_model
    # Unknown model — still route to DeepSeek rather than rejecting
    logger.warning("Unknown model '%s' — routing to '%s'", requested, settings.deepseek_model)
    return settings.deepseek_model


# ---------------------------------------------------------------------------
# Health / Discovery endpoints
# ---------------------------------------------------------------------------


@app.get("/")
@app.head("/")
async def root(request: Request):
    """Health check — required by Claude Gateway."""
    auth = request.headers.get("authorization", "")
    if auth:
        await verify_bearer(authorization=auth)
    return {"status": "ok", "service": "zen-claude-bridge", "version": "0.1.0"}


@app.get("/v1/models")
async def list_models(request: Request):
    """Return the available model aliases (Claude Gateway discovery)."""
    auth = request.headers.get("authorization", "")
    if auth:
        await verify_bearer(authorization=auth)

    models = []
    for name in settings.model_aliases:
        models.append(
            {
                "id": name,
                "object": "model",
                "created": 1700000000,
                "owned_by": "zen-claude-bridge",
            }
        )
    return {"object": "list", "data": models}


# ---------------------------------------------------------------------------
# Core generation endpoint
# ---------------------------------------------------------------------------


async def _forward_to_upstream(
    upstream_body: Dict[str, Any],
) -> Dict[str, Any]:
    """Send a non-streaming request to the upstream chat completions endpoint."""
    headers = {"Content-Type": "application/json"}

    # Add OpenCode key if configured
    if settings.opencode_zen_api_key:
        headers["Authorization"] = f"Bearer {settings.opencode_zen_api_key}"

    logger.debug(
        "Upstream request: %s",
        redact_secrets(json.dumps(upstream_body, ensure_ascii=False)),
    )

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        resp = await client.post(
            settings.deepseek_upstream_url,
            headers=headers,
            json=upstream_body,
        )

    logger.debug("Upstream status: %d", resp.status_code)
    if not resp.is_success:
        logger.error(
            "Upstream error %d: %s", resp.status_code, resp.text[:500]
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Upstream error: {redact_secrets(resp.text[:500])}",
        )

    return resp.json()


async def _forward_stream_upstream(
    upstream_body: Dict[str, Any],
) -> AsyncGenerator[bytes, None]:
    """Send a streaming request and yield raw SSE bytes from upstream."""
    headers = {"Content-Type": "application/json"}
    if settings.opencode_zen_api_key:
        headers["Authorization"] = f"Bearer {settings.opencode_zen_api_key}"

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        async with client.stream(
            "POST",
            settings.deepseek_upstream_url,
            headers=headers,
            json=upstream_body,
        ) as resp:
            if not resp.is_success:
                error_text = await resp.aread()
                logger.error(
                    "Upstream stream error %d: %s",
                    resp.status_code,
                    error_text[:500],
                )
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Upstream stream error: {redact_secrets(error_text[:500])}",
                )
            async for chunk in resp.aiter_bytes():
                yield chunk


@app.post("/v1/messages")
async def create_message(request: Request):
    """Main generation endpoint — accepts Anthropic /v1/messages format."""
    auth = request.headers.get("authorization", "")
    await verify_bearer(authorization=auth)

    body = await request.json()
    logger.debug("Incoming request: %s", redact_secrets(json.dumps(body, ensure_ascii=False)))

    # Extract fields
    messages: List[Dict[str, Any]] = body.get("messages", [])
    system = body.get("system")
    tools = body.get("tools")
    stream = body.get("stream", False)
    max_tokens = body.get("max_tokens", 4096)
    temperature = body.get("temperature", 0.7)
    requested_model = body.get("model", settings.deepseek_model)

    # Dot probe suppression
    if is_dot_probe(messages):
        logger.info("Suppressed dot probe")
        return JSONResponse(
            content={
                "id": _make_request_id(),
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": ""}],
                "model": requested_model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )

    # Resolve model
    resolved_model = _resolve_model(requested_model)

    # --- Bridge Memory Compaction (optional) ---
    fingerprint = compute_fingerprint(body) if settings.bridge_context_compaction else None

    reasoning_safe = False
    if fingerprint:
        reasoning_safe = should_use_reasoning_safe(settings, fingerprint)

    if settings.bridge_context_compaction:
        messages, compact_info = maybe_compact_messages(
            messages, system, settings, fingerprint, reasoning_safe
        )

    # Convert messages (after possible compaction)
    openai_messages = convert_messages(messages)
    openai_messages = sanitize_openai_tool_history(openai_messages)
    try:
        validate_openai_tool_history(openai_messages)
    except ValueError as exc:
        logger.error("Tool history validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    system_message = convert_system(system) if system else None
    openai_tools = convert_tools(tools) if tools else None

    # Build upstream body
    upstream_body = build_upstream_body(
        model=resolved_model,
        openai_messages=openai_messages,
        system_message=system_message,
        tools=openai_tools,
        stream=stream,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    if stream:
        return StreamingResponse(
            _generate_stream(upstream_body, requested_model, fingerprint=fingerprint),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming
    upstream_response = await _forward_to_upstream(upstream_body)

    # Track DeepSeek reasoning recovery in non-streaming responses
    if fingerprint:
        _track_recovery_in_nonstream_response(upstream_response, fingerprint)

    anthropic_response = convert_response(
        upstream_response,
        request_model=requested_model,
        request_id=_make_request_id(),
        show_recovery_notice=settings.show_deepseek_recovery_notice,
    )
    return JSONResponse(content=anthropic_response)


async def _generate_stream(
    upstream_body: Dict[str, Any],
    model: str,
    fingerprint: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Wrap upstream SSE stream into Anthropic SSE events."""
    on_recovery = None
    if fingerprint:
        on_recovery = lambda: session_tracker.record_recovery(fingerprint)  # noqa: E731
    try:
        upstream_gen = _forward_stream_upstream(upstream_body)
        async for event in stream_anthropic_events(
            upstream_gen,
            model,
            show_recovery_notice=settings.show_deepseek_recovery_notice,
            on_recovery_detected=on_recovery,
        ):
            yield event
    except HTTPException:
        yield f"event: error\ndata: {json.dumps({'error': 'upstream stream failed'})}\n\n"
    except Exception:
        logger.exception("Streaming error — internal failure")
        yield f"event: error\ndata: {json.dumps({'error': 'upstream stream error'})}\n\n"


def _track_recovery_in_nonstream_response(
    response: Dict[str, Any], fingerprint: str
) -> None:
    """Check a non-streaming upstream response for the recovery notice."""
    choices = response.get("choices", [])
    for choice in choices:
        msg = choice.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str) and COMPACTION_RECOVERY_NOTICE in content:
            session_tracker.record_recovery(fingerprint)
            break


# ---------------------------------------------------------------------------
# Token count endpoint
# ---------------------------------------------------------------------------


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    """Approximate local token counting — no upstream call.

    When compaction is enabled, returns the estimated count *after*
    compaction so that Claude/Gateway does not force its own
    destructive compaction too early.
    """
    auth = request.headers.get("authorization", "")
    await verify_bearer(authorization=auth)

    body = await request.json()
    messages: List[Dict[str, Any]] = body.get("messages", [])
    system = body.get("system")

    if settings.bridge_context_compaction:
        from .compaction import compacted_token_estimate
        fingerprint = compute_fingerprint(body)
        estimated = compacted_token_estimate(messages, system, settings, fingerprint)
        return JSONResponse(content={"input_tokens": estimated})

    result = build_count_response(messages, system)
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# Compaction / diagnostics endpoint
# ---------------------------------------------------------------------------


@app.get("/v1/memory/inspect")
async def memory_inspect(request: Request, fingerprint: str = ""):
    """Return session diagnostics for a given fingerprint.

    This endpoint requires authentication.  It does not return raw prompt
    content or secrets.
    """
    auth = request.headers.get("authorization", "")
    try:
        await verify_bearer(authorization=auth)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not fingerprint:
        return {"error": "query parameter 'fingerprint' is required"}

    from .compaction import load_memory_summary
    info = session_tracker.session_info(fingerprint)
    summary = load_memory_summary(fingerprint, settings.bridge_memory_dir)

    return {
        "fingerprint": fingerprint,
        "compaction_enabled": settings.bridge_context_compaction,
        "recovery_notice_count": info.get("recovery_notice_count", 0),
        "last_recovery_at": info.get("last_recovery_at", 0.0),
        "last_compaction_at": info.get("last_compaction_at", 0.0),
        "safe_mode_active": info.get("safe_mode_active", False),
        "has_persisted_summary": summary is not None,
        "summary_length_chars": len(summary) if summary else 0,
    }
