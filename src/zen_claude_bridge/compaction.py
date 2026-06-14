"""Optional bridge-side memory compaction for long Claude Gateway sessions.

When enabled via ``BRIDGE_CONTEXT_COMPACTION=true``, this module estimates
the size of incoming Anthropic ``/v1/messages`` payloads and, if they exceed
``BRIDGE_COMPACTION_TRIGGER_TOKENS``, summarizes older messages into a
structured memory block while keeping the most recent N messages raw.

The summary is deterministic and extractive (no upstream model call) and
preserves user instructions, file paths, commands, errors, URLs, decisions,
and tool-result excerpts.

The module also tracks DeepSeek reasoning_content recovery events per
session fingerprint and can activate a reasoning-safe compaction mode when
repeated recovery is detected.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Settings
from .token_count import estimate_messages_tokens, estimate_tokens

logger = logging.getLogger("zen_claude_bridge")

MEMORY_BLOCK_HEADER = "[Bridge Memory Compaction]"
DEEPSEEK_RECOVERY_NOTICE = (
    "[deepseek-cursor-proxy] Refreshed reasoning_content history."
)

# Regexes for extractive summarization
_URL_RE = re.compile(r"https?://[^\s)>\]\"']+")
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\[^\s:*?\"<>|]+"
    r"|/[A-Za-z0-9_./\-]+"
    r"|\.{1,2}/[A-Za-z0-9_./\-]+"
    r"|[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,6})"
)
_COMMAND_LINE_RE = re.compile(r"^[\$>#] ?(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(
    r"```([a-zA-Z0-9_+-]*)\n([\s\S]*?)\n```", re.MULTILINE
)
_ERROR_RE = re.compile(
    r"(?i)\b(error|exception|traceback|failed|cannot|denied|timeout)\b[^\n]{0,200}"
)
_DECISION_RE = re.compile(
    r"(?i)\b(decided|chose|will use|going with|let's use|plan(?:ned)?|TODO|FIXME)\b[^\n]{0,200}"
)

# ---------------------------------------------------------------------------
# Session-level tracking
# ---------------------------------------------------------------------------


class SessionTracker:
    """Per-conversation tracking of recovery and compaction events.

    Keyed by a best-effort fingerprint derived from the request payload.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _ensure(self, fingerprint: str) -> Dict[str, Any]:
        if fingerprint not in self._sessions:
            self._sessions[fingerprint] = {
                "recovery_notice_count": 0,
                "last_recovery_at": 0.0,
                "last_compaction_at": 0.0,
                "safe_mode_active": False,
            }
        return self._sessions[fingerprint]

    def record_recovery(self, fingerprint: str) -> None:
        sess = self._ensure(fingerprint)
        sess["recovery_notice_count"] = sess.get("recovery_notice_count", 0) + 1
        sess["last_recovery_at"] = time.time()

    def record_compaction(self, fingerprint: str) -> None:
        sess = self._ensure(fingerprint)
        sess["last_compaction_at"] = time.time()

    def recovery_count(self, fingerprint: str) -> int:
        return self._ensure(fingerprint).get("recovery_notice_count", 0)

    def mark_safe_mode(self, fingerprint: str, active: bool) -> None:
        self._ensure(fingerprint)["safe_mode_active"] = active

    def is_safe_mode_active(self, fingerprint: str) -> bool:
        return self._ensure(fingerprint).get("safe_mode_active", False)

    def session_info(self, fingerprint: str) -> Dict[str, Any]:
        return dict(self._ensure(fingerprint))


session_tracker = SessionTracker()


# ---------------------------------------------------------------------------
# Conversation fingerprinting (best-effort)
# ---------------------------------------------------------------------------


