from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from dialog.payment_safety import redact_payment_data


class LlmUnavailable(Exception):
    """A safe operational error: its text is never passed to chat users."""


def _extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = payload.get("output")
    if not isinstance(output, list):
        raise LlmUnavailable()
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    result = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not result:
        raise LlmUnavailable()
    return result


class OpenAIResponsesClient:
    """Small Responses API client with an injectable transport for tests."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_settings(cls) -> "OpenAIResponsesClient":
        if settings.ASSISTANT_LLM_PROVIDER != "openai":
            raise LlmUnavailable()
        if not settings.OPENAI_API_KEY or not settings.OPENAI_MODEL:
            raise LlmUnavailable()
        return cls(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )

    def create_response(self, *, instructions: str, input_text: str) -> str:
        # Keep the external-provider boundary safe even for non-HTTP callers.
        input_text = redact_payment_data(input_text)
        body = json.dumps(
            {
                "model": self.model,
                "instructions": instructions,
                "input": input_text,
                "store": False,
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed HTTPS endpoint
                raw = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise LlmUnavailable() from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LlmUnavailable() from exc
        if not isinstance(payload, dict):
            raise LlmUnavailable()
        return _extract_output_text(payload)
