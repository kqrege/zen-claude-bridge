"""Approximate local token counting for count_tokens endpoints.

No upstream API call is made — this is a fast local estimation.
"""

import json
from typing import Any, Dict, List, Optional, Union


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(
    messages: List[Dict[str, Any]],
    system: Optional[Union[str, List[Dict[str, Any]]]] = None,
) -> int:
    """Estimate total input tokens from an Anthropic message list."""
    total = 0

    if system:
        if isinstance(system, str):
            total += estimate_tokens(system)
        elif isinstance(system, list):
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))

    for msg in messages:
        role = msg.get("role", "")
        # ~1 token for role overhead
        total += 1
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                block_type = block.get("type", "")
                if block_type == "text":
                    total += estimate_tokens(block.get("text", ""))
                elif block_type == "image":
                    total += 100  # rough image token allowance
                elif block_type == "tool_use":
                    total += estimate_tokens(block.get("name", ""))
                    total += estimate_tokens(
                        json.dumps(block.get("input", {}))
                    )
                elif block_type == "tool_result":
                    tr_content = block.get("content", "")
                    if isinstance(tr_content, str):
                        total += estimate_tokens(tr_content)
                    else:
                        total += estimate_tokens(json.dumps(tr_content))

    return max(1, total)


def build_count_response(
    messages: List[Dict[str, Any]],
    system: Optional[Union[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, int]:
    """Build an Anthropic-compatible /count_tokens response."""
    input_tokens = estimate_messages_tokens(messages, system)
    return {"input_tokens": input_tokens}
