from __future__ import annotations

import re
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from cart.errors import CartApiError
from cart.service import action_snapshot, create_action, owner_key_for_session
from catalog.search import SearchIndexError, search_catalog, semantic_search_catalog
from catalog.safety import sanitize_catalog_payload, sanitize_text
from knowledge_base.engine import answer_query


MAX_HISTORY = 50
MAX_MESSAGE_LENGTH = 1200
_REFERENCE_WORDS = ("этот товар", "этот вариант", "эту позицию", "этот")
_SECOND_WORDS = ("второй", "2-й", "2й")


def _welcome() -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": (
            "Здравствуйте! Я помогу найти электротехнический товар, проверить наличие "
            "и подобрать аналог. Можно спросить: «найди товар по артикулу», "
            "«покажи второй вариант» или «добавь два» после выбора позиции."
        ),
        "suggestions": [
            "Найди товар по артикулу",
            "Покажи аналоги",
            "Уточни наличие и характеристики",
        ],
    }


def _new_dialog() -> dict[str, Any]:
    return {"dialog_id": uuid.uuid4().hex, "version": 0, "state": "idle", "history": [_welcome()]}


def _get_dialog(request: HttpRequest) -> dict[str, Any]:
    dialog = request.session.get("dialog_context")
    if not isinstance(dialog, dict) or not isinstance(dialog.get("history"), list):
        dialog = _new_dialog()
        request.session["dialog_context"] = dialog
        request.session.modified = True
    return dialog


def _save_dialog(request: HttpRequest, dialog: dict[str, Any]) -> None:
    dialog["history"] = dialog.get("history", [])[-MAX_HISTORY:]
    request.session["dialog_context"] = dialog
    request.session.modified = True