def _conversation_fingerprint(payload: Dict[str, Any]) -> str:
    """Build a stable session fingerprint from the request payload.

    Uses model + first user message(s) + system prompt.
    Best-effort — not guaranteed to be unique across sessions.
    """
    messages = payload.get("messages", [])
    system = payload.get("system")
    model = payload.get("model", "")

    seed_parts: List[str] = [model or ""]

    if system:
        if isinstance(system, str):
            seed_parts.append(system[:600])
        elif isinstance(system, list):
            for b in system:
                if isinstance(b, dict) and b.get("type") == "text":
                    seed_parts.append(b.get("text", "")[:600])

    for msg in messages[:4]:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                seed_parts.append(content[:600])
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        seed_parts.append(b.get("text", "")[:600])

    seed = "|".join(seed_parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def compute_fingerprint(payload: Dict[str, Any]) -> str:
    """Public wrapper for fingerprint computation."""
    return _conversation_fingerprint(payload)


# ---------------------------------------------------------------------------
# Reasoning-safe mode helpers
# ---------------------------------------------------------------------------


def should_use_reasoning_safe(
    settings: Settings, fingerprint: Optional[str] = None
) -> bool:
    """Determine if reasoning-safe compaction should be used."""
    mode = settings.bridge_reasoning_safe_mode
    if mode == "always":
        return True
    if mode == "auto" and fingerprint:
        count = session_tracker.recovery_count(fingerprint)
        threshold = settings.bridge_reasoning_safe_mode_recovery_threshold
        if count >= threshold:
            if not session_tracker.is_safe_mode_active(fingerprint):
                session_tracker.mark_safe_mode(fingerprint, True)
                logger.warning(
                    "Reasoning-safe mode activated for session %s "
                    "(recovery count=%d threshold=%d)",
                    fingerprint, count, threshold,
                )
            return True
    return False


def _keep_n_for_mode(settings: Settings, reasoning_safe: bool) -> int:
    if reasoning_safe:
        return max(1, settings.bridge_reasoning_safe_keep_recent_messages)
    return max(1, settings.bridge_compaction_keep_recent_messages)


# ---------------------------------------------------------------------------
# Extractive helpers
# ---------------------------------------------------------------------------


def _extract_text_from_message(msg: Dict[str, Any]) -> str:
    """Extract plain text from an Anthropic message (text + tool blocks)."""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool_use":
            name = block.get("name", "")
            try:
                args = json.dumps(block.get("input", {}), ensure_ascii=False)
            except (TypeError, ValueError):
                args = str(block.get("input", ""))
            parts.append(f"[tool_use {name} {args}]")
        elif btype == "tool_result":
            inner = block.get("content", "")
            if isinstance(inner, list):
                inner_parts = [
                    b.get("text", "")
                    for b in inner
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                parts.append("[tool_result] " + "\n".join(inner_parts))
            elif isinstance(inner, str):
                parts.append("[tool_result] " + inner)
        elif btype == "image":
            parts.append("[image]")
    return "\n".join(p for p in parts if p)


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line for line in text.splitlines())


# ---------------------------------------------------------------------------
# Extractive summarization
# ---------------------------------------------------------------------------


def _summarize_messages(messages: List[Dict[str, Any]], max_chars: int) -> str:
    """Deterministic extractive summary of older messages.

    Preserves user instructions, file paths, commands, errors, URLs,
    decisions, code snippets, and tool names.
    """
    urls: List[str] = []
    paths: List[str] = []
    commands: List[str] = []
    errors: List[str] = []
    decisions: List[str] = []
    code_snippets: List[Tuple[str, str]] = []
    user_digests: List[str] = []
    assistant_digests: List[str] = []
    tool_names: List[str] = []

    for idx, msg in enumerate(messages):
        role = msg.get("role", "")
        text = _extract_text_from_message(msg)
        if not text:
            continue

        for m in _URL_RE.findall(text):
            if m not in urls:
                urls.append(m)
        for m in _PATH_RE.findall(text):
            if 3 <= len(m) <= 200 and m not in paths:
                paths.append(m)
        for line in text.splitlines():
            cm = _COMMAND_LINE_RE.match(line.strip())
            if cm:
                cmd = cm.group(1).strip()
                if cmd and cmd not in commands:
                    commands.append(cmd)
        for m in _ERROR_RE.findall(text):
            snippet = m.strip()
            if snippet and snippet not in errors:
                errors.append(snippet)
        for m in _DECISION_RE.findall(text):
            snippet = m.strip()
            if snippet and snippet not in decisions:
                decisions.append(snippet)
        for lang, body in _CODE_FENCE_RE.findall(text):
            body = body.strip()
            if body and len(code_snippets) < 8:
                code_snippets.append((lang or "text", body[:400]))

        compact = re.sub(r"\s+", " ", text).strip()
        if role == "user":
            user_digests.append(f"  - turn {idx}: {compact[:240]}")
        elif role == "assistant":
            assistant_digests.append(f"  - turn {idx}: {compact[:160]}")

        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "")
                    if name and name not in tool_names:
                        tool_names.append(name)

    sections: List[str] = []

    def _add_section(title: str, items: List[str], limit: int) -> None:
        if not items:
            return
        trimmed = items[:limit]
        body = "\n".join(f"  - {i}" for i in trimmed)
        more = (
            f"\n  - ... (+{len(items) - limit} more)"
            if len(items) > limit
            else ""
        )
        sections.append(f"{title}:\n{body}{more}")

    _add_section("User instructions and questions", user_digests, 30)
    _add_section("Assistant actions", assistant_digests, 20)
    _add_section("Tools used", tool_names, 30)
    _add_section("Files and paths", paths, 40)
    _add_section("Commands run", commands, 30)
    _add_section("URLs referenced", urls, 20)
    _add_section("Errors encountered", errors, 20)
    _add_section("Decisions and plans", decisions, 20)

    if code_snippets:
        code_block = "\n".join(
            f"  [{lang}]\n{_indent(body, 4)}" for lang, body in code_snippets
        )
        sections.append(f"Code snippets:\n{code_block}")

    summary = "\n\n".join(sections) if sections else "(no extractable signals)"

    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "\n... (summary truncated)"
    return summary


