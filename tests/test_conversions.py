"""Tests for message and tool conversion between Anthropic and OpenAI formats."""

import json

from zen_claude_bridge.conversions import (
    build_upstream_body,
    convert_messages,
    convert_response,
    convert_system,
    convert_tools,
    is_dot_probe,
    sanitize_openai_tool_history,
    validate_openai_tool_history,
)


# ---------------------------------------------------------------------------
# Anthropic -> OpenAI message conversion
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
# Tool-use conversion: Anthropic assistant tool_use -> OpenAI tool_calls
# ---------------------------------------------------------------------------


def test_assistant_tool_use_converts_to_tool_calls():
    msgs = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me check the weather."},
                {
                    "type": "tool_use",
                    "id": "toolu_abc123",
                    "name": "get_weather",
                    "input": {"location": "Tokyo"},
                },
            ],
        }
    ]
    result = convert_messages(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert result[0]["content"] == "Let me check the weather."
    assert "tool_calls" in result[0]
    assert len(result[0]["tool_calls"]) == 1
    tc = result[0]["tool_calls"][0]
    assert tc["id"] == "toolu_abc123"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "get_weather"
    assert json.loads(tc["function"]["arguments"]) == {"location": "Tokyo"}


# ---------------------------------------------------------------------------
# Tool-result conversion: Anthropic user tool_result -> OpenAI role:tool
# ---------------------------------------------------------------------------


def test_user_tool_result_converts_to_tool_message():
    msgs = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_file",
                    "input": {"path": "README.md"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "README content here",
                }
            ],
        },
    ]
    result = convert_messages(msgs)
    assert len(result) == 2
    assert result[0]["role"] == "assistant"
    assert "tool_calls" in result[0]
    assert result[1]["role"] == "tool"
    assert result[1]["tool_call_id"] == "toolu_1"
    assert "README content here" in result[1]["content"]


def test_multiple_tool_results_preserve_ids():
    msgs = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_a", "name": "get_a", "input": {}},
                {"type": "tool_use", "id": "toolu_b", "name": "get_b", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_a", "content": "Result A"},
                {"type": "tool_result", "tool_use_id": "toolu_b", "content": "Result B"},
            ],
        },
    ]
    result = convert_messages(msgs)
    assert len(result) == 3
    assert result[0]["role"] == "assistant"
    assert len(result[0]["tool_calls"]) == 2
    assert result[1]["role"] == "tool"
    assert result[1]["tool_call_id"] == "toolu_a"
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "toolu_b"


# ---------------------------------------------------------------------------
# Mixed tool_result + text in user message
# ---------------------------------------------------------------------------


def test_mixed_tool_result_and_text_splits_correctly():
    msgs = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "read", "input": {}}],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "file content"},
                {"type": "text", "text": "Now summarize what you read."},
            ],
        },
    ]
    result = convert_messages(msgs)
    assert len(result) == 3
    assert result[0]["role"] == "assistant"
    assert result[1]["role"] == "tool"
    assert result[1]["tool_call_id"] == "toolu_1"
    assert result[2]["role"] == "user"
    assert "Now summarize" in result[2]["content"]


def test_tool_result_text_before_text_in_user_message():
    msgs = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "read", "input": {}}],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Look at this file: "},
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ABC"},
                {"type": "text", "text": " What do you think?"},
            ],
        },
    ]
    result = convert_messages(msgs)
    assert len(result) == 3
    assert result[1]["role"] == "tool"
    assert result[1]["tool_call_id"] == "toolu_1"
    assert result[2]["role"] == "user"
    assert "Look at this file:" in result[2]["content"]
    assert "What do you think?" in result[2]["content"]
    assert "ABC" not in result[2]["content"]


# ---------------------------------------------------------------------------
# Tool result with list content block
# ---------------------------------------------------------------------------


def test_tool_result_list_content_extracts_text():
    msgs = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_x", "name": "search", "input": {}}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_x",
                    "content": [
                        {"type": "text", "text": "Search result line 1"},
                        {"type": "text", "text": "Search result line 2"},
                    ],
                }
            ],
        },
    ]
    result = convert_messages(msgs)
    assert len(result) == 2
    assert result[1]["role"] == "tool"
    assert result[1]["tool_call_id"] == "toolu_x"
    assert "Search result line 1" in result[1]["content"]
    assert "Search result line 2" in result[1]["content"]
    assert result[0]["role"] == "assistant"
    assert "tool_calls" in result[0]


# ---------------------------------------------------------------------------
# Realistic Claude Code style: tool use -> result -> follow-up
# ---------------------------------------------------------------------------


def test_claude_code_style_tool_chain():
    msgs = [
        {"role": "user", "content": "Read the README"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_read_1",
                    "name": "Read",
                    "input": {"file_path": "README.md"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_read_1",
                    "content": "# Zen Claude Bridge\nA bridge to run...",
                }
            ],
        },
        {"role": "user", "content": "Now summarize what you read."},
    ]
    result = convert_messages(msgs)
    assert len(result) == 4
    assert result[0] == {"role": "user", "content": "Read the README"}
    assert result[1]["role"] == "assistant"
    assert result[1]["tool_calls"][0]["id"] == "toolu_read_1"
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "toolu_read_1"
    assert result[3] == {"role": "user", "content": "Now summarize what you read."}


def test_tool_call_id_not_regenerated():
    """Tool IDs from Anthropic must be preserved exactly in OpenAI conversion."""
    msgs = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_custom_id_42", "name": "read", "input": {}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_custom_id_42", "content": "data"}
            ],
        },
    ]
    result = convert_messages(msgs)
    assert result[0]["tool_calls"][0]["id"] == "toolu_custom_id_42"
    assert result[1]["tool_call_id"] == "toolu_custom_id_42"


# ---------------------------------------------------------------------------
# Tool history validation and sanitization
# ---------------------------------------------------------------------------


def test_validate_valid_tool_history_passes():
    msgs = [
        {"role": "user", "content": "Read it"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        {"role": "user", "content": "Thanks"},
    ]
    validate_openai_tool_history(msgs)


def test_validate_missing_tool_result_raises():
    msgs = [
        {"role": "user", "content": "Read it"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        },
        {"role": "user", "content": "Where is the result?"},
    ]
    import pytest
    with pytest.raises(ValueError, match="Invalid converted tool history"):
        validate_openai_tool_history(msgs)


def test_validate_extra_non_tool_between_tool_calls_and_results_raises():
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        },
        {"role": "user", "content": "Wait, I changed my mind."},
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
    ]
    import pytest
    with pytest.raises(ValueError, match="Invalid converted tool history"):
        validate_openai_tool_history(msgs)


def test_sanitize_removes_orphan_tool_calls():
    msgs = [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "Let me help",
            "tool_calls": [{"id": "orphan_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        },
        {"role": "user", "content": "Never mind"},
    ]
    result = sanitize_openai_tool_history(msgs)
    assert "tool_calls" not in result[1]
    assert result[1]["content"] == "Let me help"


def test_sanitize_preserves_complete_tool_calls():
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
    ]
    result = sanitize_openai_tool_history(msgs)
    assert "tool_calls" in result[0]
    assert len(result[0]["tool_calls"]) == 1
    assert result[0]["tool_calls"][0]["id"] == "call_1"


def test_sanitize_handles_partial_missing_ids():
    """If some tool calls have results and some don't, remove only orphaned ones."""
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_a", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_b", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": "result A"},
        {"role": "user", "content": "Continue"},
    ]
    result = sanitize_openai_tool_history(msgs)
    assert "tool_calls" not in result[0]


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
# OpenAI -> Anthropic response conversion
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
