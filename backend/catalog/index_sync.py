from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from catalog.errors import CatalogError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncResult:
    success: bool
    stop_reason: str
    pages: int
    products: int
    errors: int
    duration_seconds: float
    warning: str | None = None
    synced_at: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_status(path: Path, result: SyncResult, previous: dict[str, Any] | None) -> None:
    status: dict[str, Any] = dict(previous or {})
    status.update(
        {
            "last_attempt_at": result.synced_at,
            "last_status": "success" if result.success else "failed",
            "last_stop_reason": result.stop_reason,
            "last_pages": result.pages,
            "last_products": result.products,
            "last_errors": result.errors,
            "last_duration_seconds": round(result.duration_seconds, 3),
            "last_warning": result.warning,
        }
    )
    if result.success:
        status["last_successful_sync"] = result.synced_at
        status["last_successful_pages"] = result.pages
        status["last_successful_products"] = result.products
    _write_json(path, status)


def _read_status(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def sync_catalog(
    provider: Any,
    index_path: Path,
    status_path: Path,
    max_pages: int,
    per_page: int,
) -> SyncResult:
    """Build a complete, ID-deduplicated catalog index from a provider.

    EKT does not provide a reliable end-of-pagination marker. Empty pages and
    repeated page ID signatures are accepted as end conditions. The max-pages
    guard never replaces a previously successful index with a partial one.
    """
    started = time.monotonic()
    synced_at = _iso(_utc_now())
    products_by_id: dict[int, dict[str, Any]] = {}
    signatures: set[tuple[int, ...]] = set()
    pages_fetched = 0
    errors = 0
    stop_reason = "max_pages_guard"
    warning: str | None = None

    if max_pages < 1 or per_page < 1:
        result = SyncResult(False, "invalid_configuration", 0, 0, 1, time.monotonic() - started, "max_pages and per_page must be positive", synced_at)
        _write_status(status_path, result, _read_status(status_path))
        return result

    for page in range(1, max_pages + 1):
        try:
            payload = provider.list_products(page, per_page)
            pages_fetched = page
        except CatalogError as exc:
            errors += 1
            warning = f"catalog page {page} failed: {exc.code}"
            logger.exception("Catalog index synchronization failed at page %s", page)
            result = SyncResult(False, "provider_error", page - 1, len(products_by_id), errors, time.monotonic() - started, warning, synced_at)
            _write_status(status_path, result, _read_status(status_path))
            return result
        except Exception:
            errors += 1
            warning = f"catalog page {page} failed with an unexpected error"
            logger.exception("Catalog index synchronization failed at page %s", page)
            result = SyncResult(False, "provider_error", page - 1, len(products_by_id), errors, time.monotonic() - started, warning, synced_at)
            _write_status(status_path, result, _read_status(status_path))
            return result

        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            errors += 1
            warning = f"catalog page {page} has no valid items array"
            result = SyncResult(False, "invalid_payload", page, len(products_by_id), errors, time.monotonic() - started, warning, synced_at)
            _write_status(status_path, result, _read_status(status_path))
            return result

        if not items:
            stop_reason = "empty_page"
            break

        page_ids = tuple(item.get("id") for item in items if isinstance(item, dict) and isinstance(item.get("id"), int))
        if not page_ids:
            errors += 1
            warning = f"catalog page {page} contained no valid product IDs"
            result = SyncResult(False, "invalid_payload", page, len(products_by_id), errors, time.monotonic() - started, warning, synced_at)
            _write_status(status_path, result, _read_status(status_path))
            return result
        if page_ids in signatures:
            stop_reason = "repeated_page_ids"
            break
        signatures.add(page_ids)

        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                products_by_id[item["id"]] = deepcopy(item)
    else:
        warning = f"catalog synchronization reached max_pages={max_pages}"
        logger.warning(warning)

    if stop_reason == "max_pages_guard":
        result = SyncResult(False, stop_reason, pages_fetched, len(products_by_id), errors, time.monotonic() - started, warning, synced_at)
        _write_status(status_path, result, _read_status(status_path))
        return result

    ordered_items = [products_by_id[product_id] for product_id in sorted(products_by_id)]
    index_payload = {
        "data_source": provider.data_source,
        "synced_at": synced_at,
        "stop_reason": stop_reason,
        "pages": pages_fetched,
        "count": len(ordered_items),
        "items": ordered_items,
    }
    _write_json(index_path, index_payload)
    result = SyncResult(True, stop_reason, pages_fetched, len(ordered_items), errors, time.monotonic() - started, warning, synced_at)
    _write_status(status_path, result, _read_status(status_path))
    return result
