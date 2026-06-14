"""Tests for message and tool conversion between Anthropic and OpenAI formats."""

import json

from zen_claude_bridge.conversions import (
    build_upstream_body,
    convert_messages,
    convert_response,
    convert_system,
    convert_tools,
    is_dot_probe,
)


# ---------------------------------------------------------------------------
# Anthropic → OpenAI message conversion
# ---------------------------------------------------------------------------


def test_text_message():
    msgs = [{"role": "user", "content": "Hello"}]
    result = convert_messages(msgs)
    assert len(result) == 1
    assert result[0] == {"role": "user", "content": "Hello"}


def test_text_block_content():
    msgs = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Hello from blocks"}],
        }
    ]
    result = convert_messages(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "Hello from blocks" in result[0]["content"]


def test_assistant_message():
    msgs = [{"role": "assistant", "content": "Sure, I can help!"}]
    result = convert_messages(msgs)
    assert result[0] == {"role": "assistant", "content": "Sure, I can help!"}


def test_tool_result_message():
    msgs = [{"role": "tool_result", "content": "Result: 42"}]
    result = convert_messages(msgs)
    assert result[0]["role"] == "tool"
    assert "Result: 42" in result[0]["content"]


def test_image_block_safe_fallback():
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}
            ],
        }
    ]
    result = convert_messages(msgs)
    assert result[0]["role"] == "user"
    assert "image content not supported" in result[0]["content"]


# ---------------------------------------------------------------------------
# System prompt conversion
# ---------------------------------------------------------------------------


def test_system_string():
    result = convert_system("You are a helpful assistant.")
    assert result == {"role": "system", "content": "You are a helpful assistant."}


def test_system_list():
    result = convert_system([
        {"type": "text", "text": "You are helpful."},
        {"type": "text", "text": "Be concise."},
    ])
    assert result is not None
    assert "You are helpful." in result["content"]
    assert "Be concise." in result["content"]


def test_system_none():
    assert convert_system(None) is None


# ---------------------------------------------------------------------------
# Tool conversion
# ---------------------------------------------------------------------------


def test_convert_tools():
    tools = [
        {
            "name": "get_weather",
            "description": "Get current weather",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        }
    ]
    result = convert_tools(tools)
    assert result is not None
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "get_weather"
    assert result[0]["function"]["parameters"]["properties"]["location"]["type"] == "string"


def test_convert_tools_none():
    assert convert_tools(None) is None


# ---------------------------------------------------------------------------
# Upstream body builder
# ---------------------------------------------------------------------------


def test_build_upstream_body():
    body = build_upstream_body(
        model="test-model",
        openai_messages=[{"role": "user", "content": "hi"}],
        system_message=None,
        tools=None,
        stream=False,
    )
    assert body["model"] == "test-model"
    assert body["stream"] is False
    assert len(body["messages"]) == 1


def test_build_upstream_body_with_system():
    body = build_upstream_body(
        model="test-model",
        openai_messages=[{"role": "user", "content": "hi"}],
        system_message={"role": "system", "content": "You are a bot."},
        tools=None,
        stream=False,
    )
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "system"


# ---------------------------------------------------------------------------
# OpenAI → Anthropic response conversion
# ---------------------------------------------------------------------------


def test_convert_text_response():
    openai_resp = {
        "choices": [
            {
                "message": {"content": "Hello back!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    result = convert_response(openai_resp, request_model="test-model")
    assert result["role"] == "assistant"
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Hello back!"
    assert result["stop_reason"] == "end_turn"
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


def test_convert_tool_call_response():
    openai_resp = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
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
    assert result["stop_reason"] == "tool_use"
    assert result["content"][0]["type"] == "tool_use"
    assert result["content"][0]["name"] == "get_weather"
    assert result["content"][0]["input"] == {"location": "Tokyo"}


# ---------------------------------------------------------------------------
# Dot probe detection
# ---------------------------------------------------------------------------


def test_dot_probe_detected():
    assert is_dot_probe([{"role": "user", "content": "."}]) is True


def test_dot_probe_block():
    assert is_dot_probe([{"role": "user", "content": [{"type": "text", "text": "."}]}]) is True


def test_dot_probe_rejected_multiple():
    assert is_dot_probe([{"role": "user", "content": "."}, {"role": "assistant", "content": "hi"}]) is False


def test_dot_probe_rejected_non_dot():
    assert is_dot_probe([{"role": "user", "content": "Hello"}]) is False


def test_dot_probe_rejected_empty():
    assert is_dot_probe([]) is False