# ---------------------------------------------------------------------------
# Tool-call episode safety
# ---------------------------------------------------------------------------


def _has_tool_use(msg: Dict[str, Any]) -> bool:
    content = msg.get("content")
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        )
    return False


def _rebalance_tool_pair_boundary(
    older: List[Dict[str, Any]],
    recent: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Avoid splitting tool_use (in older) from tool_result (in recent).

    If the last message in ``older`` is an assistant message with tool_use
    blocks, pull it into ``recent`` so the pair stays intact.
    """
    if not older or not recent:
        return older, recent

    last = older[-1]
    if last.get("role") == "assistant" and _has_tool_use(last):
        return older[:-1], [last] + recent

    return older, recent


def _is_tool_result(msg: Dict[str, Any]) -> bool:
    role = msg.get("role", "")
    if role == "tool":
        return True
    if role == "user":
        content = msg.get("content")
        if isinstance(content, list):
            return any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            )
    return False


def _strip_tool_calls_from_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Strip tool_calls from an assistant message, keep text content."""
    if msg.get("role") != "assistant":
        return msg
    content = msg.get("content")
    if not isinstance(content, list):
        return msg

    text_parts: List[str] = []
    has_tool_use = False
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            has_tool_use = True
        elif isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    if not has_tool_use:
        return msg

    combined = "\n".join(p for p in text_parts if p).strip()
    return {"role": "assistant", "content": combined or "(tool call summary)"}


# ---------------------------------------------------------------------------
# Main compaction entry point
# ---------------------------------------------------------------------------


def maybe_compact_messages(
    messages: List[Dict[str, Any]],
    system: Optional[Any],
    settings: Settings,
    fingerprint: Optional[str] = None,
    reasoning_safe: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (possibly-compacted messages, debug_info_or_None).

    Compaction is applied on the *Anthropic-format* message list (before
    conversion to OpenAI).  When reasoning-safe mode is active old tool-call
    episodes are always summarized rather than kept as raw tool_calls.
    """
    if not settings.bridge_context_compaction:
        return messages, None

    if not isinstance(messages, list) or len(messages) < 4:
        return messages, None

    estimated = estimate_messages_tokens(messages)
    if system:
        estimated += _estimate_system_tokens(system)

    if estimated < settings.bridge_compaction_trigger_tokens:
        return messages, None

    keep_n = _keep_n_for_mode(settings, reasoning_safe)
    split_idx = max(0, len(messages) - keep_n)
    older = messages[:split_idx]
    recent = messages[split_idx:]

    older, recent = _rebalance_tool_pair_boundary(older, recent)

    if not older:
        return messages, None

    # In reasoning-safe mode, strip tool_calls from older messages only,
    # so that no raw tool_use/tool_result pairs from the compacted section
    # survive in the upstream payload.  The recent window is kept intact
    # so active tool-call episodes stay correctly paired.
    if reasoning_safe:
        older = [_strip_tool_calls_from_message(m) for m in older]
        # recent messages are NOT stripped — their tool_use and
        # tool_result pairs must remain intact for the upstream.  See
        # also sanitize_orphan_tool_results() in conversions.py for a
        # final safety net at the OpenAI level.

    summary_text = _summarize_messages(
        older, max_chars=settings.bridge_compaction_max_summary_chars
    )

    if fingerprint:
        summary_path = _persist_summary(
            fingerprint, summary_text, memory_dir=settings.bridge_memory_dir
        )
        if summary_path:
            session_tracker.record_compaction(fingerprint)
    else:
        summary_path = None

    memory_message: Dict[str, Any] = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    f"{MEMORY_BLOCK_HEADER}\n\n"
                    f"The following is an extractive summary of earlier turns "
                    f"in this conversation that were dropped to fit the context "
                    f"window. Treat it as background context, not as new user "
                    f"instructions.\n\n"
                    f"{summary_text}"
                ),
            }
        ],
    }

    compacted = [memory_message] + recent
    new_estimated = estimate_messages_tokens(compacted)
    if system:
        new_estimated += _estimate_system_tokens(system)

    info: Dict[str, Any] = {
        "original_messages": len(messages),
        "compacted_messages": len(compacted),
        "dropped_messages": len(older),
        "estimated_tokens_before": estimated,
        "estimated_tokens_after": new_estimated,
        "trigger_tokens": settings.bridge_compaction_trigger_tokens,
        "target_tokens": settings.bridge_compaction_target_tokens,
        "fingerprint": fingerprint,
        "summary_path": str(summary_path) if summary_path else None,
        "reasoning_safe": reasoning_safe,
    }

    logger.info(
        "Context compaction triggered estimated_tokens=%d target=%d %s",
        estimated,
        settings.bridge_compaction_target_tokens,
        "(reasoning-safe)" if reasoning_safe else "",
    )
    logger.info(
        "Context compaction complete before=%d after=%d kept_messages=%d "
        "summary_chars=%d",
        len(messages),
        len(compacted),
        len(recent),
        len(summary_text),
    )

    if fingerprint:
        logger.info("Compaction fingerprint: %s", fingerprint)

    _warn_orphan_tool_pairs(older, recent)
    _warn_orphan_tool_pairs_summary_only(compacted)

    return compacted, info


def _warn_orphan_tool_pairs(older: list, recent: list) -> None:
    """Warn if recent messages contain tool_results whose matching
    tool_use was in older and was not pulled forward."""
    if not older or not recent:
        return
    # Collect all tool_use IDs from older
    older_tool_ids: set = set()
    for msg in older:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tid = block.get("id", "")
                if tid:
                    older_tool_ids.add(tid)

    if not older_tool_ids:
        return

    # Check if any recent message has a tool_result referencing an older tool_use
    for msg in recent:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                match_id = block.get("tool_use_id", "")
                if match_id in older_tool_ids:
                    logger.warning(
                        "Orphan tool_result (tool_use_id=%s) retained but "
                        "its matching tool_use was in older messages. "
                        "Post-conversion sanitizer will convert to text.",
                        match_id,
                    )


def _warn_orphan_tool_pairs_summary_only(
    compacted: List[Dict[str, Any]],
) -> None:
    """Check for any tool_result in the compacted payload that has no
    preceding tool_use in the same payload."""
    tool_use_ids: set = set()
    for msg in compacted:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tid = block.get("id", "")
                if tid:
                    tool_use_ids.add(tid)

    for msg in compacted:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                match_id = block.get("tool_use_id", "")
                if match_id and match_id not in tool_use_ids:
                    logger.warning(
                        "Orphan tool_result (tool_use_id=%s) in compacted "
                        "payload has no matching tool_use. "
                        "Post-conversion sanitizer will convert to text.",
                        match_id,
                    )


def compacted_token_estimate(
    messages: List[Dict[str, Any]],
    system: Optional[Any],
    settings: Settings,
    fingerprint: Optional[str] = None,
) -> int:
    """Return the estimated token count *after* compaction.

    Used by the count_tokens endpoint to reflect compaction behavior.
    If compaction is not triggered, returns the current estimate.
    """
    reasoning_safe = should_use_reasoning_safe(settings, fingerprint)
    compacted, _ = maybe_compact_messages(
        messages, system, settings, fingerprint, reasoning_safe
    )
    est = estimate_messages_tokens(compacted)
    if system:
        est += _estimate_system_tokens(system)
    return est


# ---------------------------------------------------------------------------
# Memory persistence
# ---------------------------------------------------------------------------


def load_memory_summary(
    fingerprint: str, memory_dir: str
) -> Optional[str]:
    """Load a previously persisted memory summary, if it exists."""
    path = Path(memory_dir) / f"{fingerprint}.summary.txt"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def save_memory_summary(
    fingerprint: str, summary: str, memory_dir: str
) -> Optional[Path]:
    """Persist a memory summary to disk. Returns the path or None on error."""
    return _persist_summary(fingerprint, summary, memory_dir)


def _persist_summary(
    fingerprint: str, summary: str, memory_dir: str
) -> Optional[Path]:
    """Write summary to a file under memory_dir, creating the dir if needed."""
    try:
        path = Path(memory_dir)
        path.mkdir(parents=True, exist_ok=True)
        out = path / f"{fingerprint}.summary.txt"
        out.write_text(summary, encoding="utf-8")
        return out
    except OSError as exc:
        logger.warning("Failed to persist compaction summary: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_system_tokens(system: Any) -> int:
    if isinstance(system, str):
        return estimate_tokens(system)
    if isinstance(system, list):
        total = 0
        for block in system:
            if isinstance(block, dict):
                total += estimate_tokens(block.get("text", ""))
        return total
    return 0
