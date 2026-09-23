from __future__ import annotations

import json
from html import escape
from typing import Any
from uuid import UUID

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST

from cart.errors import CartApiError
from config.observability import record_event, record_metric, safe_identifier
from cart.service import (
    action_snapshot,
    cart_snapshot,
    confirm_action,
    confirm_text,
    create_action,
    get_or_create_cart,
    owner_key_for_session,
)


def _error_response(error: CartApiError) -> JsonResponse:
    record_metric("cart_errors_total")
    record_metric(f"cart_errors_{error.code}_total")
    record_event("cart.error", status_code=error.status_code, error_type=error.code)
    payload: dict[str, Any] = {
        "error": {"code": error.code, "message": error.message},
        **error.extra,
    }
    return JsonResponse(payload, status=error.status_code)


def _owner_key(request: HttpRequest) -> str:
    if request.session.session_key is None:
        request.session.create()
    return owner_key_for_session(request.session.session_key)


def _json_body(request: HttpRequest, *, allow_empty: bool = False) -> dict[str, Any]:
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
    if content_type != "application/json":
        raise CartApiError(415, "unsupported_media_type", "Content-Type must be application/json")
    if not request.body and allow_empty:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CartApiError(400, "invalid_json", "Request body must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise CartApiError(400, "invalid_request", "Request body must be a JSON object")
    return payload


@require_POST
def cart_actions(request: HttpRequest) -> JsonResponse:
    try:
        action, created = create_action(_owner_key(request), _json_body(request))
        record_metric("cart_proposals_total")
        if not created:
            record_metric("cart_proposal_replays_total")
        record_event(
            "cart.proposed",
            action_id=safe_identifier(action.id),
            product_id=action.product_id,
            quantity=action.quantity,
            replay=not created,
        )
        return JsonResponse(action_snapshot(action), status=201 if created else 200)
    except CartApiError as exc:
        return _error_response(exc)


@require_POST
def cart_action_confirm(request: HttpRequest, action_id: str) -> JsonResponse:
    try:
        try:
            parsed_action_id = UUID(action_id)
        except (TypeError, ValueError) as exc:
            raise CartApiError(404, "action_not_found", "Cart action was not found") from exc
        payload = _json_body(request, allow_empty=True)
        if payload:
            raise CartApiError(
                400,
                "immutable_action",
                "Confirmation body cannot change a cart proposal",
            )
        result = confirm_action(_owner_key(request), parsed_action_id)
        record_metric("cart_confirmations_total")
        if result.get("status") == "succeeded":
            record_metric("cart_successes_total")
        record_event(
            "cart.confirmed",
            action_id=safe_identifier(parsed_action_id),
            status=result.get("status"),
        )
        return JsonResponse(result)
    except CartApiError as exc:
        return _error_response(exc)


@require_POST
def cart_action_confirm_text(request: HttpRequest) -> JsonResponse:
    try:
        payload = _json_body(request)
        result = confirm_text(_owner_key(request), payload.get("dialog_id"), payload.get("text"))
        record_metric("cart_confirmations_total")
        if result.get("status") == "succeeded":
            record_metric("cart_successes_total")
        record_event("cart.confirmed_text", status=result.get("status"))
        return JsonResponse(result)
    except CartApiError as exc:
        return _error_response(exc)


@require_GET
def cart_detail(request: HttpRequest) -> JsonResponse:
    record_metric("cart_reads_total")
    get_token(request)
    cart = get_or_create_cart(_owner_key(request))
    return JsonResponse(cart_snapshot(cart))


@require_GET
def demo_cart(request: HttpRequest) -> HttpResponse:
    cart = get_or_create_cart(_owner_key(request))
    snapshot = cart_snapshot(cart)
    rows = "".join(
        "<li>"
        f"{escape(str(item['product'].get('name') or item['product_id']))} — "
        f"{item['quantity']} × {item['unit_price']} {escape(snapshot['currency'])}"
        "</li>"
        for item in snapshot["items"]
    ) or "<li>Корзина пуста</li>"
    body = (
        "<!doctype html><html lang='ru'><meta charset='utf-8'><title>Демо-корзина</title>"
        "<body><main><strong>DEMO FIXTURE — синтетические данные</strong>"
        f"<h1>Корзина</h1><ul>{rows}</ul>"
        f"<p>Итого: {snapshot['total']} {escape(snapshot['currency'])}</p>"
        f"<p>Версия: {snapshot['version']}</p></main></body></html>"
    )
    return HttpResponse(body, content_type="text/html; charset=utf-8")


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    del request, reason
    return _error_response(CartApiError(403, "csrf_failed", "CSRF validation failed"))
