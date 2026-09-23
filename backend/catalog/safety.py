from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


_DANGEROUS_SCHEME = re.compile(r"^(?:javascript|data|vbscript):", re.IGNORECASE)
_HTML_BLOCK = re.compile(r"<\s*(?:script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*(?:script|style|iframe|object|embed)\s*>", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_MARKDOWN_DANGEROUS_LINK = re.compile(
    r"(!?\[[^\]]*\])\(\s*(?:javascript|data|vbscript):[^)]*\)", re.IGNORECASE
)


def sanitize_text(value: Any) -> str:
    text = str(value)
    text = _HTML_BLOCK.sub(" ", text)
    text = _MARKDOWN_DANGEROUS_LINK.sub(r"\1", text)
    return _HTML_TAG.sub(" ", text).replace("\x00", "").strip()


def sanitize_url(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if _DANGEROUS_SCHEME.match(value.strip()):
        return None
    if not parsed.scheme:
        return value if value.startswith("/") and not value.startswith("//") else None
    if parsed.scheme != "https" or parsed.hostname not in {"ekt.kz", "www.ekt.kz"}:
        return None
    if parsed.username or parsed.password or parsed.fragment:
        return None
    return value


def sanitize_catalog_value(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize_catalog_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_catalog_value(item) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    if _DANGEROUS_SCHEME.match(value.strip()) or value.strip().startswith(("/", "https://", "http://")):
        parsed = urlsplit(value.strip())
        if parsed.scheme or value.strip().startswith("/"):
            return sanitize_url(value)
    return sanitize_text(value)


def sanitize_catalog_payload(payload: Any) -> Any:
    """Treat catalog/files/pages as data; never return executable markup or URLs."""
    return sanitize_catalog_value(payload)
