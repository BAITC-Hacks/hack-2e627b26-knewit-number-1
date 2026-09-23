from __future__ import annotations

import copy
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from django.conf import settings

from catalog.analogs import find_analogs
from catalog.errors import CatalogError
from catalog.providers import get_catalog_provider
from catalog.safety import sanitize_catalog_payload, sanitize_text, sanitize_url
from catalog.search import SearchIndexError, search_catalog, semantic_search_catalog
from config.observability import observe_latency, record_event, record_metric
from knowledge_base.engine import answer_query


class ToolValidationError(ValueError):
    """The model supplied arguments that do not match the server contract."""


class ToolExecutionError(RuntimeError):
    """A typed tool failed without exposing upstream secrets or response bodies."""


MAX_TOOL_RESULTS = 5
MAX_TOOL_QUERY_LENGTH = 1200


TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "search_catalog",
        "description": (
            "Find up to five catalog candidates by id, article, name, purpose, or characteristics. "
            "Candidate data does not prove a current price or current availability; call get_product "
            "for every candidate whose price or availability will be presented."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["auto", "exact_fuzzy", "semantic"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["query", "mode", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_product",
        "description": (
            "Fetch the current server-side product detail. Its result may be used for current price "
            "and availability statements; search results may not."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "minimum": 1},
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_analogs",
        "description": (
            "Find compatible lighting alternatives using the approved compatibility matrix, then "
            "live-check every returned candidate. Other categories require manager review."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["product_id", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "query_knowledge_base",
        "description": (
            "Retrieve verified payment, delivery, pickup, power-of-attorney, or minimum-order terms. "
            "Conflicted and missing records require a qualification or manager escalation."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "language": {"type": "string", "enum": ["ru", "kk"]},
            },
            "required": ["query", "language"],
            "additionalProperties": False,
        },
    },
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _object(
    arguments: Any,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ToolValidationError("tool arguments must be a JSON object")
    allowed = required | (optional or set())
    unknown = set(arguments) - allowed
    missing = required - set(arguments)
    if unknown:
        raise ToolValidationError(f"unknown tool arguments: {', '.join(sorted(unknown))}")
    if missing:
        raise ToolValidationError(f"missing tool arguments: {', '.join(sorted(missing))}")
    return arguments


def _query(value: Any) -> str:
    if not isinstance(value, str):
        raise ToolValidationError("query must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > MAX_TOOL_QUERY_LENGTH:
        raise ToolValidationError("query must contain 1..1200 characters")
    return normalized


def _positive_int(value: Any, field: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolValidationError(f"{field} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ToolValidationError(f"{field} must not exceed {maximum}")
    return value


def _bounded_value(value: Any, depth: int = 0) -> Any:
    """Bound untrusted catalog data before it enters an LLM request."""
    if depth >= 6:
        return "[nested data omitted]"
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, list):
        return [_bounded_value(item, depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        return {
            str(key)[:200]: _bounded_value(item, depth + 1)
            for key, item in list(value.items())[:50]
        }
    return value


def _candidate(item: dict[str, Any]) -> dict[str, Any]:
    """Return searchable facts while deliberately excluding volatile commerce fields."""
    allowed = (
        "id",
        "name",
        "article",
        "category",
        "description",
        "properties",
        "image",
        "url",
        "url_api_detail",
        "match_type",
        "score",
        "explanation",
        "matched_parameters",
        "missing_required_parameters",
        "data_source",
    )
    return _bounded_value(
        sanitize_catalog_payload({key: item.get(key) for key in allowed if key in item})
    )


def _detail(item: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "id",
        "name",
        "article",
        "category",
        "description",
        "price",
        "currency",
        "properties",
        "availability",
        "image",
        "url",
        "url_api_detail",
        "certificates",
        "certificate",
        "documents",
        "instructions",
        "files",
        "offers",
        "data_source",
        "fixture_version",
    )
    result = _bounded_value(
        sanitize_catalog_payload({key: item.get(key) for key in allowed if key in item})
    )
    if result.get("data_source") == "fixture" and result.get("price") is not None:
        result.setdefault("currency", settings.CART_CURRENCY)
    return result


def _safe_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    raw_sources = result.get("sources")
    if isinstance(raw_sources, list):
        for source in raw_sources[:5]:
            if not isinstance(source, dict):
                continue
            url = source.get("source_url")
            safe_url = sanitize_url(url) if isinstance(url, str) and url else None
            sources.append(
                {
                    "source_url": safe_url,
                    "verified_at": str(source.get("verified_at") or ""),
                }
            )
    else:
        url = result.get("source_url")
        safe_url = sanitize_url(url) if isinstance(url, str) and url else None
        if safe_url or result.get("verified_at"):
            sources.append(
                {
                    "source_url": safe_url,
                    "verified_at": str(result.get("verified_at") or ""),
                }
            )
    return sources


class DialogToolRegistry:
    """Closed, typed tool registry. There is intentionally no generic HTTP tool."""

    def __init__(
        self,
        *,
        provider_factory: Callable[[], Any] = get_catalog_provider,
        index_path: Path | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._index_path = Path(index_path or settings.CATALOG_INDEX_PATH)

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(list(TOOL_DEFINITIONS))

    @property
    def names(self) -> frozenset[str]:
        return frozenset(definition["name"] for definition in TOOL_DEFINITIONS)

    def execute(self, name: Any, arguments: Any) -> dict[str, Any]:
        if not isinstance(name, str) or name not in self.names:
            record_metric("llm_tool_rejected_total")
            raise ToolValidationError("unknown or forbidden tool")
        started = time.perf_counter()
        try:
            handler = getattr(self, f"_tool_{name}")
            data = handler(arguments)
        except ToolValidationError:
            record_metric("llm_tool_validation_errors_total")
            record_event("llm.tool.completed", tool=name, status="rejected")
            raise
        except (CatalogError, SearchIndexError, ToolExecutionError, KeyError, OSError, ValueError) as exc:
            record_metric("llm_tool_errors_total")
            record_event("llm.tool.completed", tool=name, status="failed", error_type=type(exc).__name__)
            raise ToolExecutionError(f"{name} is temporarily unavailable") from exc
        duration_ms = (time.perf_counter() - started) * 1000
        observe_latency("llm_tool", duration_ms)
        record_metric("llm_tool_calls_total")
        record_event(
            "llm.tool.completed",
            tool=name,
            status="ok",
            duration_ms=round(duration_ms, 3),
        )
        return {
            "ok": True,
            "tool": name,
            "retrieved_at": _utc_now(),
            # Tool/catalog text is explicitly untrusted data, not instructions.
            "untrusted_data": data,
        }

    def _tool_search_catalog(self, arguments: Any) -> dict[str, Any]:
        values = _object(arguments, required={"query", "mode", "limit"})
        query = _query(values["query"])
        mode = values["mode"]
        if mode not in {"auto", "exact_fuzzy", "semantic"}:
            raise ToolValidationError("mode is not supported")
        limit = _positive_int(values["limit"], "limit", MAX_TOOL_RESULTS)
        if mode == "semantic":
            result = semantic_search_catalog(query, self._index_path, limit)
        else:
            result = search_catalog(query, self._index_path, limit)
            if mode == "auto" and not result.get("results"):
                result = semantic_search_catalog(query, self._index_path, limit)
        items = [
            _candidate(item)
            for item in result.get("results", [])[:limit]
            if isinstance(item, dict)
        ]
        return {
            "source": "local_official_catalog_index",
            "index_version": settings.CATALOG_INDEX_VERSION,
            "query": query,
            "mode": result.get("mode"),
            "candidates": items,
            "count": len(items),
            "volatile_fields_verified": False,
        }

    def _tool_get_product(self, arguments: Any) -> dict[str, Any]:
        values = _object(arguments, required={"product_id"})
        product_id = _positive_int(values["product_id"], "product_id")
        product = _detail(self._provider_factory().get_product(product_id))
        if product.get("id") != product_id:
            raise ToolExecutionError("catalog returned a different product")
        result = {
            "source": "catalog_detail_api",
            "source_ref": f"/api/products/detail?id={product_id}",
            "product": product,
            "price_verified": "price" in product and product.get("price") is not None,
            "availability_verified": isinstance(product.get("availability"), dict),
        }
        availability = product.get("availability")
        # A zero sellable stock is an explicit absence signal. Do not rely on
        # the model to remember the analog fallback: run the same guarded
        # compatibility flow server-side and expose its result as data.
        if (
            isinstance(availability, dict)
            and availability.get("status") == "unavailable"
            and availability.get("sellable_quantity") == 0
        ):
            result["analog_fallback"] = self._tool_find_analogs(
                {"product_id": product_id, "limit": MAX_TOOL_RESULTS}
            )
            result["fallback_reason"] = "zero_sellable_stock"
        return result

    def _tool_find_analogs(self, arguments: Any) -> dict[str, Any]:
        values = _object(arguments, required={"product_id", "limit"})
        product_id = _positive_int(values["product_id"], "product_id")
        limit = _positive_int(values["limit"], "limit", MAX_TOOL_RESULTS)
        ranked = find_analogs(product_id, self._index_path, limit)
        if ranked.get("manager_review_required"):
            return {
                "source": "compatibility_matrix",
                "matrix": ranked.get("matrix"),
                "status": ranked.get("status"),
                "manager_review_required": True,
                "analogs": [],
                "count": 0,
            }

        provider = self._provider_factory()
        source_product = _detail(provider.get_product(product_id))
        if source_product.get("id") != product_id:
            raise ToolExecutionError("catalog returned a different source product")
        verified: list[dict[str, Any]] = []
        for candidate in ranked.get("results", [])[:limit]:
            if not isinstance(candidate, dict):
                continue
            candidate_id = candidate.get("id")
            if isinstance(candidate_id, bool) or not isinstance(candidate_id, int):
                continue
            try:
                live = _detail(provider.get_product(candidate_id))
            except CatalogError:
                continue
            availability = live.get("availability")
            sellable = availability.get("sellable_quantity") if isinstance(availability, dict) else None
            if (
                not isinstance(availability, dict)
                or availability.get("status") != "available"
                or isinstance(sellable, bool)
                or not isinstance(sellable, (int, float))
                or sellable <= 0
            ):
                continue
            verified.append(
                {
                    "product": live,
                    "recommendation_label": sanitize_text(candidate.get("recommendation_label", "")),
                    "explanation": sanitize_text(candidate.get("explanation", "")),
                    "comparison": sanitize_catalog_payload(candidate.get("comparison", {})),
                    "compatibility": sanitize_catalog_payload(candidate.get("compatibility", {})),
                    "ranking": sanitize_catalog_payload(candidate.get("ranking", {})),
                    "source_ref": f"/api/products/detail?id={candidate_id}",
                }
            )
        return {
            "source": "compatibility_matrix_and_live_catalog_detail",
            "matrix": ranked.get("matrix"),
            "status": "ok" if verified else "no_live_compatible_analogs",
            "manager_review_required": False,
            "critical_parameters": ranked.get("critical_parameters", []),
            "source_product": source_product,
            "analogs": verified[:limit],
            "count": len(verified[:limit]),
        }

    def _tool_query_knowledge_base(self, arguments: Any) -> dict[str, Any]:
        values = _object(arguments, required={"query", "language"})
        query = _query(values["query"])
        language = values["language"]
        if language not in {"ru", "kk"}:
            raise ToolValidationError("language is not supported")
        result = answer_query(query, language=language)
        return {
            "source": "versioned_knowledge_base",
            "status": result.get("status"),
            "intent": sanitize_text(result.get("intent", "")),
            "answer": sanitize_text(result.get("answer", "")) if result.get("answer") else None,
            "manager_required": bool(result.get("manager_required")),
            "sources": _safe_sources(result),
        }
