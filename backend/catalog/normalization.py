from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


ATTRIBUTE_ALIASES: dict[str, tuple[str, ...]] = {
    "brand": ("TORGOVAYA_MARKA", "BRAND"),
    "supplier_article": ("ARTIKULPOSTAVSHCHIKA",),
    "barcode": ("CML2_BAR_CODE", "BARCODE"),
    "product_type": ("OBYEM", "CATEGORY"),
    "pole_count": ("KOLICHESTVO_POLYUSOV", "POLES"),
    "rated_current": ("NOMINALNYY_TOK", "RATED_CURRENT"),
    "rated_voltage": ("NOMINALNOE_NAPRYAZHENIE", "RATED_VOLTAGE"),
    "breaking_capacity": (
        "NOMINALNAYA_OTKLYUCHAYUSHCHAYA_SPOSOBNOST",
        "BREAKING_CAPACITY",
    ),
    "installation_type": ("TIP_USTANOVKI", "INSTALLATION_TYPE"),
    "analog_group": ("ANALOG_GROUP",),
}

SOURCE_UPDATED_KEYS = (
    "source_updated_at",
    "updated_at",
    "modified_at",
    "date_modified",
)


def _utc_iso(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def _number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return int(parsed) if parsed == parsed.to_integral() else float(parsed)


def _first_present(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _source_value(
    source: Mapping[str, Any],
    properties: Mapping[str, Any],
    source_keys: tuple[str, ...],
    property_keys: tuple[str, ...],
) -> Any:
    direct = _first_present(source, source_keys)
    return direct if direct is not None else _first_present(properties, property_keys)


def normalize_attributes(properties: Any) -> dict[str, Any]:
    """Map only approved aliases; the complete source remains in properties_raw."""
    if not isinstance(properties, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for canonical_name, aliases in ATTRIBUTE_ALIASES.items():
        value = _first_present(properties, aliases)
        if value is not None:
            normalized[canonical_name] = copy.deepcopy(value)
    return normalized


def normalize_product(
    source: Mapping[str, Any],
    *,
    default_currency: str | None,
    availability: Mapping[str, Any] | None,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the internal product model without mutating or replacing source JSON."""
    if not isinstance(source, Mapping):
        raise TypeError("source must be a mapping")

    verified_at = _utc_iso(fetched_at)
    properties = source.get("properties") if isinstance(source.get("properties"), Mapping) else {}
    raw_price = source.get("price")
    if isinstance(raw_price, Mapping):
        amount = _number(raw_price.get("amount"))
        source_currency = raw_price.get("currency")
    else:
        amount = _number(raw_price)
        source_currency = source.get("currency")
    currency = source_currency if source_currency not in (None, "") else default_currency

    computed_availability = availability if isinstance(availability, Mapping) else {}
    stores = source.get("stores") if isinstance(source.get("stores"), list) else []
    offers = source.get("offers") if isinstance(source.get("offers"), list) else []

    unit = _source_value(
        source,
        properties,
        ("unit", "quantity_unit"),
        ("UNIT", "QUANTITY_UNIT", "EDINICA_IZMERENIYA", "EDINICZA_IZMERENIYA"),
    )
    step = _source_value(
        source,
        properties,
        ("step", "quantity_step"),
        ("STEP", "QUANTITY_STEP"),
    )
    minimum = _source_value(
        source,
        properties,
        ("minimum", "minimum_quantity"),
        ("MINIMUM", "MINIMUM_QUANTITY", "KRATNOST_MIN"),
    )

    source_updated_at = _first_present(source, SOURCE_UPDATED_KEYS)
    if isinstance(source_updated_at, datetime):
        source_updated_at = _utc_iso(source_updated_at)
    elif not isinstance(source_updated_at, (str, int, float)):
        source_updated_at = None

    return {
        "id": copy.deepcopy(source.get("id")),
        "article": copy.deepcopy(source.get("article")),
        "name": copy.deepcopy(source.get("name")),
        "description": copy.deepcopy(source.get("description")),
        "price": {
            "amount": amount,
            "currency": copy.deepcopy(currency),
            "verified_at": verified_at,
        },
        "availability": {
            "status": computed_availability.get("status", "availability_unknown"),
            "sellable_quantity": copy.deepcopy(computed_availability.get("sellable_quantity")),
            "unit": copy.deepcopy(unit),
            "step": _number(step),
            "minimum": _number(minimum),
            "rule_version": copy.deepcopy(computed_availability.get("rule_version")),
            "verified_at": verified_at,
            "stores": copy.deepcopy(stores),
        },
        "image_url": copy.deepcopy(source.get("image_url", source.get("image"))),
        "product_url": copy.deepcopy(source.get("product_url", source.get("url"))),
        "offers": copy.deepcopy(offers),
        "properties_raw": copy.deepcopy(dict(properties)),
        "attributes_normalized": normalize_attributes(properties),
        "source_fetched_at": verified_at,
        "source_updated_at": copy.deepcopy(source_updated_at),
    }
