from __future__ import annotations

from typing import Any

from html import escape

from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from catalog.errors import CatalogError
from catalog.providers import get_catalog_provider
from catalog.search import SearchIndexError, search_catalog
from catalog.providers.fixture import (
    FIXTURE_DATASET_VERSION,
    FIXTURE_PRODUCT_COUNT,
    FIXTURE_SEED,
    PRODUCTS_BY_ID,
)


def _error_response(error: CatalogError, data_source: str) -> JsonResponse:
    response = JsonResponse(
        {
            "error": {"code": error.code, "message": error.message},
            "data_source": data_source,
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
    try:
        provider = get_catalog_provider()
        page = _positive_int(request, "page", 1)
        per_page = _positive_int(request, "per_page", 20, maximum=100)
        return JsonResponse(provider.list_products(page, per_page, _fixture_case(request)))
    except CatalogError as exc:
        return _error_response(exc, getattr(provider, "data_source", "unknown"))


@require_GET
def product_detail(request: HttpRequest) -> JsonResponse:
    provider: Any = None
    try:
        provider = get_catalog_provider()
        product_id = _positive_int(request, "id", 0)
        return JsonResponse(provider.get_product(product_id, _fixture_case(request)))
    except CatalogError as exc:
        return _error_response(exc, getattr(provider, "data_source", "unknown"))


@require_GET
def search(request: HttpRequest) -> JsonResponse:
    query = request.GET.get("q", "")
    try:
        result = search_catalog(query, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    except ValueError as exc:
        return JsonResponse({"error": {"code": "invalid_query", "message": str(exc)}}, status=400)
    except SearchIndexError as exc:
        return JsonResponse({"error": {"code": "search_index_unavailable", "message": str(exc)}}, status=503)
    return JsonResponse(result)


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    del request
    provider = get_catalog_provider()
    payload: dict[str, Any] = {
        "status": "ok",
        "catalog_provider": provider.data_source,
        "data_source": provider.data_source,
    }
    if provider.data_source == "fixture":
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
