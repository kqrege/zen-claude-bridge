"""Tests for approximate local token counting."""

from zen_claude_bridge.token_count import (
    build_count_response,
    estimate_messages_tokens,
    estimate_tokens,
)


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_short():
    assert estimate_tokens("Hello") == 1  # "Hello" is 5 chars, 5//4 = 1


def test_estimate_tokens_longer():
    text = "Hello world, this is a test"  # 26 chars
    assert estimate_tokens(text) == 6  # 26//4 = 6


def test_count_response_basic():
    messages = [{"role": "user", "content": "Hello world"}]
    result = build_count_response(messages)
    assert "input_tokens" in result
    assert isinstance(result["input_tokens"], int)
    assert result["input_tokens"] >= 1


def test_count_response_with_system():
    messages = [{"role": "user", "content": "Hello"}]
    result = build_count_response(messages, system="You are a bot.")
    assert result["input_tokens"] >= 1


def test_estimate_messages_empty():
    assert estimate_messages_tokens([]) >= 1


def test_estimate_messages_with_content_blocks():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hello from block"},
                {"type": "tool_result", "content": "42"},
            ],
        }
    ]
    tokens = estimate_messages_tokens(messages)
    assert tokens >= 1


def test_estimate_messages_with_tool_use():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "get_weather", "input": {"loc": "NYC"}}
            ],
        }
    ]
    tokens = estimate_messages_tokens(messages)
    assert tokens >= 1


def test_estimate_messages_with_image():
    messages = [
        {
            "role": "user",
            "content": [{"type": "image", "source": {"data": "abc"}}],
        }
    ]
    tokens = estimate_messages_tokens(messages)
    assert tokens >= 100  # image overhead