def _products_from_history(dialog: dict[str, Any]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for message in reversed(dialog.get("history", [])):
        if message.get("role") != "assistant":
            continue
        for product in message.get("products", []):
            if isinstance(product, dict) and product.get("id") not in {item.get("id") for item in products}:
                products.append(product)
        if products:
            break
    return products


def _quantity(text: str) -> int | None:
    match = re.search(r"(?:добавь|добавить|нужно)\s+(\d+)", text.casefold())
    if match:
        return int(match.group(1))
    words = {"один": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5}
    match = re.search(r"(?:добавь|добавить|нужно)\s+([а-яё]+)", text.casefold())
    return words.get(match.group(1)) if match else None


def _resolve_reference(dialog: dict[str, Any], text: str) -> dict[str, Any] | None:
    products = _products_from_history(dialog)
    normalized = text.casefold()
    if any(word in normalized for word in _SECOND_WORDS):
        return products[1] if len(products) > 1 else None
    if any(word in normalized for word in _REFERENCE_WORDS):
        return products[0] if products else None
    if any(word in normalized for word in ("добавь", "добавить")):
        return products[0] if products else None
    return None


def _search_answer(text: str) -> tuple[str, list[dict[str, Any]]]:
    knowledge_answer = answer_query(text)
    if knowledge_answer["status"] != "not_found":
        return sanitize_text(knowledge_answer["answer"]), []
    try:
        result = search_catalog(text, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    except ValueError:
        result = semantic_search_catalog(text, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    products = [sanitize_catalog_payload(item) for item in result.get("results", []) if isinstance(item, dict)]
    if not products:
        return "Не нашёл подходящую позицию в локальном индексе. Уточните артикул, назначение или характеристику.", []
    return f"Нашёл {len(products)} вариант(а). Уточните, какой товар использовать дальше.", products


def _make_cart_proposal(request: HttpRequest, dialog: dict[str, Any], product: dict[str, Any], quantity: int) -> dict[str, Any] | None:
    if request.session.session_key is None:
        request.session.create()
    try:
        action, _ = create_action(
            owner_key_for_session(request.session.session_key),
            {
                "dialog_id": dialog["dialog_id"],
                "message_id": uuid.uuid4().hex,
                "message_version": dialog["version"],
                "product_id": int(product["id"]),
                "quantity": quantity,
                "offer_id": None,
            },
        )
    except (CartApiError, KeyError, TypeError, ValueError):
        return None
    return action_snapshot(action)


def _process(request: HttpRequest, dialog: dict[str, Any], text: str) -> dict[str, Any]:
    reference = _resolve_reference(dialog, text)
    quantity = _quantity(text)
    is_add = any(word in text.casefold() for word in ("добавь", "добавить"))
    if is_add and reference is not None:
        response: dict[str, Any] = {
            "content": f"Подготовил предложение добавить {quantity or 1} шт. выбранного товара. Подтвердите добавление явно.",
            "resolved_reference": {"product_id": reference["id"], "quantity": quantity or 1},
            "products": [reference],
        }
        proposal = _make_cart_proposal(request, dialog, reference, quantity or 1)
        if proposal is not None:
            response["cart_proposal"] = proposal
        return response
    if reference is not None:
        return {
            "content": "Понял ссылку на выбранный товар из предыдущего сообщения.",
            "resolved_reference": {"product_id": reference["id"]},
            "products": [reference],
        }
    content, products = _search_answer(text)
    return {"content": sanitize_text(content), "products": products}


def _json_body(request: HttpRequest) -> dict[str, Any]:
    import json

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body


@require_GET
def dialog_state(request: HttpRequest) -> JsonResponse:
    dialog = _get_dialog(request)
    return JsonResponse({"dialog_id": dialog["dialog_id"], "state": dialog.get("state", "idle"), "history": dialog["history"]})


@require_POST
def dialog_message(request: HttpRequest) -> JsonResponse:
    dialog = _get_dialog(request)
    try:
        body = _json_body(request)
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE_LENGTH:
            raise ValueError("text must be a non-empty string up to 1200 characters")
        if body.get("dialog_id") and body["dialog_id"] != dialog["dialog_id"]:
            raise ValueError("dialog_id does not match the current session dialog")
        dialog["state"] = "processing"
        dialog["version"] += 1
        user_message = {"id": uuid.uuid4().hex, "role": "user", "content": text.strip(), "state": "sent"}
        dialog["history"].append(user_message)
        response = _process(request, dialog, text.strip())
        assistant_message = {"id": uuid.uuid4().hex, "role": "assistant", "state": "done", **response}
        dialog["history"].append(assistant_message)
        dialog["state"] = "done"
        _save_dialog(request, dialog)
        return JsonResponse({"dialog_id": dialog["dialog_id"], "state": "done", "message": assistant_message})
    except (ValueError, SearchIndexError) as exc:
        dialog["state"] = "error"
        _save_dialog(request, dialog)
        return JsonResponse({"dialog_id": dialog["dialog_id"], "state": "error", "retryable": isinstance(exc, SearchIndexError), "error": {"code": "dialog_error", "message": str(exc)}}, status=400 if isinstance(exc, ValueError) else 503)


@require_POST
def dialog_retry(request: HttpRequest, message_id: str) -> JsonResponse:
    dialog = _get_dialog(request)
    previous = next((item for item in reversed(dialog["history"]) if item.get("id") == message_id and item.get("role") == "user"), None)
    if previous is None:
        return JsonResponse({"error": {"code": "message_not_found", "message": "User message was not found"}}, status=404)
    request._body = __import__("json").dumps({"text": previous["content"], "dialog_id": dialog["dialog_id"]}).encode()
    return dialog_message(request)


@require_POST
def dialog_cancel(request: HttpRequest) -> JsonResponse:
    dialog = _get_dialog(request)
    dialog["state"] = "cancelled"
    _save_dialog(request, dialog)
    return JsonResponse({"dialog_id": dialog["dialog_id"], "state": "cancelled"})


@require_http_methods(["DELETE", "POST"])
def dialog_clear(request: HttpRequest) -> JsonResponse:
    dialog = _new_dialog()
    request.session["dialog_context"] = dialog
    request.session.modified = True
    return JsonResponse({"dialog_id": dialog["dialog_id"], "state": "idle", "history": dialog["history"]})
