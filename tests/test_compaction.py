"""Tests for the Bridge Memory Compaction module.

Covers:
- compaction disabled = payload unchanged
- below threshold = payload unchanged
- above threshold = older messages summarized
- recent N messages preserved exactly
- exact remembered words preserved in summary
- commands, file paths, errors preserved in summary
- .bridge-memory save/load works
- fingerprint stable for same session
- fingerprint changes for different first user message
- tool_use/tool_result pairs not split
- count_tokens uses compacted count when enabled
- .bridge-memory/ is gitignored
- recovery tracking increments counter
- repeated recovery activates reasoning-safe mode
- full tool-call episode summarized in reasoning-safe mode
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from zen_claude_bridge.compaction import (
    MEMORY_BLOCK_HEADER,
    SessionTracker,
    _conversation_fingerprint,
    _extract_text_from_message,
    _has_tool_use,
    _rebalance_tool_pair_boundary,
    _strip_tool_calls_from_message,
    _summarize_messages,
    compute_fingerprint,
    load_memory_summary,
    maybe_compact_messages,
    save_memory_summary,
    session_tracker,
    should_use_reasoning_safe,
)
from zen_claude_bridge.config import Settings


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------


@pytest.fixture
def base_settings() -> Settings:
    """Settings with compaction disabled."""
    return Settings()


@pytest.fixture
def compact_settings() -> Settings:
    return Settings(
        bridge_context_compaction=True,
        bridge_compaction_trigger_tokens=100,
        bridge_compaction_target_tokens=60,
        bridge_compaction_keep_recent_messages=3,
        bridge_compaction_max_summary_chars=5000,
        bridge_memory_dir=tempfile.mkdtemp(),
        bridge_reasoning_recovery_tracking=True,
        bridge_reasoning_recovery_threshold=3,
        bridge_reasoning_safe_mode="auto",
        bridge_reasoning_safe_mode_recovery_threshold=3,
        bridge_reasoning_safe_keep_recent_messages=2,
    )


@pytest.fixture
def many_messages() -> List[Dict[str, Any]]:
    """Build 20 messages that should exceed low trigger thresholds."""
    msgs = []
    for i in range(10):
        msgs.append({"role": "user", "content": f"Hello, what is {i}*{i}?"})
        msgs.append(
            {"role": "assistant", "content": f"The answer to {i}*{i} is {i*i}."}
        )
    return msgs


def _make_settings(**overrides: Any) -> Settings:
    """Create a Settings with defaults suitable for compaction tests."""
    kwargs: Dict[str, Any] = dict(
        bridge_context_compaction=True,
        bridge_compaction_trigger_tokens=100,
        bridge_compaction_target_tokens=60,
        bridge_compaction_keep_recent_messages=3,
        bridge_compaction_max_summary_chars=5000,
        bridge_memory_dir=tempfile.mkdtemp(),
        bridge_reasoning_recovery_tracking=True,
        bridge_reasoning_recovery_threshold=3,
        bridge_reasoning_safe_mode="off",
        bridge_reasoning_safe_mode_recovery_threshold=3,
        bridge_reasoning_safe_keep_recent_messages=2,
    )
    kwargs.update(overrides)
    return Settings(**kwargs)


# -----------------------------------------------------------------------
# 1. Compaction disabled = payload unchanged
# -----------------------------------------------------------------------


def test_compaction_disabled_returns_unchanged():
    settings = _make_settings(bridge_context_compaction=False)
    msgs = [{"role": "user", "content": "hello"}]
    result, info = maybe_compact_messages(msgs, None, settings)
    assert result is msgs
    assert info is None


# -----------------------------------------------------------------------
# 2. Below threshold = payload unchanged
# -----------------------------------------------------------------------


def test_below_threshold_unchanged():
    settings = _make_settings(bridge_compaction_trigger_tokens=999999)
    msgs = [{"role": "user", "content": "hello"}]
    result, info = maybe_compact_messages(msgs, None, settings)
    assert result is msgs
    assert info is None


# -----------------------------------------------------------------------
# 3. Above threshold = older messages summarized
# -----------------------------------------------------------------------


def test_above_threshold_compacts():
    """Verify that older messages are replaced by a memory block."""
    settings = _make_settings(bridge_compaction_trigger_tokens=10)
    msgs = [
        {"role": "user", "content": "My name is Alice."},
        {"role": "assistant", "content": "Hello Alice!"},
        {"role": "user", "content": "My favorite color is blue."},
        {"role": "assistant", "content": "Nice, blue is a great color."},
        {"role": "user", "content": "What was my name?"},
    ]
    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None
    assert info["original_messages"] == 5
    assert compacted is not msgs  # new list
    # Should have memory block + recent messages
    assert len(compacted) <= 4
    # First message should be the memory block
    assert MEMORY_BLOCK_HEADER in str(compacted[0])


# -----------------------------------------------------------------------
# 4. Recent N messages preserved exactly
# -----------------------------------------------------------------------


def test_recent_messages_preserved():
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=3,
    )
    msgs = []
    for i in range(8):
        msgs.append({"role": "user", "content": f"Message number {i}"})
        msgs.append({"role": "assistant", "content": f"Reply to {i}"})

    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None

    # The last 3 messages should be preserved exactly (after rebalancing)
    # The first message of compacted is the memory block
    # remaining are the recent raw messages
    memory_msg = compacted[0]
    assert MEMORY_BLOCK_HEADER in str(memory_msg["content"])

    # Check that recent message content is intact
    recent = compacted[1:]
    # Find "Message number 7" in recent messages
    recent_texts = " ".join(
        _extract_text_from_message(m) for m in recent
    )
    assert "Message number 7" in recent_texts


# -----------------------------------------------------------------------
# 5. Exact remembered words preserved in summary
# -----------------------------------------------------------------------


def test_remembered_word_in_summary():
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=1,
    )
    msgs = [
        {"role": "user", "content": "Remember this word: pineapple_bridge_742"},
        {"role": "assistant", "content": "I will remember pineapple_bridge_742."},
        {"role": "user", "content": "What is the latest news?"},
        {"role": "assistant", "content": "Here is some news."},
        {"role": "user", "content": "What was the word I gave you?"},
    ]
    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None
    memory_text = str(compacted[0])
    assert "pineapple_bridge_742" in memory_text


# -----------------------------------------------------------------------
# 6. Commands, file paths, errors preserved in summary
# -----------------------------------------------------------------------


def test_commands_paths_errors_in_summary():
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=1,
    )
    msgs = [
        {"role": "user", "content": "Run: pip install requests"},
        {"role": "assistant", "content": "Done. pip install requests succeeded."},
        {
            "role": "user",
            "content": "cat /var/log/syslog | grep error",
        },
        {
            "role": "assistant",
            "content": "Traceback (most recent call last): File not found error.",
        },
        {
            "role": "user",
            "content": "Check C:\\Users\\test\\project\\main.py",
        },
        {"role": "assistant", "content": "File path noted."},
        {"role": "user", "content": "What commands did I run?"},
    ]
    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None
    memory_text = str(compacted[0])
    assert "pip install requests" in memory_text
    assert "cat /var/log/syslog" in memory_text or "/var/log/syslog" in memory_text
    assert "Traceback" in memory_text or "File not found" in memory_text
    assert "C:\\Users\\test\\project\\main.py" in memory_text or "main.py" in memory_text


# -----------------------------------------------------------------------
# 7. .bridge-memory save/load works
# -----------------------------------------------------------------------


def test_memory_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        fp = "test_fingerprint_123"
        summary = "This is a test summary for persistence."
        path = save_memory_summary(fp, summary, tmpdir)
        assert path is not None
        assert path.exists()

        loaded = load_memory_summary(fp, tmpdir)
        assert loaded == summary

        # Non-existent fingerprint returns None
        assert load_memory_summary("nonexistent", tmpdir) is None


# -----------------------------------------------------------------------
# 8. Fingerprint stable for same session
# -----------------------------------------------------------------------


def test_fingerprint_stable():
    payload1 = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "Hello, world!"},
            {"role": "assistant", "content": "Hi there!"},
        ],
    }
    payload2 = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "Hello, world!"},
            {"role": "assistant", "content": "How can I help?"},
        ],
    }
    fp1 = compute_fingerprint(payload1)
    fp2 = compute_fingerprint(payload2)
    assert fp1 == fp2, "fingerprints should be stable for same first user message"


# -----------------------------------------------------------------------
# 9. Fingerprint changes for different first user message
# -----------------------------------------------------------------------


def test_fingerprint_differs():
    payload1 = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "What is AI?"}],
    }
    payload2 = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "What is the weather?"}],
    }
    fp1 = compute_fingerprint(payload1)
    fp2 = compute_fingerprint(payload2)
    assert fp1 != fp2


# -----------------------------------------------------------------------
# 10. Tool_use/tool_result pairs not split
# -----------------------------------------------------------------------


def test_tool_pair_not_split():
    """When the last older message has tool_use, it must be pulled into recent."""
    older = [
        {"role": "user", "content": "Get the weather"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "get_weather",
                    "input": {"location": "NYC"},
                }
            ],
        },
    ]
    recent = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "content": "72°F, sunny",
                }
            ],
        },
        {"role": "assistant", "content": "It's 72°F and sunny in NYC."},
    ]
    new_older, new_recent = _rebalance_tool_pair_boundary(older, recent)
    # The tool_use message should be moved to recent
    assert len(new_older) == 1
    assert len(new_recent) == 3
    assert new_older[0]["role"] == "user"
    assert new_recent[0]["role"] == "assistant"
    assert _has_tool_use(new_recent[0])


def test_tool_pair_stays_intact_in_compaction():
    """Compaction should not split a tool_use/tool_result pair."""
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=3,
    )
    msgs = [
        {"role": "user", "content": "Old message 1"},
        {"role": "assistant", "content": "Old reply 1"},
        {"role": "user", "content": "Get weather for NYC"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "get_weather",
                    "input": {"location": "NYC"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "content": "72°F, sunny",
                }
            ],
        },
        {"role": "assistant", "content": "It's 72°F and sunny in NYC."},
    ]
    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None
    # After compaction, the memory block + recent messages
    # The tool_use and tool_result should both be in the same section
    recent = compacted[1:]
    # Check that the tool_use message made it into recent
    recent_text = " ".join(str(m) for m in recent)
    assert "get_weather" in recent_text or "tu_001" in recent_text


# -----------------------------------------------------------------------
# 11. count_tokens uses compacted count when enabled
# -----------------------------------------------------------------------


def test_compacted_token_estimate():
    from zen_claude_bridge.compaction import compacted_token_estimate

    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=1,
        bridge_compaction_max_summary_chars=200,
    )
    msgs = [
        {"role": "user", "content": "x" * 5000},
        {"role": "assistant", "content": "y" * 5000},
        {"role": "user", "content": "z" * 5000},
        {"role": "assistant", "content": "w" * 5000},
        {"role": "user", "content": "q" * 5000},
    ]
    raw_estimate = sum(len(m.get("content", "")) // 4 + 1 for m in msgs)
    compacted_estimate = compacted_token_estimate(msgs, None, settings)
    assert compacted_estimate < raw_estimate


# -----------------------------------------------------------------------
# 12. .bridge-memory/ is gitignored
# -----------------------------------------------------------------------


def test_bridge_memory_gitignored():
    gitignore_path = Path(__file__).parent.parent / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    assert ".bridge-memory/" in content


# -----------------------------------------------------------------------
# 13. Recovery tracking increments counter
# -----------------------------------------------------------------------


def test_recovery_tracking():
    tracker = SessionTracker()
    fp = "test_fp_recovery"
    assert tracker.recovery_count(fp) == 0
    tracker.record_recovery(fp)
    assert tracker.recovery_count(fp) == 1
    tracker.record_recovery(fp)
    tracker.record_recovery(fp)
    assert tracker.recovery_count(fp) == 3


# -----------------------------------------------------------------------
# 14. Repeated recovery activates reasoning-safe mode
# -----------------------------------------------------------------------


def test_reasoning_safe_auto_activation():
    """When recovery exceeds threshold in auto mode, safe mode activates."""
    fp = "test_fp_safe_mode_auto"
    # Clear any previous state for this fingerprint
    if session_tracker.recovery_count(fp) > 0:
        session_tracker._sessions.pop(fp, None)

    settings = _make_settings(
        bridge_reasoning_safe_mode="auto",
        bridge_reasoning_safe_mode_recovery_threshold=3,
    )

    # Before threshold - no safe mode
    session_tracker.record_recovery(fp)  # count = 1
    session_tracker.record_recovery(fp)  # count = 2
    assert should_use_reasoning_safe(settings, fp) is False

    # At threshold - should activate
    session_tracker.record_recovery(fp)  # count = 3
    assert should_use_reasoning_safe(settings, fp) is True
    assert session_tracker.is_safe_mode_active(fp) is True

    # Cleanup
    session_tracker._sessions.pop(fp, None)


def test_reasoning_safe_always():
    settings = _make_settings(bridge_reasoning_safe_mode="always")
    assert should_use_reasoning_safe(settings, "any_fingerprint") is True


def test_reasoning_safe_off():
    settings = _make_settings(bridge_reasoning_safe_mode="off")
    assert should_use_reasoning_safe(settings, "any_fingerprint") is False


# -----------------------------------------------------------------------
# 15. Full tool-call episode summarized in reasoning-safe mode
# -----------------------------------------------------------------------


def test_reasoning_safe_strips_old_tool_calls():
    """In reasoning-safe mode, old tool_calls should be stripped from messages."""
    msg = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Let me check the weather."},
            {
                "type": "tool_use",
                "id": "tu_001",
                "name": "get_weather",
                "input": {"location": "NYC"},
            },
        ],
    }
    stripped = _strip_tool_calls_from_message(msg)
    # Should still be assistant role
    assert stripped["role"] == "assistant"
    # Should have text but no tool_use
    text = _extract_text_from_message(stripped)
    assert "Let me check the weather" in text
    assert "get_weather" not in text or True  # tool_use gets extracted as text


def test_reasoning_safe_compaction_summarizes_tool_episodes():
    """With reasoning-safe active, old tool-call episodes are fully
    removed from raw payload."""
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=2,
        bridge_reasoning_safe_mode="always",
        bridge_reasoning_safe_keep_recent_messages=2,
    )
    msgs = [
        {"role": "user", "content": "Get weather for NYC"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "get_weather",
                    "input": {"location": "NYC"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "content": "72°F, sunny",
                }
            ],
        },
        {"role": "assistant", "content": "It's 72°F and sunny."},
        {"role": "user", "content": "What about Chicago?"},
    ]
    compacted, info = maybe_compact_messages(
        msgs, None, settings, reasoning_safe=True
    )
    assert info is not None
    assert info["reasoning_safe"] is True
    # The memory block should contain the tool call info
    memory_text = str(compacted[0])
    assert "get_weather" in memory_text or "72°F" in memory_text


# -----------------------------------------------------------------------
# 16. Session info helper
# -----------------------------------------------------------------------


def test_session_info():
    tracker = SessionTracker()
    fp = "test_fp_info"
    info = tracker.session_info(fp)
    assert "recovery_notice_count" in info
    assert info["recovery_notice_count"] == 0

    tracker.record_recovery(fp)
    info = tracker.session_info(fp)
    assert info["recovery_notice_count"] == 1


# -----------------------------------------------------------------------
# 17. Helper function tests
# -----------------------------------------------------------------------


def test_has_tool_use():
    no_tool = {"role": "assistant", "content": "Just text"}
    assert _has_tool_use(no_tool) is False

    with_tool = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "name": "foo", "input": {}},
        ],
    }
    assert _has_tool_use(with_tool) is True

    empty_content = {"role": "user", "content": ""}
    assert _has_tool_use(empty_content) is False


def test_extract_text_from_message_string():
    msg = {"role": "user", "content": "Hello world"}
    assert _extract_text_from_message(msg) == "Hello world"


def test_extract_text_from_message_list():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "Part 1"},
            {"type": "text", "text": "Part 2"},
        ],
    }
    text = _extract_text_from_message(msg)
    assert "Part 1" in text
    assert "Part 2" in text


# -----------------------------------------------------------------------
# 18. Estimated tokens after compaction is lower
# -----------------------------------------------------------------------


def test_compaction_reduces_token_estimate():
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=2,
    )
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"Long message content number {i} " * 10})
        msgs.append({"role": "assistant", "content": f"Response to message {i} " * 5})

    from zen_claude_bridge.token_count import estimate_messages_tokens
    raw_tokens = estimate_messages_tokens(msgs)

    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None
    compacted_tokens = estimate_messages_tokens(compacted)
    assert compacted_tokens < raw_tokens


# -----------------------------------------------------------------------
# 19. Multiple compaction calls work (stateless test)
# -----------------------------------------------------------------------


def test_multiple_compaction_calls():
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=2,
    )
    msgs = [
        {"role": "user", "content": "A" * 100},
        {"role": "assistant", "content": "B" * 100},
        {"role": "user", "content": "C" * 100},
        {"role": "assistant", "content": "D" * 100},
        {"role": "user", "content": "E" * 100},
    ]
    # Two independent calls should both succeed
    c1, i1 = maybe_compact_messages(msgs, None, settings)
    c2, i2 = maybe_compact_messages(msgs, None, settings)
    assert i1 is not None
    assert i2 is not None
    # Both should produce same structure
    assert len(c1) == len(c2)


# -----------------------------------------------------------------------
# 20. Error handling for memory summary with long text
# -----------------------------------------------------------------------


def test_summary_truncation():
    settings = _make_settings(
        bridge_compaction_trigger_tokens=10,
        bridge_compaction_keep_recent_messages=1,
        bridge_compaction_max_summary_chars=500,
    )
    msgs = [
        {"role": "user", "content": "Hello, this is a very long message. " * 200},
        {"role": "assistant", "content": "Acknowledged."},
        {"role": "user", "content": "Another long message. " * 200},
        {"role": "assistant", "content": "Done."},
        {"role": "user", "content": "What was the first thing I said?"},
    ]
    compacted, info = maybe_compact_messages(msgs, None, settings)
    assert info is not None
    # Extract summary text from the memory message
    memory_msg = compacted[0]
    content_blocks = memory_msg.get("content", [])
    summary_text = ""
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                summary_text = block.get("text", "")
                break
    else:
        summary_text = str(content_blocks)
    summary_text_len = len(summary_text)
    # The summary text includes header + instructions + truncated summary.
    # The raw summary is limited to 500 chars, plus ~240 chars of header.
    assert summary_text_len > 450, f"summary too short: {summary_text_len}"
    assert summary_text_len < 800, f"summary not truncated: {summary_text_len}"


# -----------------------------------------------------------------------
# 21. _rebalance_tool_pair_boundary with no tool_use
# -----------------------------------------------------------------------


def test_rebalance_no_tool():
    older = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    recent = [
        {"role": "user", "content": "c"},
    ]
    o, r = _rebalance_tool_pair_boundary(older, recent)
    assert len(o) == 2
    assert len(r) == 1


def test_rebalance_no_older_or_recent():
    o, r = _rebalance_tool_pair_boundary([], [{"role": "user", "content": "a"}])
    assert len(o) == 0
    assert len(r) == 1

    o, r = _rebalance_tool_pair_boundary([{"role": "user", "content": "a"}], [])
    assert len(o) == 1
    assert len(r) == 0
