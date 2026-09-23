from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.conf import settings

from catalog.availability import calculate_availability
from catalog.search import SearchIndexError, _load_items


LIGHTING_CATEGORY_MARKERS = ("свет", "ламп", "прожектор", "освещ", "led")

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "purpose": ("PURPOSE", "APPLICATION", "USE", "НАЗНАЧЕНИЕ", "ПРИМЕНЕНИЕ"),
    "mounting": (
        "MOUNT_TYPE",
        "MOUNTING",
        "MOUNT",
        "TYPE_MOUNT",
        "ТИП_МОНТАЖА",
        "КРЕПЛЕНИЕ",
    ),
    "power": ("POWER", "WATTAGE", "МОЩНОСТЬ"),
    "voltage": ("VOLTAGE", "НАПРЯЖЕНИЕ"),
    "color_temperature": (
        "COLOR_TEMPERATURE",
        "CCT",
        "ЦВЕТОВАЯ_ТЕМПЕРАТУРА",
    ),
    "luminous_flux": (
        "LUMINOUS_FLUX",
        "LIGHT_FLUX",
        "СВЕТОВОЙ_ПОТОК",
    ),
    "ip_rating": ("IP_RATING", "IP", "СТЕПЕНЬ_ЗАЩИТЫ", "СТЕПЕНЬ_ЗАЩИТЫ_IP"),
    "dimensions": ("DIMENSIONS", "DIMENSION", "ГАБАРИТЫ", "РАЗМЕРЫ"),
}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().replace("ё", "е")
    return " ".join(text.split())


def _compact(value: Any) -> str:
    return re.sub(r"[^\w]+", "", _normalize(value), flags=re.UNICODE)


def _properties(item: dict[str, Any]) -> dict[str, Any]:
    properties = item.get("properties")
    return properties if isinstance(properties, dict) else {}


def _value(item: dict[str, Any], field: str) -> Any:
    properties = _properties(item)
    normalized = {_compact(key): value for key, value in properties.items()}
    for alias in _FIELD_ALIASES[field]:
        value = normalized.get(_compact(alias))
        if value not in (None, "", []):
            return value
    return None


def _category(item: dict[str, Any]) -> str:
    return _normalize(_value(item, "purpose") or _properties(item).get("CATEGORY") or item.get("category"))


def _is_lighting(item: dict[str, Any]) -> bool:
    category = _category(item)
    name = _normalize(item.get("name"))
    return any(marker in category or marker in name for marker in LIGHTING_CATEGORY_MARKERS)


def _numeric(value: Any) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)?", _normalize(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _compatible(field: str, source: Any, candidate: Any) -> bool:
    if field == "ip_rating":
        source_ip = _numeric(source)
        candidate_ip = _numeric(candidate)
        return source_ip is None or candidate_ip is None or candidate_ip >= source_ip
    return _compact(source) == _compact(candidate)


def _compatibility(source: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, list[str], list[str], list[str]]:
    matched: list[str] = []
    unknown: list[str] = []
    rejected: list[str] = []
    for field in _FIELD_ALIASES:
        source_value = _value(source, field)
        candidate_value = _value(candidate, field)
        if source_value in (None, "", []) or candidate_value in (None, "", []):
            if source_value not in (None, "", []):
                unknown.append(field)
            continue
        if _compatible(field, source_value, candidate_value):
            matched.append(field)
        else:
            rejected.append(field)
    return not rejected, matched, unknown, rejected


def _explanation(matched: list[str], unknown: list[str]) -> str:
    parts = []
    if matched:
        parts.append("совпадают: " + ", ".join(matched))
    if unknown:
        parts.append("нет данных для проверки: " + ", ".join(unknown))
    return "; ".join(parts) or "критичные параметры не заполнены в источнике"


def _availability(item: dict[str, Any], index_path: Path) -> dict[str, Any]:
    existing = item.get("availability")
    if isinstance(existing, dict):
        return existing
    source = item.get("data_source") or settings.CATALOG_PROVIDER
    store_ids = (
        settings.FIXTURE_SELLABLE_STORE_IDS
        if source == "fixture"
        else settings.SELLABLE_STORE_IDS
    )
    rule_version = (
        settings.FIXTURE_AVAILABILITY_RULE_VERSION
        if source == "fixture"
        else settings.AVAILABILITY_RULE_VERSION
    )
    observed_at = datetime.fromtimestamp(index_path.stat().st_mtime, tz=timezone.utc)
    return calculate_availability(
        item.get("stores"),
        item.get("quantity"),
        store_ids,
        rule_version,
        observed_at=observed_at,
        stale_after_seconds=settings.AVAILABILITY_STALE_AFTER_SECONDS,
    )


