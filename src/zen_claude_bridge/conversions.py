"""Conversion helpers between Anthropic and OpenAI API message formats."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zen_claude_bridge")

DEEPSEEK_RECOVERY_NOTICE = (
    "[deepseek-cursor-proxy] Refreshed reasoning_content history."
)


# ---------------------------------------------------------------------------
# Anthropic -> OpenAI (upstream request)
# ---------------------------------------------------------------------------


def convert_messages(
    anthropic_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert a list of Anthropic-format messages to OpenAI chat-format messages.

    A single Anthropic message may produce multiple OpenAI messages when it
    contains tool_result blocks mixed with text content.
    """
    openai_messages: List[Dict[str, Any]] = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        converted = _convert_content(msg.get("content", ""), role)
        openai_messages.extend(converted)
    return openai_messages


def _extract_tool_result_text(tr_content: Any) -> str:
    if isinstance(tr_content, str):
        return tr_content
    if isinstance(tr_content, list):
        parts = []
        for sub in tr_content:
            if isinstance(sub, dict) and sub.get("type") == "text":
                parts.append(sub.get("text", ""))
        return "".join(parts)
    return str(tr_content)


def _convert_content(
    content: Any, role: str
) -> List[Dict[str, Any]]:
    if isinstance(content, str):
        if role == "tool_result":
            return [{"role": "tool", "content": content}]
        return [{"role": role, "content": content}]

    if isinstance(content, list):
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []

        for block in content:
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_result":
                tr_content = block.get("content", "")
                tr_text = _extract_tool_result_text(tr_content)
                tool_id = block.get("tool_use_id", "")
                tool_results.append({
                    "role": "tool",
                    "content": tr_text,
                    "tool_call_id": tool_id,
                })
            elif block_type == "tool_use":
                parsed_input = block.get("input", {})
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(parsed_input),
                    },
                })
            elif block_type == "image":
                text_parts.append("[image content not supported by this bridge]")
            else:
                text_parts.append(str(block.get("text", json.dumps(block))))

        result: List[Dict[str, Any]] = []

        # Emit tool results first (they must follow the assistant's tool_calls)
        if tool_results:
            result.extend(tool_results)

        if role == "assistant":
            msg: Dict[str, Any] = {"role": "assistant"}
            combined_text = "".join(text_parts)
            msg["content"] = combined_text if combined_text else ""
            if tool_calls:
                msg["tool_calls"] = tool_calls
            result.append(msg)
        elif role == "user":
            combined_text = "".join(text_parts)
            if combined_text:
                result.append({"role": "user", "content": combined_text})
        else:
            combined_text = "".join(text_parts)
            result.append({"role": role, "content": combined_text or ""})

        return result

    return [{"role": role, "content": str(content)}]


def convert_system(system: Any) -> Optional[Dict[str, str]]:
    if not system:
        return None
    if isinstance(system, str):
        return {"role": "system", "content": system}
    if isinstance(system, list):
        texts = [
            b.get("text", "")
            for b in system
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return {"role": "system", "content": "\n".join(texts)}
    return {"role": "system", "content": str(system)}


def convert_tools(
    tools: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    openai_tools = []
    for t in tools:
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.get("name", "unknown"),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
        )
    return openai_tools


# ---------------------------------------------------------------------------
# OpenAI tool history validation and sanitization
# ---------------------------------------------------------------------------


def validate_openai_tool_history(messages: List[Dict[str, Any]]) -> None:
    """Validate OpenAI message list for tool-call ordering.

    Raises ValueError with a clear message if the history is invalid.
    """
    for i, msg in enumerate(messages):
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        tc_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}

        remaining = tc_ids.copy()
        for j in range(i + 1, len(messages)):
            if not remaining:
                break
            nxt = messages[j]
            if nxt.get("role") == "tool":
                tcid = nxt.get("tool_call_id", "")
                remaining.discard(tcid)
            else:
                break

        if remaining:
            raise ValueError(
                f"Invalid converted tool history: assistant tool_calls "
                f"at index {i} not followed by matching tool messages. "
                f"Missing IDs: {remaining}"
            )


def sanitize_openai_tool_history(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sanitize message list by removing orphaned tool_calls.

    If an assistant message has tool_calls but no matching tool messages
    follow it, the tool_calls are removed from that message (text content
    is preserved). A warning is logged for each occurrence.

    This handles partial/incomplete histories that Claude may send.
    """
    result = list(messages)
    removals: List[int] = []

    for i, msg in enumerate(result):
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        tc_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
        remaining = tc_ids.copy()

        for j in range(i + 1, len(result)):
            if not remaining:
                break
            nxt = result[j]
            if nxt.get("role") == "tool":
                tcid = nxt.get("tool_call_id", "")
                remaining.discard(tcid)

        if remaining:
            logger.warning(
                "Sanitizing incomplete tool history at index %d: "
                "removing tool_calls with no matching results. IDs: %s",
                i,
                remaining,
            )
            removals.append(i)

    for i in reversed(removals):
        msg = result[i]
        del msg["tool_calls"]

    return result


# ---------------------------------------------------------------------------
# Upstream body builder
# ---------------------------------------------------------------------------


def build_upstream_body(
    model: str,
    openai_messages: List[Dict[str, Any]],
    system_message: Optional[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]],
    stream: bool,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    messages = list(openai_messages)
    if system_message:
        messages.insert(0, system_message)

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        body["tools"] = tools
    return body


# ---------------------------------------------------------------------------
# DeepSeek recovery notice stripping
# ---------------------------------------------------------------------------


def strip_recovery_notice(text: str, show_notice: bool = False) -> str:
    if show_notice or DEEPSEEK_RECOVERY_NOTICE not in text:
        return text

    lines = text.split("\n")
    filtered = [line for line in lines if DEEPSEEK_RECOVERY_NOTICE not in line]
    result = "\n".join(filtered)

    if result != text:
        logger.warning(
            "DeepSeek reasoning_content recovery occurred; "
            "older tool-call context may have been dropped."
        )

    return result


# ---------------------------------------------------------------------------
# OpenAI -> Anthropic (response)
# ---------------------------------------------------------------------------


def convert_response(
    openai_response: Dict[str, Any],
    request_model: str,
    request_id: str = "msg_0000000000",
    show_recovery_notice: bool = False,
) -> Dict[str, Any]:
    choices = openai_response.get("choices", [])
    choice = choices[0] if choices else {}
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")
    usage = openai_response.get("usage", {})

    content_blocks: List[Dict[str, Any]] = []
    tool_calls = message.get("tool_calls")

    text_content = strip_recovery_notice(
        message.get("content", ""), show_notice=show_recovery_notice
    )
    if text_content:
        content_blocks.append({"type": "text", "text": text_content})

    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {})
            try:
                parsed_args = json.loads(func.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                parsed_args = {}
            content_blocks.append(
                {
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": parsed_args,
                }
            )

    stop_reason_map = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
    }
    stop_reason = stop_reason_map.get(finish_reason, finish_reason or "end_turn")

    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    return {
        "id": request_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": request_model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Dot-probe suppression
# ---------------------------------------------------------------------------


def is_dot_probe(messages: List[Dict[str, Any]]) -> bool:
    if len(messages) != 1:
        return False
    msg = messages[0]
    if msg.get("role") != "user":
        return False
    content = msg.get("content", "")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "".join(
            b.get("text", "") for b in content if b.get("type") == "text"
        ).strip()
    else:
        return False
    return text == "."
