"""Anthropic-compatible SSE event generation for streaming responses."""

import json
import uuid
from typing import Any, AsyncGenerator, Dict, Optional


def _make_id(prefix: str = "msg") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


async def stream_anthropic_events(
    upstream_stream: AsyncGenerator[bytes, None],
    request_model: str,
) -> AsyncGenerator[str, None]:
    """Convert OpenAI SSE chunks into Anthropic SSE events."""
    msg_id = _make_id("msg")
    content_index = 0
    has_started = False
    has_content_block_started = False

    async for raw_chunk in upstream_stream:
        chunk_str = raw_chunk.decode("utf-8", errors="replace").strip()

        # Handle OpenAI SSE format (data: {...})
        if not chunk_str or chunk_str.startswith(":") or chunk_str == "data: [DONE]":
            continue

        prefix = "data: "
        if chunk_str.startswith(prefix):
            chunk_str = chunk_str[len(prefix):]

        try:
            chunk_data = json.loads(chunk_str)
        except json.JSONDecodeError:
            continue

        choices = chunk_data.get("choices", [])
        if not choices:
            continue

        delta = choices[0].get("delta", {})
        finish_reason = choices[0].get("finish_reason")

        # Emit message_start on first chunk with content
        if not has_started:
            has_started = True
            yield _sse("message_start", _build_message_start(msg_id, request_model))

        # Emit content_block_start for text
        text_content = delta.get("content", "")
        if text_content and not has_content_block_started:
            has_content_block_started = True
            yield _sse(
                "content_block_start",
                {
                    "type": "text",
                    "index": content_index,
                    "content_block": {"type": "text", "text": ""},
                },
            )

        # Content block delta
        if text_content:
            yield _sse(
                "content_block_delta",
                {
                    "type": "text_delta",
                    "index": content_index,
                    "delta": {"text": text_content},
                },
            )

        # Handle tool calls
        tool_calls = delta.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            tc_index = tc.get("index", 0)
            # Emit content_block_start for tool_use
            yield _sse(
                "content_block_start",
                {
                    "type": "tool_use",
                    "index": content_index + tc_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tc.get("id", f"tu_{uuid.uuid4().hex[:16]}"),
                        "name": func.get("name", ""),
                        "input": {},
                    },
                },
            )
            # Tool use delta
            args = func.get("arguments", "")
            if args:
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "input_json_delta",
                        "index": content_index + tc_index,
                        "delta": {"partial_json": args},
                    },
                )
            # content_block_stop for tool_use
            yield _sse(
                "content_block_stop",
                {"index": content_index + tc_index},
            )

        # Emit content_block_stop for text on finish
        if finish_reason and has_content_block_started:
            yield _sse("content_block_stop", {"index": content_index})
            content_index += 1

        # Emit message_delta and message_stop on finish
        if finish_reason:
            stop_reason_map = {
                "stop": "end_turn",
                "length": "max_tokens",
                "tool_calls": "tool_use",
            }
            stop_reason = stop_reason_map.get(finish_reason, finish_reason)

            usage = chunk_data.get("usage", {})
            yield _sse(
                "message_delta",
                {
                    "delta": {
                        "stop_reason": stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": {
                        "output_tokens": usage.get("completion_tokens", 0),
                    },
                },
            )
            yield _sse("message_stop", {})


def _build_message_start(msg_id: str, model: str) -> Dict[str, Any]:
    return {
        "type": "message",
        "id": msg_id,
        "role": "assistant",
        "content": [],
        "model": model,
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
