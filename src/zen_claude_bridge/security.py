"""Authentication and safe-logging utilities."""

import re
from typing import Optional

from fastapi import Header, HTTPException, status

from .config import settings


async def verify_bearer(authorization: Optional[str] = Header(None)) -> None:
    """Reject requests that do not carry a valid bearer token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if token != settings.claude_gateway_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def redact_secrets(text: str) -> str:
    """Replace likely secret strings with [REDACTED] for safe logging."""
    # Replace common bearer tokens and API keys in headers and body
    text = re.sub(r"(?i)(Bearer\s+)(sk-\w+|[\w-]{20,})", r"\1[REDACTED]", text)
    text = re.sub(
        r'(?i)("x-api-key"\s*:\s*")([^"]+)', r"\1[REDACTED]", text
    )
    text = re.sub(r"(?i)(api[_-]?key[=:]\s*)[\w-]{8,}", r"\1[REDACTED]", text)
    return text
