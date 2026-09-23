from __future__ import annotations

import time
from typing import Any

from html import escape

from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from catalog.errors import CatalogError
from catalog.analogs import find_analogs
from catalog.search import SearchIndexError, search_catalog, semantic_search_catalog
from config.observability import add_stage, record_metric
from catalog.providers import get_catalog_provider
from catalog.providers.fixture import (
    FIXTURE_DATASET_VERSION,
    FIXTURE_PRODUCT_COUNT,
    FIXTURE_SEED,
    PRODUCTS_BY_ID,
)


def _error_response(error: CatalogError, data_source: str) -> JsonResponse:
    record_metric("catalog_errors_total")
    record_metric(f"catalog_errors_{error.code}_total")
    degraded = error.status_code in {502, 503, 504}
    if degraded:
        record_metric("catalog_degraded_responses_total")
    response = JsonResponse(
        {
            "error": {"code": error.code, "message": error.message},
            "data_source": data_source,
            **(
                {
                    "data_freshness": "stale",
                    "price_and_availability_current": False,
                }
                if degraded
                else {}
            ),
        },
        status=error.status_code,
    )
    for name, value in error.headers.items():
        response[name] = value
    return response


def _positive_int(request: HttpRequest, name: str, default: int, maximum: int | None = None) -> int:
    raw = request.GET.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise CatalogError(400, "invalid_query_parameter", f"{name} must be an integer") from exc
    if value < 1 or (maximum is not None and value > maximum):
        constraint = f"between 1 and {maximum}" if maximum else "a positive integer"
        raise CatalogError(400, "invalid_query_parameter", f"{name} must be {constraint}")
    return value


def _fixture_case(request: HttpRequest) -> str | None:
    return request.GET.get("fixture_case") or request.headers.get("X-Fixture-Scenario")


@require_GET
def products(request: HttpRequest) -> JsonResponse:
    provider: Any = None
    started = time.perf_counter()
    try:
        provider = get_catalog_provider()
        page = _positive_int(request, "page", 1)
        per_page = _positive_int(request, "per_page", 20, maximum=100)
        return JsonResponse(provider.list_products(page, per_page, _fixture_case(request)))
    except CatalogError as exc:
        return _error_response(exc, getattr(provider, "data_source", "unknown"))
    finally:
        add_stage("catalog_provider", started)


@require_GET
def product_detail(request: HttpRequest) -> JsonResponse:
    provider: Any = None
    started = time.perf_counter()
    try:
        provider = get_catalog_provider()
        product_id = _positive_int(request, "id", 0)
        return JsonResponse(provider.get_product(product_id, _fixture_case(request)))
    except CatalogError as exc:
        return _error_response(exc, getattr(provider, "data_source", "unknown"))
    finally:
        add_stage("catalog_provider", started)


@require_GET
def search(request: HttpRequest) -> JsonResponse:
    query = request.GET.get("q", "")
    started = time.perf_counter()
    try:
        result = search_catalog(query, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    except ValueError as exc:
        return JsonResponse({"error": {"code": "invalid_query", "message": str(exc)}}, status=400)
    except SearchIndexError as exc:
        return JsonResponse({"error": {"code": "search_index_unavailable", "message": str(exc)}}, status=503)
    finally:
        add_stage("local_search", started)
    record_metric("search_success_total" if result["results"] else "search_empty_total")
    return JsonResponse(result)


@require_GET
def semantic_search(request: HttpRequest) -> JsonResponse:
    query = request.GET.get("q", "")
    started = time.perf_counter()
    try:
        result = semantic_search_catalog(query, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    except ValueError as exc:
        return JsonResponse({"error": {"code": "invalid_query", "message": str(exc)}}, status=400)
    except SearchIndexError as exc:
        return JsonResponse({"error": {"code": "search_index_unavailable", "message": str(exc)}}, status=503)
    finally:
        add_stage("semantic_search", started)
    record_metric("semantic_search_success_total" if result["results"] else "semantic_search_empty_total")
    return JsonResponse(result)


@require_GET
def analogs(request: HttpRequest) -> JsonResponse:
    raw_product_id = request.GET.get("id")
    try:
        product_id = int(raw_product_id or "0")
        if product_id < 1:
            raise ValueError
        started = time.perf_counter()
        try:
            result = find_analogs(product_id, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
        finally:
            add_stage("analog_compatibility", started)
    except ValueError:
        return JsonResponse({"error": {"code": "invalid_product_id", "message": "id must be a positive integer"}}, status=400)
    except KeyError:
        return JsonResponse({"error": {"code": "product_not_found", "message": "Product was not found in the local index"}}, status=404)
    except SearchIndexError as exc:
        return JsonResponse({"error": {"code": "search_index_unavailable", "message": str(exc)}}, status=503)
    record_metric("analogs_success_total" if result["results"] else "analogs_empty_total")
    return JsonResponse(result)


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    del request
    payload: dict[str, Any] = {
        "status": "ok",
        "catalog_provider": settings.CATALOG_PROVIDER,
        "data_source": settings.CATALOG_PROVIDER,
        "service": "alive",
    }
    if settings.CATALOG_PROVIDER == "fixture":
        payload.update(
            {
                "fixture_version": FIXTURE_DATASET_VERSION,
                "fixture_seed": FIXTURE_SEED,
                "fixture_product_count": FIXTURE_PRODUCT_COUNT,
            }
        )
    return JsonResponse(payload)


@require_GET
def fixture_image(request: HttpRequest) -> FileResponse:
    del request
    asset = settings.BASE_DIR / "catalog" / "static" / "catalog" / "product-placeholder.svg"
    return FileResponse(asset.open("rb"), content_type="image/svg+xml")


@require_GET
def fixture_product_page(request: HttpRequest, product_id: int) -> HttpResponse:
    del request
    product = PRODUCTS_BY_ID.get(product_id)
    if product is None:
        return HttpResponse("Fixture product not found", status=404, content_type="text/plain")
    body = f"""<!doctype html>
<html lang="ru"><meta charset="utf-8"><title>{escape(product['name'])}</title>
<body><main><strong>DEMO FIXTURE — синтетические данные</strong>
<h1>{escape(product['name'])}</h1><p>Артикул: {escape(product['article'])}</p>
<p>Цена: {product['price']} ₸</p></main></body></html>"""
    return HttpResponse(body, content_type="text/html; charset=utf-8")
