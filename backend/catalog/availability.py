from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


NON_SELLABLE_STORE_MARKERS = (
    "брак",
    "перемещ",
    "маркетинг",
    "восстановлен",
    "образц",
    "витрина",
)


def _quantity(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result >= 0 else None


def calculate_availability(
    stores: Any,
    total_quantity: Any,
    sellable_store_ids: Iterable[int],
    rule_version: str,
) -> dict[str, Any]:
    """Apply the same conservative store allowlist rule to every provider."""
    allowed = set(sellable_store_ids)
    total = _quantity(total_quantity)
    if total is None:
        return {
            "status": "availability_unknown",
            "sellable_quantity": None,
            "rule_version": rule_version,
        }
    if not isinstance(stores, list) or not stores:
        return {
            "status": "availability_unknown" if total > 0 else "unavailable",
            "sellable_quantity": None if total > 0 else 0,
            "rule_version": rule_version,
        }

    sellable = Decimal("0")
    has_unclassified_positive_stock = False
    for store in stores:
        if not isinstance(store, dict):
            return {
                "status": "availability_unknown",
                "sellable_quantity": None,
                "rule_version": rule_version,
            }
        quantity = _quantity(store.get("quantity"))
        if quantity is None:
            return {
                "status": "availability_unknown",
                "sellable_quantity": None,
                "rule_version": rule_version,
            }
        store_id = store.get("id")
        name = str(store.get("name") or "").casefold()
        is_known_service_store = any(marker in name for marker in NON_SELLABLE_STORE_MARKERS)
        if is_known_service_store:
            continue
        if store_id in allowed:
            sellable += quantity
        elif quantity > 0:
            has_unclassified_positive_stock = True

    if has_unclassified_positive_stock:
        return {
            "status": "availability_unknown",
            "sellable_quantity": None,
            "rule_version": rule_version,
        }

    normalized = int(sellable) if sellable == sellable.to_integral() else float(sellable)
    return {
        "status": "available" if sellable > 0 else "unavailable",
        "sellable_quantity": normalized,
        "rule_version": rule_version,
    }
