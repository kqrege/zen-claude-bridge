"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from typing import List


# Allowed model names that Claude Desktop / Claude Code Gateway may request.
# All are aliased to the configured DEEPSEEK_MODEL upstream.
CLAUDE_MODEL_ALIASES: List[str] = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-haiku-4-5-latest",
    "claude-3-5-haiku-latest",
    "claude-3-5-sonnet-latest",
    "claude-opus-4-1",
    "deepseek-v4-flash-free",
    "deepseek-v4-flash",
]


@dataclass
class Settings:
    claude_gateway_key: str = field(
        default_factory=lambda: os.environ.get("CLAUDE_GATEWAY_KEY", "sk-local-zen")
    )
    opencode_zen_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENCODE_ZEN_API_KEY", "")
    )
    deepseek_upstream_url: str = field(
        default_factory=lambda: os.environ.get(
            "DEEPSEEK_UPSTREAM_URL",
            "http://127.0.0.1:9000/v1/chat/completions",
        )
    )
    deepseek_model: str = field(
        default_factory=lambda: os.environ.get(
            "DEEPSEEK_MODEL", "deepseek-v4-flash-free"
        )
    )
    deepseek_proxy_host: str = field(
        default_factory=lambda: os.environ.get(
            "DEEPSEEK_PROXY_HOST", "127.0.0.1"
        )
    )
    deepseek_proxy_port: int = field(
        default_factory=lambda: int(
            os.environ.get("DEEPSEEK_PROXY_PORT", "9000")
        )
    )
    bridge_host: str = field(
        default_factory=lambda: os.environ.get("BRIDGE_HOST", "127.0.0.1")
    )
    bridge_port: int = field(
        default_factory=lambda: int(os.environ.get("BRIDGE_PORT", "4000"))
    )
    request_timeout_seconds: int = field(
        default_factory=lambda: int(
            os.environ.get("REQUEST_TIMEOUT_SECONDS", "600")
        )
    )
    show_deepseek_recovery_notice: bool = field(
        default_factory=lambda: os.environ.get(
            "SHOW_DEEPSEEK_RECOVERY_NOTICE", "false"
        ).lower() in ("true", "1", "yes")
    )

    # ---------------------------------------------------------------
    # Optional bridge-side memory compaction
    # ---------------------------------------------------------------
    bridge_context_compaction: bool = field(
        default_factory=lambda: os.environ.get(
            "BRIDGE_CONTEXT_COMPACTION", "false"
        ).lower() in ("true", "1", "yes")
    )
    bridge_compaction_trigger_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("BRIDGE_COMPACTION_TRIGGER_TOKENS", "180000")
        )
    )
    bridge_compaction_target_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("BRIDGE_COMPACTION_TARGET_TOKENS", "120000")
        )
    )
    bridge_compaction_keep_recent_messages: int = field(
        default_factory=lambda: int(
            os.environ.get("BRIDGE_COMPACTION_KEEP_RECENT_MESSAGES", "20")
        )
    )
    bridge_compaction_max_summary_chars: int = field(
        default_factory=lambda: int(
            os.environ.get("BRIDGE_COMPACTION_MAX_SUMMARY_CHARS", "20000")
        )
    )
    bridge_memory_dir: str = field(
        default_factory=lambda: os.environ.get(
            "BRIDGE_MEMORY_DIR", ".bridge-memory"
        )
    )

    # ---------------------------------------------------------------
    # Optional DeepSeek reasoning recovery tracking
    # ---------------------------------------------------------------
    bridge_reasoning_recovery_tracking: bool = field(
        default_factory=lambda: os.environ.get(
            "BRIDGE_REASONING_RECOVERY_TRACKING", "true"
        ).lower() in ("true", "1", "yes")
    )
    bridge_reasoning_recovery_threshold: int = field(
        default_factory=lambda: int(
            os.environ.get("BRIDGE_REASONING_RECOVERY_THRESHOLD", "3")
        )
    )
    bridge_reasoning_safe_mode: str = field(
        default_factory=lambda: os.environ.get(
            "BRIDGE_REASONING_SAFE_MODE", "auto"
        ).lower()
    )
    bridge_reasoning_safe_mode_recovery_threshold: int = field(
        default_factory=lambda: int(
            os.environ.get(
                "BRIDGE_REASONING_SAFE_MODE_RECOVERY_THRESHOLD", "3"
            )
        )
    )
    bridge_reasoning_safe_keep_recent_messages: int = field(
        default_factory=lambda: int(
            os.environ.get(
                "BRIDGE_REASONING_SAFE_KEEP_RECENT_MESSAGES", "8"
            )
        )
    )

    @property
    def model_aliases(self) -> List[str]:
        return CLAUDE_MODEL_ALIASES


settings = Settings()
