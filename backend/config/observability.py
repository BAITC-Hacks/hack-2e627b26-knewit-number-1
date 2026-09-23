from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import JsonResponse


logger = logging.getLogger("app.observability")
_request_context: ContextVar[dict[str, Any] | None] = ContextVar("request_context", default=None)


def _safe_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(f"{settings.SECRET_KEY}:{value}".encode("utf-8")).hexdigest()[:16]


def safe_identifier(value: Any) -> str | None:
    """Return a short, non-reversible identifier suitable for logs."""
    return _safe_hash(str(value)) if value is not None else None


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def observe(self, name: str, milliseconds: float) -> None:
        with self._lock:
            values = self._latencies.setdefault(name, [])
            values.append(round(milliseconds, 3))
            if len(values) > 2000:
                del values[: len(values) - 2000]

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1))))
        return ordered[index]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            latency_values = {key: list(value) for key, value in self._latencies.items()}
        return {
            "counters": counters,
            "latency_ms": {
                key: {
                    "p50": self._percentile(values, 50),
                    "p95": self._percentile(values, 95),
                    "p99": self._percentile(values, 99),
                    "samples": len(values),
                }
                for key, values in latency_values.items()
            },
        }


metrics = MetricsRegistry()


def current_context() -> dict[str, Any]:
    return dict(_request_context.get() or {})


def record_metric(name: str, amount: int = 1) -> None:
    metrics.increment(name, amount)


def observe_latency(name: str, milliseconds: float) -> None:
    metrics.observe(name, milliseconds)


def mark_cache(hit: bool) -> None:
    record_metric("cache_hits_total" if hit else "cache_misses_total")


def record_event(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "trace_id": current_context().get("trace_id"),
        "session_id": current_context().get("session_id"),
        "intent": current_context().get("intent"),
        "prompt_version": settings.PROMPT_VERSION,
        "model_version": settings.MODEL_VERSION,
        "index_version": settings.CATALOG_INDEX_VERSION,
        "rule_version": settings.AVAILABILITY_RULE_VERSION,
        **fields,
    }
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _intent(path: str) -> str:
    if "/dialog" in path:
        return "dialog"
    if "/search/semantic" in path:
        return "semantic_search"
    if "/search" in path:
        return "search"
    if "/products/detail" in path:
        return "product_detail"
    if "/products" in path:
        return "catalog_list"
    if "/cart" in path:
        return "cart"
    if "health" in path or "ready" in path or "metrics" in path:
        return "observability"
    return "http"


class ObservabilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        trace_id = request.headers.get("X-Request-ID")
        if not trace_id or len(trace_id) > 128 or any(char.isspace() for char in trace_id):
            trace_id = uuid.uuid4().hex
        session_key = getattr(getattr(request, "session", None), "session_key", None)
        context = {
            "trace_id": trace_id,
            "session_id": _safe_hash(session_key),
            "intent": _intent(request.path),
        }
        token = _request_context.set(context)
        record_metric("http_requests_total")
        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            status_code = getattr(response, "status_code", 500)
            observe_latency("http_request", duration_ms)
            record_metric(f"http_responses_{status_code}_total")
            record_event(
                "http.request.completed",
                status_code=status_code,
                duration_ms=round(duration_ms, 3),
                cache_hit=current_context().get("cache_hit"),
                stage_durations_ms=current_context().get("stage_durations_ms", {}),
            )
            if response is not None:
                response["X-Request-ID"] = trace_id
            _request_context.reset(token)


def add_stage(name: str, started: float) -> None:
    context = _request_context.get()
    if context is not None:
        stages = context.setdefault("stage_durations_ms", {})
        stages[name] = round((time.perf_counter() - started) * 1000, 3)


def set_cache_hit(hit: bool) -> None:
    context = _request_context.get()
    if context is not None:
        context["cache_hit"] = hit
    mark_cache(hit)


def metrics_payload() -> dict[str, Any]:
    payload = metrics.snapshot()
    try:
        sync_path = Path(settings.CATALOG_SYNC_STATUS_PATH)
        status = json.loads(sync_path.read_text(encoding="utf-8"))
        payload["last_sync"] = {
            "last_successful_sync": status.get("last_successful_sync"),
            "last_status": status.get("last_status"),
            "products": status.get("last_successful_products"),
            "pages": status.get("last_successful_pages"),
            "errors": status.get("last_errors"),
            "duration_seconds": status.get("last_duration_seconds"),
        }
    except (OSError, json.JSONDecodeError):
        payload["last_sync"] = {"last_successful_sync": None}
    return payload


def readiness_payload() -> tuple[dict[str, Any], int]:
    provider = settings.CATALOG_PROVIDER
    provider_configured = provider != "ekt" or bool(settings.EKT_API_USERNAME and settings.EKT_API_PASSWORD)
    index_ready = Path(settings.CATALOG_INDEX_PATH).exists()
    ready = provider_configured and index_ready
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "provider_configured": provider_configured,
            "catalog_index": index_ready,
        },
        "catalog_provider": provider,
    }, (200 if ready else 503)


def metrics_response(request):
    del request
    return JsonResponse(metrics_payload())


def readiness_response(request):
    del request
    payload, status = readiness_payload()
    return JsonResponse(payload, status=status)
