from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from math import lcm
from typing import Any

from django.conf import settings
from django.core.signing import salted_hmac
from django.db import OperationalError, connection, transaction
from django.db.models import Max
from django.utils import timezone

from catalog.errors import CatalogError
from catalog.providers import get_catalog_provider
from cart.errors import CartApiError
from cart.models import Cart, CartAction, CartItem, CartMutation


CONFIRMATION_ALLOWLIST = frozenset({"да", "подтверждаю", "добавить в корзину"})


class StaleCartCondition(Exception):
    def __init__(self, detail_values: dict[str, Any] | None = None) -> None:
        self.detail_values = detail_values


def owner_key_for_session(session_key: str) -> str:
    return salted_hmac("cart.owner", session_key).hexdigest()


def _money(value: Decimal) -> str:
    return format(value, ".2f")


def _decimal_price(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise CartApiError(422, "invalid_product_price", "Product price is not usable")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CartApiError(422, "invalid_product_price", "Product price is not usable") from exc
    if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2:
        raise CartApiError(422, "invalid_product_price", "Product price is not usable")
    return price.quantize(Decimal("0.01"))


def _positive_stock(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        stock = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return 0
    if not stock.is_finite() or stock <= 0 or stock != stock.to_integral_value():
        return 0
    return int(stock)


def _validate_identifier(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise CartApiError(400, "invalid_request", f"{name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > 128 or any(ord(char) < 32 for char in normalized):
        raise CartApiError(400, "invalid_request", f"{name} is invalid")
    return normalized


def validate_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    dialog_id = _validate_identifier(payload.get("dialog_id"), "dialog_id")
    message_id = _validate_identifier(payload.get("message_id"), "message_id")
    message_version = payload.get("message_version")
    product_id = payload.get("product_id")
    quantity = payload.get("quantity")
    for value, name in (
        (message_version, "message_version"),
        (product_id, "product_id"),
        (quantity, "quantity"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CartApiError(400, "invalid_request", f"{name} must be a positive integer")
    if quantity > settings.CART_MAX_QUANTITY:
        raise CartApiError(
            422,
            "quantity_limit_exceeded",
            "Quantity exceeds the fixture cart limit",
            {"maximum_quantity": settings.CART_MAX_QUANTITY},
        )
    offer_id = payload.get("offer_id")
    if offer_id is not None:
        offer_id = _validate_identifier(str(offer_id), "offer_id")
        raise CartApiError(
            422,
            "unsupported_offer",
            "Offer selection is disabled until the offer contract is confirmed",
        )
    return {
        "dialog_id": dialog_id,
        "message_id": message_id,
        "message_version": message_version,
        "product_id": product_id,
        "offer_id": "",
        "quantity": quantity,
    }


def _ensure_fixture_provider():
    provider = get_catalog_provider()
    if provider.data_source != "fixture":
        raise CartApiError(
            503,
            "cart_integration_unavailable",
            "Cart changes are disabled until the production cart contract is configured",
        )
    return provider


def _load_detail(product_id: int) -> dict[str, Any]:
    provider = _ensure_fixture_provider()
    try:
        detail = provider.get_product(product_id)
    except CatalogError as exc:
        raise CartApiError(exc.status_code, exc.code, exc.message) from exc
    if not isinstance(detail, dict):
        raise CartApiError(502, "invalid_catalog_response", "Catalog returned invalid product data")
    return detail


def _detail_values(detail: dict[str, Any], expected_product_id: int) -> dict[str, Any]:
    availability = detail.get("availability")
    if not isinstance(availability, dict) or availability.get("status") != "available":
        raise CartApiError(409, "product_unavailable", "Product is not available for cart changes")
    stock = _positive_stock(availability.get("sellable_quantity"))
    if stock < 1:
        raise CartApiError(409, "product_unavailable", "Product is not available for cart changes")
    product_id = detail.get("id")
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id < 1:
        raise CartApiError(502, "invalid_catalog_response", "Catalog returned invalid product data")
    if product_id != expected_product_id:
        raise CartApiError(502, "catalog_product_mismatch", "Catalog returned another product")
    offers = detail.get("offers")
    if not isinstance(offers, list):
        raise CartApiError(502, "invalid_catalog_response", "Catalog returned invalid offers data")
    if offers:
        raise CartApiError(
            409,
            "offer_selection_required",
            "Cart changes are disabled for products with unconfirmed offer contracts",
        )
    price_version = detail.get("fixture_version")
    if not isinstance(price_version, str) or not price_version:
        raise CartApiError(502, "invalid_catalog_response", "Catalog omitted the price version")
    rule_version = availability.get("rule_version")
    if not isinstance(rule_version, str) or not rule_version:
        raise CartApiError(502, "invalid_catalog_response", "Catalog omitted the availability rule")
    snapshot = {
        "id": product_id,
        "name": str(detail.get("name") or ""),
        "article": str(detail.get("article") or ""),
        "url": str(detail.get("url") or ""),
        "image": str(detail.get("image") or ""),
    }
    return {
        "product_id": product_id,
        "unit_price": _decimal_price(detail.get("price")),
        "currency": settings.CART_CURRENCY,
        "price_version": price_version,
        "pricing_context": {
            "data_source": "fixture",
            "availability_rule_version": rule_version,
            "sales_rules": {
                "unit": "piece",
                "minimum": 1,
                "step": 1,
                "multiple": 1,
                "maximum": settings.CART_MAX_QUANTITY,
            },
        },
        "stock": stock,
        "product_snapshot": snapshot,
    }


def get_or_create_cart(owner_key: str) -> Cart:
    cart, _ = Cart.objects.get_or_create(
        owner_key=owner_key,
        defaults={"currency": settings.CART_CURRENCY},
    )
    return cart


def cart_snapshot(cart: Cart) -> dict[str, Any]:
    items = []
    total = Decimal("0")
    for item in cart.items.order_by("id"):
        line_total = item.unit_price * item.quantity
        total += line_total
        items.append(
            {
                "product_id": item.product_id,
                "offer_id": item.offer_id or None,
                "quantity": item.quantity,
                "unit_price": _money(item.unit_price),
                "line_total": _money(line_total),
                "product": item.product_snapshot,
            }
        )
    return {
        "version": cart.version,
        "currency": cart.currency,
        "items": items,
        "total": _money(total),
        "url": settings.CART_URL,
        "data_source": "fixture",
    }


def action_snapshot(action: CartAction) -> dict[str, Any]:
    return {
        "action_id": str(action.id),
        "status": action.status,
        "dialog_id": action.dialog_id,
        "message_id": action.message_id,
        "message_version": action.message_version,
        "expires_at": action.expires_at.isoformat(),
        "expected_cart_version": action.expected_cart_version,
        "product": action.product_snapshot,
        "product_id": action.product_id,
        "offer_id": action.offer_id or None,
        "quantity": action.quantity,
        "unit_price": _money(action.unit_price),
        "currency": action.currency,
        "total": _money(action.unit_price * action.quantity),
        "price_version": action.price_version,
        "pricing_context": action.pricing_context,
    }


def _active_quantity(cart: Cart, product_id: int, offer_id: str = "") -> int:
    return (
        CartItem.objects.filter(cart=cart, product_id=product_id, offer_id=offer_id)
        .values_list("quantity", flat=True)
        .first()
        or 0
    )


def _same_request(action: CartAction, values: dict[str, Any]) -> bool:
    return (
        action.product_id == values["product_id"]
        and action.offer_id == values["offer_id"]
        and action.quantity == values["quantity"]
    )


def _create_action_once(owner_key: str, payload: dict[str, Any]) -> tuple[CartAction, bool]:
    request_values = validate_create_payload(payload)
    _ensure_fixture_provider()
    existing = CartAction.objects.filter(
        owner_key=owner_key,
        dialog_id=request_values["dialog_id"],
        message_id=request_values["message_id"],
        message_version=request_values["message_version"],
    ).first()
    if existing is not None:
        if not _same_request(existing, request_values):
            raise CartApiError(
                409,
                "message_version_conflict",
                "This message version is already bound to another cart proposal",
            )
        return existing, False
    detail_values = _detail_values(
        _load_detail(request_values["product_id"]), request_values["product_id"]
    )
    with transaction.atomic():
        cart = get_or_create_cart(owner_key)
        cart = Cart.objects.select_for_update().get(pk=cart.pk)
        existing = CartAction.objects.filter(
            owner_key=owner_key,
            dialog_id=request_values["dialog_id"],
            message_id=request_values["message_id"],
            message_version=request_values["message_version"],
        ).first()
        if existing is not None:
            if not _same_request(existing, request_values):
                raise CartApiError(
                    409,
                    "message_version_conflict",
                    "This message version is already bound to another cart proposal",
                )
            return existing, False

        available_to_add = detail_values["stock"] - _active_quantity(
            cart, request_values["product_id"]
        )
        if request_values["quantity"] > max(available_to_add, 0):
            raise CartApiError(
                409,
                "insufficient_stock",
                "Requested quantity exceeds current sellable stock",
                {"maximum_quantity": max(available_to_add, 0), "cart": cart_snapshot(cart)},
            )

        CartAction.objects.filter(
            owner_key=owner_key,
            dialog_id=request_values["dialog_id"],
            status=CartAction.Status.PROPOSED,
        ).update(status=CartAction.Status.EXPIRED, failure_code="superseded")
        now = timezone.now()
        action = CartAction.objects.create(
            owner_key=owner_key,
            dialog_id=request_values["dialog_id"],
            message_id=request_values["message_id"],
            message_version=request_values["message_version"],
            cart=cart,
            expected_cart_version=cart.version,
            product_id=request_values["product_id"],
            offer_id="",
            quantity=request_values["quantity"],
            unit_price=detail_values["unit_price"],
            currency=detail_values["currency"],
            price_version=detail_values["price_version"],
            pricing_context=detail_values["pricing_context"],
            product_snapshot=detail_values["product_snapshot"],
            expires_at=now + timedelta(seconds=settings.CART_ACTION_TTL_SECONDS),
        )
    return action, True


def _run_with_database_retry(operation):
    attempts = 4 if connection.vendor == "sqlite" else 1
    for attempt in range(attempts):
        try:
            return operation()
        except OperationalError as exc:
            is_lock = "locked" in str(exc).casefold() or "busy" in str(exc).casefold()
            if not is_lock or attempt + 1 >= attempts:
                if is_lock:
                    raise CartApiError(
                        503,
                        "cart_busy",
                        "Cart is busy; retry the same action",
                    ) from exc
                raise
            time.sleep(0.02 * (2**attempt))
    raise AssertionError("database retry loop exhausted")


def create_action(owner_key: str, payload: dict[str, Any]) -> tuple[CartAction, bool]:
    return _run_with_database_retry(lambda: _create_action_once(owner_key, payload))


def _saved_success(action: CartAction, mutation: CartMutation | None = None) -> dict[str, Any]:
    result = mutation.result if mutation is not None else action.result
    if not result:
        raise CartApiError(409, "action_in_progress", "Cart action is still being reconciled")
    if action.status != CartAction.Status.SUCCEEDED or action.result != result:
        CartAction.objects.filter(pk=action.pk).update(
            status=CartAction.Status.SUCCEEDED, result=result, failure_code=""
        )
    return result


def _reconcile_or_mark_failed(
    action_id: Any, owner_key: str, code: str, message: str
) -> dict[str, Any] | CartApiError:
    with transaction.atomic():
        action = CartAction.objects.select_for_update().get(pk=action_id, owner_key=owner_key)
        mutation = CartMutation.objects.filter(idempotency_key=action.idempotency_key).first()
        if mutation is not None:
            return _saved_success(action, mutation)
        cart = Cart.objects.select_for_update().get(pk=action.cart_id)
        result = {"action_id": str(action.id), "status": "failed", "cart": cart_snapshot(cart)}
        action.status = CartAction.Status.FAILED
        action.failure_code = code
        action.result = result
        action.save(update_fields=("status", "failure_code", "result", "updated_at"))
    return CartApiError(
        502 if code == "cart_mutation_failed" else 503,
        code,
        message,
        {"action_id": str(action.id), "status": action.status, "cart": result["cart"]},
    )


def _replacement_for_stale(
    action_id: Any, owner_key: str, detail_values: dict[str, Any] | None, reason: str
) -> dict[str, Any] | None:
    with transaction.atomic():
        action = CartAction.objects.select_for_update().get(pk=action_id, owner_key=owner_key)
        if hasattr(action, "replacement"):
            return action_snapshot(action.replacement)
        action.status = CartAction.Status.EXPIRED
        action.failure_code = reason
        action.save(update_fields=("status", "failure_code", "updated_at"))
        if detail_values is None:
            return None
        cart = Cart.objects.select_for_update().get(pk=action.cart_id)
        available_to_add = detail_values["stock"] - _active_quantity(
            cart, action.product_id, action.offer_id
        )
        sales_rules = detail_values["pricing_context"]["sales_rules"]
        increment = lcm(sales_rules["step"], sales_rules["multiple"])
        quantity = min(
            action.quantity,
            max(available_to_add, 0),
            sales_rules["maximum"],
        )
        quantity -= quantity % increment
        if quantity < sales_rules["minimum"]:
            return None
        CartAction.objects.filter(
            owner_key=owner_key,
            dialog_id=action.dialog_id,
            status=CartAction.Status.PROPOSED,
        ).update(status=CartAction.Status.EXPIRED, failure_code="superseded")
        max_version = (
            CartAction.objects.filter(
                owner_key=owner_key,
                dialog_id=action.dialog_id,
                message_id=action.message_id,
            ).aggregate(value=Max("message_version"))["value"]
            or action.message_version
        )
        replacement = CartAction.objects.create(
            owner_key=owner_key,
            dialog_id=action.dialog_id,
            message_id=action.message_id,
            message_version=max_version + 1,
            cart=cart,
            expected_cart_version=cart.version,
            product_id=action.product_id,
            offer_id=action.offer_id,
            quantity=quantity,
            unit_price=detail_values["unit_price"],
            currency=detail_values["currency"],
            price_version=detail_values["price_version"],
            pricing_context=detail_values["pricing_context"],
            product_snapshot=detail_values["product_snapshot"],
            expires_at=timezone.now() + timedelta(seconds=settings.CART_ACTION_TTL_SECONDS),
            replacement_for=action,
        )
        return action_snapshot(replacement)


def _stale_error(
    action: CartAction, owner_key: str, detail_values: dict[str, Any] | None, reason: str
) -> CartApiError:
    replacement = _replacement_for_stale(action.id, owner_key, detail_values, reason)
    extra: dict[str, Any] = {"action_id": str(action.id), "status": "expired"}
    if replacement is not None:
        extra["replacement_action"] = replacement
    return CartApiError(409, "action_stale", "Cart proposal is no longer current", extra)


def _mutate_fixture(action_id: Any, owner_key: str) -> dict[str, Any]:
    with transaction.atomic():
        action = CartAction.objects.select_for_update().get(pk=action_id, owner_key=owner_key)
        mutation = CartMutation.objects.filter(idempotency_key=action.idempotency_key).first()
        if mutation is not None:
            return _saved_success(action, mutation)
        cart = Cart.objects.select_for_update().get(pk=action.cart_id)
        try:
            detail_values = _detail_values(_load_detail(action.product_id), action.product_id)
        except CartApiError as exc:
            if exc.code in {
                "product_unavailable",
                "invalid_product_price",
                "offer_selection_required",
            }:
                raise StaleCartCondition() from exc
            raise
        if cart.version != action.expected_cart_version:
            raise StaleCartCondition(detail_values)
        if (
            detail_values["unit_price"] != action.unit_price
            or detail_values["currency"] != action.currency
            or detail_values["price_version"] != action.price_version
            or detail_values["pricing_context"] != action.pricing_context
        ):
            raise StaleCartCondition(detail_values)
        sales_rules = detail_values["pricing_context"]["sales_rules"]
        if (
            action.quantity < sales_rules["minimum"]
            or action.quantity > sales_rules["maximum"]
            or action.quantity % sales_rules["step"] != 0
            or action.quantity % sales_rules["multiple"] != 0
        ):
            raise StaleCartCondition(detail_values)
        item = CartItem.objects.filter(
            cart=cart, product_id=action.product_id, offer_id=action.offer_id
        ).first()
        old_quantity = item.quantity if item is not None else 0
        if old_quantity + action.quantity > detail_values["stock"]:
            raise StaleCartCondition(detail_values)
        if item is None:
            CartItem.objects.create(
                cart=cart,
                product_id=action.product_id,
                offer_id=action.offer_id,
                quantity=action.quantity,
                unit_price=action.unit_price,
                product_snapshot=action.product_snapshot,
            )
        else:
            item.quantity += action.quantity
            item.unit_price = action.unit_price
            item.product_snapshot = action.product_snapshot
            item.save(update_fields=("quantity", "unit_price", "product_snapshot", "updated_at"))
        cart.version += 1
        cart.save(update_fields=("version", "updated_at"))
        result = {
            "action_id": str(action.id),
            "status": "succeeded",
            "added_quantity": action.quantity,
            "cart": cart_snapshot(cart),
        }
        CartMutation.objects.create(
            idempotency_key=action.idempotency_key,
            action=action,
            cart=cart,
            result=result,
        )
        action.status = CartAction.Status.SUCCEEDED
        action.failure_code = ""
        action.result = result
        action.save(update_fields=("status", "failure_code", "result", "updated_at"))
        return result


def _confirm_action_once(owner_key: str, action_id: Any) -> dict[str, Any]:
    expiry_error: CartApiError | None = None
    with transaction.atomic():
        try:
            action = CartAction.objects.select_for_update().get(pk=action_id, owner_key=owner_key)
        except CartAction.DoesNotExist as exc:
            raise CartApiError(404, "action_not_found", "Cart action was not found") from exc
        if action.status == CartAction.Status.SUCCEEDED:
            return _saved_success(action)
        if action.status == CartAction.Status.FAILED:
            raise CartApiError(
                409,
                "action_failed",
                "Cart action has already failed",
                {"action_id": str(action.id), "status": action.status, **action.result},
            )
        if action.status == CartAction.Status.EXPIRED:
            extra: dict[str, Any] = {"action_id": str(action.id), "status": action.status}
            if hasattr(action, "replacement"):
                extra["replacement_action"] = action_snapshot(action.replacement)
            raise CartApiError(409, "action_expired", "Cart action has expired", extra)
        if timezone.now() >= action.expires_at:
            action.status = CartAction.Status.EXPIRED
            action.failure_code = "ttl_expired"
            action.save(update_fields=("status", "failure_code", "updated_at"))
            expiry_error = CartApiError(
                409,
                "action_expired",
                "Cart action has expired",
                {"action_id": str(action.id), "status": action.status},
            )
        elif action.status == CartAction.Status.PROPOSED:
            action.status = CartAction.Status.CONFIRMED
            action.save(update_fields=("status", "updated_at"))
        if action.status == CartAction.Status.CONFIRMED:
            action.status = CartAction.Status.EXECUTING
            action.save(update_fields=("status", "updated_at"))

    if expiry_error is not None:
        raise expiry_error

    mutation = CartMutation.objects.filter(idempotency_key=action.idempotency_key).first()
    if mutation is not None:
        return _saved_success(action, mutation)
    try:
        return _mutate_fixture(action.id, owner_key)
    except StaleCartCondition as exc:
        raise _stale_error(
            action, owner_key, exc.detail_values, "catalog_cart_or_stock_changed"
        ) from exc
    except CartApiError as exc:
        outcome = _reconcile_or_mark_failed(
            action.id, owner_key, "catalog_verification_failed", exc.message
        )
        if isinstance(outcome, CartApiError):
            raise outcome from exc
        return outcome
    except OperationalError:
        raise
    except Exception as exc:
        mutation = CartMutation.objects.filter(idempotency_key=action.idempotency_key).first()
        if mutation is not None:
            return _saved_success(action, mutation)
        outcome = _reconcile_or_mark_failed(
            action.id, owner_key, "cart_mutation_failed", "Cart mutation could not be completed"
        )
        if isinstance(outcome, CartApiError):
            raise outcome from exc
        return outcome


def confirm_action(owner_key: str, action_id: Any) -> dict[str, Any]:
    return _run_with_database_retry(lambda: _confirm_action_once(owner_key, action_id))


def confirm_text(owner_key: str, dialog_id: Any, text: Any) -> dict[str, Any]:
    normalized_dialog = _validate_identifier(dialog_id, "dialog_id")
    if not isinstance(text, str) or " ".join(text.casefold().strip().split()) not in CONFIRMATION_ALLOWLIST:
        raise CartApiError(
            422,
            "confirmation_required",
            "The message is not an explicit cart confirmation",
        )
    now = timezone.now()
    CartAction.objects.filter(
        owner_key=owner_key,
        dialog_id=normalized_dialog,
        status=CartAction.Status.PROPOSED,
        expires_at__lte=now,
    ).update(status=CartAction.Status.EXPIRED, failure_code="ttl_expired")
    actions = list(
        CartAction.objects.filter(
            owner_key=owner_key,
            dialog_id=normalized_dialog,
            status=CartAction.Status.PROPOSED,
            expires_at__gt=now,
        )[:2]
    )
    if not actions:
        raise CartApiError(409, "no_active_action", "There is no active cart proposal")
    if len(actions) != 1:
        raise CartApiError(
            409,
            "ambiguous_confirmation",
            "Text confirmation does not identify a single cart proposal",
        )
    return confirm_action(owner_key, actions[0].id)
