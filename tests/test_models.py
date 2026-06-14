"""Tests for model alias resolution."""

from zen_claude_bridge.config import settings, CLAUDE_MODEL_ALIASES


def test_core_aliases_present():
    required = [
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-haiku-4-5",
        "claude-haiku-4-5-latest",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
        "claude-opus-4-1",
        "deepseek-v4-flash-free",
    ]
    for alias in required:
        assert alias in CLAUDE_MODEL_ALIASES, f"Missing alias: {alias}"


def test_all_aliases_via_settings():
    aliases = settings.model_aliases
    assert len(aliases) >= 8
    assert "claude-sonnet-4-6" in aliases


def test_resolve_model_internal():
    """Verifies the model mapping logic (integration-style)."""
    from zen_claude_bridge.app import _resolve_model

    # Any alias should map to the configured deepseek_model
    for alias in CLAUDE_MODEL_ALIASES:
        resolved = _resolve_model(alias)
        assert resolved == settings.deepseek_model, (
            f"Alias '{alias}' resolved to '{resolved}', expected '{settings.deepseek_model}'"
        )


def test_unknown_model_resolves():
    """Unknown models should still resolve to the default model."""
    from zen_claude_bridge.app import _resolve_model

    resolved = _resolve_model("unknown-model-v99")
    assert resolved == settings.deepseek_model