def _price_score(source: dict[str, Any], candidate: dict[str, Any]) -> float:
    try:
        source_price = Decimal(str(source.get("price")))
        candidate_price = Decimal(str(candidate.get("price")))
        if source_price <= 0 or candidate_price < 0:
            return 0.0
        return float(max(Decimal("0"), Decimal("1") - abs(candidate_price - source_price) / max(source_price, candidate_price)))
    except (InvalidOperation, TypeError, ValueError):
        return 0.0


def _comparison(source: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    unverified: list[str] = []
    for field in _FIELD_ALIASES:
        source_value = _value(source, field)
        candidate_value = _value(candidate, field)
        if source_value in (None, "", []) or candidate_value in (None, "", []):
            if source_value not in (None, "", []) or candidate_value not in (None, "", []):
                unverified.append(field)
            continue
        if _compatible(field, source_value, candidate_value):
            matched.append({"parameter": field, "source": source_value, "candidate": candidate_value})
            if field == "ip_rating" and _compact(source_value) != _compact(candidate_value):
                differences.append({"parameter": field, "source": source_value, "candidate": candidate_value, "kind": "higher_protection"})
        else:
            differences.append({"parameter": field, "source": source_value, "candidate": candidate_value, "kind": "different"})
    return {"matched": matched, "differences": differences, "unverified": unverified}


def find_analogs(product_id: int, index_path: Path, max_results: int = 5) -> dict[str, Any]:
    items = _load_items(index_path)
    source = next((item for item in items if item.get("id") == product_id), None)
    if source is None:
        raise KeyError(product_id)

    lighting = _is_lighting(source)
    if not lighting:
        return {
            "product_id": product_id,
            "category": _category(source),
            "matrix": "unapproved",
            "status": "manager_review_required",
            "manager_review_required": True,
            "results": [],
            "count": 0,
        }

    source_group = _properties(source).get("ANALOG_GROUP")
    candidates = []
    rejected_count = 0
    for candidate in items:
        if candidate.get("id") == product_id or not _is_lighting(candidate):
            continue
        candidate_group = _properties(candidate).get("ANALOG_GROUP")
        if source_group and candidate_group and source_group != candidate_group:
            continue
        compatible, matched, unknown, rejected = _compatibility(source, candidate)
        if not compatible:
            rejected_count += 1
            continue
        availability = _availability(candidate, index_path)
        sellable_quantity = availability.get("sellable_quantity")
        if availability.get("status") != "available" or not isinstance(sellable_quantity, (int, float)) or sellable_quantity <= 0:
            continue
        comparison = _comparison(source, candidate)
        similarity_score = len(matched) / max(len(_FIELD_ALIASES), 1)
        availability_score = 1.0
        price_score = _price_score(source, candidate)
        rank_score = similarity_score * 0.6 + availability_score * 0.25 + price_score * 0.15
        label = "совместимый аналог" if not unknown else "кандидат, нужна проверка параметров"
        candidates.append(
            dict(
                candidate,
                match_type="compatible_analog",
                recommendation_label=label,
                sellable_quantity=sellable_quantity,
                availability=availability,
                ranking={
                    "score": round(rank_score, 4),
                    "similarity": round(similarity_score, 4),
                    "availability": availability_score,
                    "price": round(price_score, 4),
                },
                comparison=comparison,
                compatibility={
                    "status": "compatible" if not unknown else "compatible_with_unverified_fields",
                    "matched_parameters": matched,
                    "unverified_parameters": unknown,
                    "rejected_parameters": rejected,
                },
                explanation=_explanation(matched, unknown),
            )
        )
    candidates.sort(key=lambda item: (-item["ranking"]["score"], int(item["id"])))
    return {
        "product_id": product_id,
        "category": _category(source),
        "matrix": "lighting-v1",
        "status": "ok" if candidates else "no_compatible_analogs",
        "manager_review_required": False,
        "critical_parameters": list(_FIELD_ALIASES),
        "rejected_candidates": rejected_count,
        "results": candidates[:max_results],
        "count": min(len(candidates), max_results),
    }
