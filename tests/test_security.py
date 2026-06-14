"""Tests for security utilities."""

from zen_claude_bridge.security import redact_secrets


def test_redact_secrets_string():
    result = redact_secrets("Bearer sk-my-secret-key-here")
    assert "[REDACTED]" in result
    assert "sk-my-secret-key-here" not in result


def test_redact_secrets_bytes():
    result = redact_secrets(b"Bearer sk-my-secret-key-here")
    assert "[REDACTED]" in result
    assert "sk-my-secret-key-here" not in result


def test_redact_secrets_bytearray():
    result = redact_secrets(bytearray(b"Bearer sk-my-secret-key-here"))
    assert "[REDACTED]" in result
    assert "sk-my-secret-key-here" not in result


def test_redact_secrets_no_secret():
    result = redact_secrets("Just some normal text")
    assert result == "Just some normal text"


def test_redact_secrets_empty():
    assert redact_secrets("") == ""
    assert redact_secrets(b"") == ""


def test_redact_secrets_bytes_error_message():
    error = b'{"error":{"message":"Something failed"}}'
    result = redact_secrets(error)
    assert "Something failed" in result
