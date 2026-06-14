"""Conversion helpers between Anthropic and OpenAI API message formats."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zen_claude_bridge")

# Recovery notice that deepseek-cursor-proxy may inject into responses
DEEPSEEK_RECOVERY_NOTICE = (
    "[deepseek-cursor-proxy] Refreshed reasoning_content history."
)


# ---------------------------------------------------------------------------
# Anthropic → OpenAI (upstream request)
# ---------------------------------------------------------------------------


def convert_messages(
    anthropic_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert a list of Anthropic-format messages to OpenAI chat-format messages."""
    openai_messages: List[Dict[str, Any]] = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        c = _convert_content(msg.get("content", ""), role)
        if c is not None:
            openai_messages.append(c)
    return openai_messages


def _convert_content(
    content: Any, role: str
) -> Optional[Dict[str, Any]]:
    """Convert a single message's content field."""
    if isinstance(content, str):
        # tool_result with string content → role tool
        if role == "tool_result":
            return {"role": "tool", "content": content}
        return {"role": role, "content": content}

    if isinstance(content, list):
        # Anthropic content blocks
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []

        for block in content:
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_result":
                tr_content = block.get("content", "")
                if isinstance(tr_content, list):
                    for sub in tr_content:
                        if sub.get("type") == "text":
                            text_parts.append(sub.get("text", ""))
                else:
                    text_parts.append(str(tr_content))
                # Carry tool_call_id for the 'tool' role
                tool_id = block.get("tool_use_id", "")
                if tool_id:
                    tool_results.append(
                        {
                            "role": "tool",
                            "content": str(tr_content),
                            "tool_call_id": tool_id,
                        }
                    )
            elif block_type == "tool_use":
                # Anthropic tool_use (request from assistant) → OpenAI tool_calls
                parsed_input = block.get("input", {})
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(parsed_input),
                        },
                    }
                )
            elif block_type == "image":
                # Image blocks not supported by the upstream — drop with notice
                text_parts.append("[image content not supported by this bridge]")
            else:
                # Fallback: try to stringify
                text_parts.append(str(block.get("text", json.dumps(block))))

        # Build the result
        result: Dict[str, Any] = {"role": role}
        combined = "".join(text_parts)
        if combined:
            result["content"] = combined
        else:
            result["content"] = ""

        # Attach tool_calls for assistant messages
        if tool_calls:
            result["tool_calls"] = tool_calls

        # If there were tool results, return those instead
        if tool_results:
            return tool_results[0]

        return result

    return {"role": role, "content": str(content)}


def convert_system(system: Any) -> Optional[Dict[str, str]]:
    """Convert an Anthropic system prompt to an OpenAI system message."""
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
    """Convert Anthropic tool definitions to OpenAI tool definitions."""
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


def build_upstream_body(
    model: str,
    openai_messages: List[Dict[str, Any]],
    system_message: Optional[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]],
    stream: bool,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Build the complete upstream request body."""
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
    """Remove the DeepSeek reasoning_content recovery notice line from text.

    When *show_notice* is True the text is returned unchanged.
    When *show_notice* is False any line containing the notice is removed
    and a warning is logged once per occurrence.
    """
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
# OpenAI → Anthropic (response)
# ---------------------------------------------------------------------------


def convert_response(
    openai_response: Dict[str, Any],
    request_model: str,
    request_id: str = "msg_0000000000",
    show_recovery_notice: bool = False,
) -> Dict[str, Any]:
    """Convert an OpenAI /v1/chat/completions response to Anthropic /v1/messages format."""
    choices = openai_response.get("choices", [])
    choice = choices[0] if choices else {}
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")
    usage = openai_response.get("usage", {})

    content_blocks: List[Dict[str, Any]] = []
    tool_calls = message.get("tool_calls")

    # Text content — strip recovery notice if disabled
    text_content = strip_recovery_notice(
        message.get("content", ""), show_notice=show_recovery_notice
    )
    if text_content:
        content_blocks.append({"type": "text", "text": text_content})

    # Tool calls
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

    # Map finish reasons
    stop_reason_map = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
    }
    stop_reason = stop_reason_map.get(finish_reason, finish_reason or "end_turn")

    # Map usage
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
    """Detect whether the conversation is a one-token dot probe from Claude."""
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
    # The dot probe is exactly "." with nothing else
    return text == "."
