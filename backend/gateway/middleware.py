from __future__ import annotations

import threading
import time
from collections import deque

from django.conf import settings
from django.http import JsonResponse


_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}


def _client_ip(request) -> str:
    # Do not trust X-Forwarded-For until a trusted proxy allowlist is configured.
    return request.META.get("REMOTE_ADDR") or "unknown"


def _consume(key: str, now: float, limit: int, window: float) -> tuple[bool, int, int]:
    with _lock:
        bucket = _hits.setdefault(key, deque())
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(bucket[0] + window - now + 0.999))
            return False, 0, retry_after
        bucket.append(now)
        return True, max(0, limit - len(bucket)), 0


class ApiGatewayMiddleware:
    """Prototype BFF boundary: session identity and process-local API throttling."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        limit = max(1, int(settings.API_RATE_LIMIT_PER_MINUTE))
        window = 60.0
        now = time.monotonic()
        ip = _client_ip(request)
        session_key = getattr(getattr(request, "session", None), "session_key", None)
        keys = [f"ip:{ip}"]
        if session_key:
            keys.append(f"session:{session_key}")
        remaining = limit
        for key in keys:
            allowed, current_remaining, retry_after = _consume(key, now, limit, window)
            remaining = min(remaining, current_remaining)
            if not allowed:
                response = JsonResponse(
                    {
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many API requests; retry later",
                        },
                        "retry_after_seconds": retry_after,
                    },
                    status=429,
                )
                response["Retry-After"] = str(retry_after)
                response["X-RateLimit-Limit"] = str(limit)
                response["X-RateLimit-Remaining"] = "0"
                return response

        response = self.get_response(request)
        response["X-RateLimit-Limit"] = str(limit)
        response["X-RateLimit-Remaining"] = str(remaining)
        return response
