"""Focused tests for dot-probe suppression logic."""

from zen_claude_bridge.conversions import is_dot_probe


def test_exact_dot():
    assert is_dot_probe([{"role": "user", "content": "."}]) is True


def test_dot_with_whitespace():
    assert is_dot_probe([{"role": "user", "content": "  .  "}]) is True


def test_dot_block():
    assert is_dot_probe(
        [{"role": "user", "content": [{"type": "text", "text": "."}]}]
    ) is True


def test_normal_message():
    assert is_dot_probe([{"role": "user", "content": "Hello"}]) is False


def test_empty_message_list():
    assert is_dot_probe([]) is False


def test_multiple_messages():
    assert (
        is_dot_probe(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ]
        )
        is False
    )


def test_wrong_role():
    assert is_dot_probe([{"role": "assistant", "content": "."}]) is False


def test_complex_content_not_dot():
    assert (
        is_dot_probe(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "."},
                        {"type": "text", "text": "more"},
                    ],
                }
            ]
        )
        is False
    )


def test_numeric_content():
    assert is_dot_probe([{"role": "user", "content": "."}]) is True
    assert is_dot_probe([{"role": "user", "content": ".."}]) is False
