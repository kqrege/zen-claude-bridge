"""Tests for DeepSeek recovery notice handling and tool-call ID preservation."""

import json
import logging

from zen_claude_bridge.conversions import (
    DEEPSEEK_RECOVERY_NOTICE,
    convert_messages,
    convert_response,
    strip_recovery_notice,
)


# ---------------------------------------------------------------------------
# strip_recovery_notice unit tests
# ---------------------------------------------------------------------------


def test_notice_stripped_by_default():
    """The recovery notice is stripped when show_notice is False (default)."""
    text = f"{DEEPSEEK_RECOVERY_NOTICE}\nHello, how can I help?"
    result = strip_recovery_notice(text)
    assert DEEPSEEK_RECOVERY_NOTICE not in result
    assert result == "Hello, how can I help?"


def test_notice_preserved_when_enabled():
    """The recovery notice remains visible when show_notice=True."""
    text = f"{DEEPSEEK_RECOVERY_NOTICE}\nHello, how can I help?"
    result = strip_recovery_notice(text, show_notice=True)
    assert DEEPSEEK_RECOVERY_NOTICE in result
    assert result == text


def test_notice_at_beginning_rest_kept():
    """Notice at the start of text is removed, rest of answer is intact."""
    text = (
        f"{DEEPSEEK_RECOVERY_NOTICE}\n"
        "Here is the information you requested.\n"
        "The weather in Tokyo is 72°F and sunny."
    )
    result = strip_recovery_notice(text)
    assert DEEPSEEK_RECOVERY_NOTICE not in result
    assert result.startswith("Here is the information")
    assert "weather in Tokyo" in result


def test_notice_in_middle_removed():
    """Notice appearing mid-text is still removed line-wise."""
    text = (
        "Here is some context.\n"
        f"{DEEPSEEK_RECOVERY_NOTICE}\n"
        "And the continuation."
    )
    result = strip_recovery_notice(text)
    assert DEEPSEEK_RECOVERY_NOTICE not in result
    assert "Here is some context." in result
    assert "And the continuation." in result


def test_no_notice_unchanged():
    """Text without the notice is returned unchanged."""
    text = "This is a normal assistant response."
    result = strip_recovery_notice(text)
    assert result == text


def test_only_notice_returns_empty():
    """When the text is only the notice, result is empty."""
    text = DEEPSEEK_RECOVERY_NOTICE
    result = strip_recovery_notice(text)
    assert result == ""
    assert DEEPSEEK_RECOVERY_NOTICE not in result


def test_notice_in_convert_response():
    """convert_response strips the notice from text content by default."""
    openai_resp = {
        "choices": [
            {
                "message": {
                    "content": f"{DEEPSEEK_RECOVERY_NOTICE}\nHello back!"
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    result = convert_response(openai_resp, request_model="test-model")
    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert DEEPSEEK_RECOVERY_NOTICE not in result["content"][0]["text"]
    assert result["content"][0]["text"] == "Hello back!"


def test_notice_preserved_in_convert_response():
    """convert_response preserves the notice when show_recovery_notice=True."""
    openai_resp = {
        "choices": [
            {
                "message": {
                    "content": f"{DEEPSEEK_RECOVERY_NOTICE}\nHello back!"
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    result = convert_response(
        openai_resp,
        request_model="test-model",
        show_recovery_notice=True,
    )
    assert len(result["content"]) == 1
    assert DEEPSEEK_RECOVERY_NOTICE in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Tool-call ID preservation tests
# ---------------------------------------------------------------------------


def test_tool_call_id_openai_to_anthropic():
    """OpenAI tool_calls[].id becomes Anthropic tool_use.id."""
    openai_resp = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_weather_001",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"location": "Tokyo"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }
    result = convert_response(openai_resp, request_model="test-model")
    assert result["content"][0]["type"] == "tool_use"
    assert result["content"][0]["id"] == "call_weather_001"
    assert result["content"][0]["name"] == "get_weather"


def test_tool_call_id_anthropic_to_openai():
    """Anthropic tool_use.id becomes OpenAI tool_calls[].id in assistant messages."""
    msgs = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_weather_001",
                    "name": "get_weather",
                    "input": {"location": "Tokyo"},
                }
            ],
        }
    ]
    result = convert_messages(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert "tool_calls" in result[0]
    assert len(result[0]["tool_calls"]) == 1
    assert result[0]["tool_calls"][0]["id"] == "tu_weather_001"
    assert result[0]["tool_calls"][0]["function"]["name"] == "get_weather"


def test_tool_result_id_anthropic_to_openai():
    """Anthropic tool_result.tool_use_id becomes OpenAI tool_call_id."""
    msgs = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_weather_001",
                    "content": "72°F and sunny",
                }
            ],
        }
    ]
    result = convert_messages(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "tool"
    assert result[0]["tool_call_id"] == "tu_weather_001"
    assert "72°F" in result[0]["content"]


def test_tool_ids_not_regenerated():
    """Tool IDs are not regenerated when upstream provides them."""
    # OpenAI → Anthropic
    openai_resp = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "specific_call_id_123",
                            "type": "function",
                            "function": {
                                "name": "test_func",
                                "arguments": '{"x": 1}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }
    result = convert_response(openai_resp, request_model="test-model")
    assert result["content"][0]["id"] == "specific_call_id_123"

    # Anthropic → OpenAI
    msgs = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "specific_tu_id_456",
                    "name": "test_func",
                    "input": {"x": 1},
                }
            ],
        }
    ]
    result = convert_messages(msgs)
    assert result[0]["tool_calls"][0]["id"] == "specific_tu_id_456"

    # Anthropic tool_result → OpenAI tool
    msgs = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "specific_tr_id_789",
                    "content": "result data",
                }
            ],
        }
    ]
    result = convert_messages(msgs)
    assert result[0]["tool_call_id"] == "specific_tr_id_789"


# ---------------------------------------------------------------------------
# Multi-tool conversion test
# ---------------------------------------------------------------------------


def test_multiple_tool_calls_preserved():
    """Multiple tool_use blocks in one message are all converted."""
    msgs = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_a",
                    "name": "get_weather",
                    "input": {"location": "Tokyo"},
                },
                {
                    "type": "tool_use",
                    "id": "call_b",
                    "name": "get_time",
                    "input": {"timezone": "UTC"},
                },
            ],
        }
    ]
    result = convert_messages(msgs)
    assert len(result[0]["tool_calls"]) == 2
    ids = [tc["id"] for tc in result[0]["tool_calls"]]
    assert "call_a" in ids
    assert "call_b" in ids
