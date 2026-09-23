from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from cart.errors import CartApiError
from cart.service import action_snapshot, create_action, owner_key_for_session
from catalog.errors import CatalogError
from catalog.providers import get_catalog_provider
from catalog.search import SearchIndexError, search_catalog, semantic_search_catalog
from catalog.safety import sanitize_catalog_payload, sanitize_text, sanitize_url
from config.observability import observe_latency, record_event, record_metric
from dialog.attachments import AttachmentError, extract_attachment
from dialog.llm import (
    LLMError,
    OpenAIResponsesOrchestrator,
    PROCESSING_TOKEN_RU,
    _catalog_identifier,
    llm_is_configured,
)
from dialog.payment_safety import (
    PAYMENT_DATA_MESSAGE,
    PAYMENT_DATA_REDACTED,
    PaymentDataDetected,
    contains_payment_data,
)
from catalog.providers.fixture import PRODUCTS
from knowledge_base.engine import answer_query


MAX_HISTORY = 50
MAX_MESSAGE_LENGTH = 1200
_GREETING_WORDS = {
    "привет",
    "здравствуйте",
    "здравствуй",
    "добрый день",
    "доброе утро",
    "добрый вечер",
    "салам",
    "сәлем",
    "сәлеметсіз бе",
}
_CAPABILITY_PHRASES = {
    "\u0447\u0442\u043e \u0442\u044b \u0443\u043c\u0435\u0435\u0448\u044c",
    "\u0447\u0442\u043e \u0442\u044b \u0443\u043c\u0435\u0435\u0448\u044c?",
    "\u043a\u0430\u043a \u0442\u044b \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0448\u044c",
}
_PRODUCT_CLARIFICATION_PHRASES = {
    "\u043d\u0430\u0439\u0434\u0438 \u0442\u043e\u0432\u0430\u0440",
    "\u043f\u043e\u043a\u0430\u0436\u0438 \u0442\u043e\u0432\u0430\u0440",
    "\u043d\u0443\u0436\u0435\u043d \u0442\u043e\u0432\u0430\u0440",
}
_REFERENCE_WORDS = ("этот товар", "этот вариант", "эту позицию", "этот")
_SECOND_WORDS = ("второй", "2-й", "2й")
_DOCUMENT_FIELDS = {
    "certificate": "Сертификат",
    "certificates": "Сертификат",
    "document": "Документ",
    "documents": "Документ",
    "instruction": "Инструкция",
    "instructions": "Инструкция",
    "file": "Файл",
    "files": "Файл",
}


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
    return {
        "dialog_id": uuid.uuid4().hex,
        "version": 0,
        "state": "idle",
        "history": [_welcome()],
        "attachments": {},
    }


def _get_dialog(request: HttpRequest) -> dict[str, Any]:
    dialog = request.session.get("dialog_context")
    if not isinstance(dialog, dict) or not isinstance(dialog.get("history"), list):
        dialog = _new_dialog()
        request.session["dialog_context"] = dialog
        request.session.modified = True
    else:
        changed = False
        for message in dialog["history"]:
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and contains_payment_data(content):
                message["content"] = PAYMENT_DATA_REDACTED
                message["state"] = "blocked"
                changed = True
        if changed:
            request.session["dialog_context"] = dialog
            request.session.modified = True
    if not isinstance(dialog.get("attachments"), dict):
        dialog["attachments"] = {}
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
    normalized = re.sub(r"[!?.,:;]+", "", text.casefold()).strip()
    if normalized in _CAPABILITY_PHRASES:
        return (
            "\u042f \u043c\u043e\u0433\u0443 \u043d\u0430\u0439\u0442\u0438 \u0442\u043e\u0432\u0430\u0440 \u043f\u043e \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044e, \u0430\u0440\u0442\u0438\u043a\u0443\u043b\u0443 \u0438\u043b\u0438 \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0430\u043c, \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0446\u0435\u043d\u0443 \u0438 \u043d\u0430\u043b\u0438\u0447\u0438\u0435, \u043f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0430\u043d\u0430\u043b\u043e\u0433\u0438. \u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u00ab\u043d\u0430\u0439\u0434\u0438 \u043a\u0430\u0431\u0435\u043b\u044c 3\u00d72,5 \u043c\u043c\u00b2\u00bb \u0438\u043b\u0438 \u00ab\u043d\u0430\u0439\u0434\u0438 \u0442\u043e\u0432\u0430\u0440 \u043f\u043e \u0430\u0440\u0442\u0438\u043a\u0443\u00bb.",
            [],
        )
    if normalized in _PRODUCT_CLARIFICATION_PHRASES:
        return (
            "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435, \u0430\u0440\u0442\u0438\u043a\u0443\u043b \u0438\u043b\u0438 \u043d\u0443\u0436\u043d\u044b\u0435 \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0438 \u0442\u043e\u0432\u0430\u0440\u0430.",
            [],
        )
    if normalized in _GREETING_WORDS:
        return (
            "\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435! \u041f\u043e\u043c\u043e\u0433\u0443 \u043d\u0430\u0439\u0442\u0438 \u0442\u043e\u0432\u0430\u0440, \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043d\u0430\u043b\u0438\u0447\u0438\u0435 \u0438 \u043f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0430\u043d\u0430\u043b\u043e\u0433. \u0427\u0442\u043e \u0438\u0449\u0435\u0442\u0435?",
            [],
        )
    knowledge_answer = answer_query(text)
    if knowledge_answer["status"] != "not_found":
        return sanitize_text(knowledge_answer["answer"]), []
    try:
        result = search_catalog(text, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    except ValueError:
        result = semantic_search_catalog(text, settings.CATALOG_INDEX_PATH, settings.CATALOG_SEARCH_MAX_RESULTS)
    except SearchIndexError:
        # The public search route correctly remains unavailable until its full
        # persisted index has been synchronized.  The fixture chat, however,
        # must stay usable immediately after `migrate` for the local demo and
        # tests.  This bounded fallback is never used with the live provider.
        if settings.CATALOG_PROVIDER != "fixture":
            raise
        terms = [term for term in re.findall(r"[\w]+", text.casefold()) if len(term) > 1]
        matches = []
        for product in PRODUCTS:
            searchable = " ".join(
                [
                    str(product.get("name") or ""),
                    str(product.get("article") or ""),
                    str((product.get("properties") or {}).get("CATEGORY") or ""),
                    " ".join((product.get("properties") or {}).get("SEARCH_ALIASES") or []),
                ]
            ).casefold()
            score = sum(term in searchable for term in terms)
            if score:
                matches.append((score, int(product["id"]), product))
        matches.sort(key=lambda candidate: (-candidate[0], candidate[1]))
        result = {
            "query": text,
            "mode": "fixture_fallback",
            "results": [item for _, _, item in matches[: settings.CATALOG_SEARCH_MAX_RESULTS]],
        }
    products = [sanitize_catalog_payload(item) for item in result.get("results", []) if isinstance(item, dict)]
    if not products:
        return "Не нашёл подходящую позицию в локальном индексе. Уточните артикул, назначение или характеристику.", []
    return f"Нашёл {len(products)} вариант(а). Уточните, какой товар использовать дальше.", products


def _catalog_detail(product_id: Any) -> dict[str, Any] | None:
    """Fetch the selected product from the detail API, never from the search index."""
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id < 1:
        return None
    try:
        product = get_catalog_provider().get_product(product_id)
    except (CatalogError, KeyError, TypeError, ValueError):
        return None
    if not isinstance(product, dict) or product.get("id") != product_id:
        return None
    return sanitize_catalog_payload(product)


def _document_links(product: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize only safe, renderable document URLs from catalog detail data."""
    links: list[dict[str, str]] = []

    def add(value: Any, default_label: str) -> None:
        if isinstance(value, str):
            url = sanitize_url(value)
            if url:
                links.append({"label": default_label, "url": url})
            return
        if isinstance(value, list):
            for item in value:
                add(item, default_label)
            return
        if not isinstance(value, dict):
            return
        label = sanitize_text(value.get("name") or value.get("title") or default_label)
        for key in ("url", "href", "link"):
            raw_url = value.get(key)
            if isinstance(raw_url, str):
                url = sanitize_url(raw_url)
                if url:
                    links.append({"label": label or default_label, "url": url})
                    return

    for field, label in _DOCUMENT_FIELDS.items():
        add(product.get(field), label)
    properties = product.get("properties")
    if isinstance(properties, dict):
        for key, value in properties.items():
            normalized_key = str(key).casefold()
            if any(token in normalized_key for token in ("cert", "сертифик", "document", "документ", "instruction", "инструкц")):
                add(value, "Документ")

    unique: list[dict[str, str]] = []
    for link in links:
        if link not in unique:
            unique.append(link)
    return unique[:10]


def _detail_answer(product: dict[str, Any]) -> dict[str, Any]:
    """Render deterministic, verified catalog facts for a chosen product."""
    product_id = product["id"]
    availability = product.get("availability")
    characteristics = product.get("properties")
    documents = _document_links(product)
    fact: dict[str, Any] = {
        "type": "product",
        "product_id": product_id,
        "source": "catalog_detail_api",
        "name": product.get("name"),
        "article": product.get("article"),
        "availability": availability if isinstance(availability, dict) else None,
        "characteristics": characteristics if isinstance(characteristics, dict) else {},
        "card_url": product.get("url"),
    }
    if documents:
        fact["documents"] = documents
    name = sanitize_text(product.get("name") or "выбранный товар")
    content = f"Проверил актуальные данные для «{name}». Наличие и характеристики приведены ниже."
    if documents:
        content += " Также доступны ссылки на сертификаты или документы."
    return {
        "content": content,
        "products": [product],
        "facts": [fact],
        "sources": [{"type": "catalog_detail", "url": f"/api/products/detail?id={product_id}"}],
        "source_status": "sourced",
    }


def _missing_detail_answer() -> dict[str, Any]:
    """Do not fall back to an unverified search snapshot for a chosen product."""
    return {
        "content": "Не удалось проверить актуальные данные выбранного товара. Попробуйте ещё раз.",
        "products": [],
        "facts": [],
        "source_status": "missing",
    }


def _numeric_product_id(text: str) -> int | None:
    """An all-numeric dialog turn can be a selected internal product ID."""
    if not re.fullmatch(r"\d+", text.strip()):
        return None
    try:
        product_id = int(text)
    except ValueError:
        return None
    return product_id if product_id > 0 else None


def _fallback_catalog_query(text: str) -> str:
    """Keep an exact article lookup deterministic when the LLM plan is rejected."""
    return _catalog_identifier(text) or text


def _run_llm(history: list[dict[str, Any]], attachments: dict[str, Any]) -> dict[str, Any]:
    enriched_history: list[dict[str, Any]] = []
    for message in history:
        item = dict(message)
        attachment_id = item.get("attachment_id")
        attachment = attachments.get(attachment_id) if isinstance(attachment_id, str) else None
        if isinstance(attachment, dict):
            item["attachment_context"] = attachment.get("text", "")
        enriched_history.append(item)
    return OpenAIResponsesOrchestrator().run(enriched_history).message


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


def _attachment_receipt(attachment: dict[str, Any]) -> dict[str, Any]:
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    text = attachment.get("text") if isinstance(attachment.get("text"), str) else ""
    details = "Доступный текст извлечён и передан в безопасный контекст диалога." if text else "Текст для извлечения не найден; сохранены доступные метаданные."
    return {
        "content": f"Файл «{attachment.get('name', 'вложение')}» принят. {details}",
        "attachment": _public_attachment(attachment),
        "facts": [{"type": "attachment", "metadata": metadata}],
    }


def _process(
    request: HttpRequest,
    dialog: dict[str, Any],
    text: str,
    attachment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if attachment is not None:
        if llm_is_configured():
            try:
                return _run_llm(dialog.get("history", []), dialog.get("attachments", {}))
            except LLMError as exc:
                record_metric("llm_degraded_total")
                record_event(
                    "llm.orchestration.completed",
                    status="degraded",
                    error_code=exc.code,
                    retryable=exc.retryable,
                )
                response = _attachment_receipt(attachment)
                response["degraded"] = True
                response["degradation_reason"] = "llm_unavailable"
                return response
        return _attachment_receipt(attachment)
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
        detail = _catalog_detail(reference.get("id"))
        if detail is not None:
            response = _detail_answer(detail)
            response["resolved_reference"] = {"product_id": detail["id"]}
            return response
        response = _missing_detail_answer()
        response["resolved_reference"] = {"product_id": reference["id"]}
        return response
    if llm_is_configured():
        try:
            return _run_llm(dialog.get("history", []), dialog.get("attachments", {}))
        except LLMError as exc:
            # Controlled degradation keeps catalog/KB answers available. Never
            # return an upstream body, API key, or prompt content to the client.
            record_metric("llm_degraded_total")
            record_event(
                "llm.orchestration.completed",
                status="degraded",
                error_code=exc.code,
                retryable=exc.retryable,
            )
    # A bare numeric ID is an explicit selection, so skip the search snapshot
    # and read the authoritative detail endpoint directly.
    product_id = _numeric_product_id(text)
    if product_id is not None:
        detail = _catalog_detail(product_id)
        response = _detail_answer(detail) if detail is not None else _missing_detail_answer()
        if llm_is_configured():
            response["degraded"] = True
            response["degradation_reason"] = "llm_unavailable"
        return response
    content, products = _search_answer(_fallback_catalog_query(text))
    response = {"content": sanitize_text(content), "products": products}
    if llm_is_configured():
        response["degraded"] = True
        response["degradation_reason"] = "llm_unavailable"
    return response


def _json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body


def _public_attachment(attachment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: attachment[key]
        for key in ("id", "name", "size", "type", "metadata")
        if key in attachment
    }


def _validated_attachment(body: dict[str, Any], dialog: dict[str, Any]) -> dict[str, Any] | None:
    attachment_id = body.get("attachment_id")
    if attachment_id is None:
        return None
    if not isinstance(attachment_id, str) or not re.fullmatch(r"[a-f0-9]{32}", attachment_id):
        raise ValueError("attachment_id is invalid")
    attachment = dialog.get("attachments", {}).get(attachment_id)
    if not isinstance(attachment, dict) or attachment.get("dialog_id") != dialog["dialog_id"]:
        raise ValueError("attachment_id does not belong to the current dialog")
    return attachment


def _validated_message(request: HttpRequest, dialog: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    body = _json_body(request)
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError("text must be a non-empty string up to 1200 characters")
    if body.get("dialog_id") and body["dialog_id"] != dialog["dialog_id"]:
        raise ValueError("dialog_id does not match the current session dialog")
    text = text.strip()
    if contains_payment_data(text):
        raise PaymentDataDetected
    return text, _validated_attachment(body, dialog)


def _append_user_message(
    dialog: dict[str, Any], text: str, attachment: dict[str, Any] | None = None
) -> dict[str, Any]:
    if contains_payment_data(text):
        raise PaymentDataDetected
    dialog["state"] = "processing"
    dialog["version"] += 1
    user_message = {
        "id": uuid.uuid4().hex,
        "role": "user",
        "content": text,
        "state": "sent",
    }
    if attachment is not None:
        user_message["attachment_id"] = attachment["id"]
        user_message["attachment"] = _public_attachment(attachment)
    dialog["history"].append(user_message)
    return user_message


@require_GET
def dialog_state(request: HttpRequest) -> JsonResponse:
    dialog = _get_dialog(request)
    return JsonResponse({"dialog_id": dialog["dialog_id"], "state": dialog.get("state", "idle"), "history": dialog["history"]})


def _attachment_error_response(exc: AttachmentError) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": exc.code, "message": exc.message}},
        status=exc.status_code,
    )


def _close_uploaded_files(files: list[Any]) -> None:
    for uploaded in files:
        close = getattr(uploaded, "close", None)
        if callable(close):
            close()


@require_POST
def dialog_upload(request: HttpRequest) -> JsonResponse:
    dialog = _get_dialog(request)
    files = request.FILES.getlist("file")
    raw_dialog_id = request.POST.get("dialog_id")
    if raw_dialog_id and raw_dialog_id != dialog["dialog_id"]:
        _close_uploaded_files(files)
        return JsonResponse(
            {"error": {"code": "dialog_error", "message": "dialog_id does not match the current session dialog"}},
            status=400,
        )
    if len(files) != 1:
        _close_uploaded_files(files)
        return JsonResponse(
            {"error": {"code": "invalid_upload", "message": "Exactly one file must be uploaded"}},
            status=400,
        )
    if len(dialog["attachments"]) >= settings.ATTACHMENT_MAX_STORED_PER_DIALOG:
        _close_uploaded_files(files)
        return JsonResponse(
            {"error": {"code": "attachment_limit_exceeded", "message": "Too many attachments in the current dialog"}},
            status=429,
        )
    try:
        attachment = extract_attachment(files[0])
    except AttachmentError as exc:
        return _attachment_error_response(exc)
    attachment["id"] = uuid.uuid4().hex
    attachment["dialog_id"] = dialog["dialog_id"]
    dialog["attachments"][attachment["id"]] = attachment
    _save_dialog(request, dialog)
    return JsonResponse({"attachment": _public_attachment(attachment)}, status=201)


@require_POST
def dialog_message(request: HttpRequest) -> JsonResponse:
    dialog = _get_dialog(request)
    try:
        text, attachment = _validated_message(request, dialog)
        _append_user_message(dialog, text, attachment)
        response = _process(request, dialog, text, attachment)
        assistant_message = {"id": uuid.uuid4().hex, "role": "assistant", "state": "done", **response}
        dialog["history"].append(assistant_message)
        dialog["state"] = "done"
        _save_dialog(request, dialog)
        return JsonResponse({"dialog_id": dialog["dialog_id"], "state": "done", "message": assistant_message})
    except PaymentDataDetected:
        dialog["state"] = "blocked"
        _save_dialog(request, dialog)
        return JsonResponse(
            {
                "dialog_id": dialog["dialog_id"],
                "state": "blocked",
                "retryable": False,
                "error": {"code": "payment_data_detected", "message": PAYMENT_DATA_MESSAGE},
            },
            status=400,
        )
    except (ValueError, SearchIndexError) as exc:
        dialog["state"] = "error"
        _save_dialog(request, dialog)
        return JsonResponse({"dialog_id": dialog["dialog_id"], "state": "error", "retryable": isinstance(exc, SearchIndexError), "error": {"code": "dialog_error", "message": str(exc)}}, status=400 if isinstance(exc, ValueError) else 503)


def _sse(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {data}\n\n"


def _text_chunks(value: Any, size: int = 160):
    text = str(value or "")
    for offset in range(0, len(text), size):
        yield text[offset : offset + size]


@require_POST
def dialog_message_stream(request: HttpRequest) -> StreamingHttpResponse | JsonResponse:
    dialog = _get_dialog(request)
    try:
        text, attachment = _validated_message(request, dialog)
    except PaymentDataDetected:
        dialog["state"] = "blocked"
        _save_dialog(request, dialog)
        return JsonResponse(
            {
                "dialog_id": dialog["dialog_id"],
                "state": "blocked",
                "retryable": False,
                "error": {"code": "payment_data_detected", "message": PAYMENT_DATA_MESSAGE},
            },
            status=400,
        )
    except ValueError as exc:
        return JsonResponse(
            {
                "dialog_id": dialog["dialog_id"],
                "state": "error",
                "retryable": False,
                "error": {"code": "dialog_error", "message": str(exc)},
            },
            status=400,
        )

    _append_user_message(dialog, text, attachment)
    _save_dialog(request, dialog)
    stream_started = time.perf_counter()

    def events():
        # Emit a visible token before any upstream call so the UI can render
        # progress immediately while catalog/knowledge tools are running.
        yield _sse("state", {"dialog_id": dialog["dialog_id"], "state": "processing"})
        observe_latency("dialog_time_to_first_token", (time.perf_counter() - stream_started) * 1000)
        record_metric("dialog_streams_total")
        yield _sse("delta", {"phase": "progress", "text": PROCESSING_TOKEN_RU})
        try:
            response = _process(request, dialog, text, attachment)
            assistant_message = {
                "id": uuid.uuid4().hex,
                "role": "assistant",
                "state": "done",
                **response,
            }
            dialog["history"].append(assistant_message)
            dialog["state"] = "done"
            _save_dialog(request, dialog)
            request.session.save()
            for chunk in _text_chunks(assistant_message.get("content")):
                yield _sse("delta", {"phase": "answer", "text": chunk})
            yield _sse("message", assistant_message)
            yield _sse("done", {"dialog_id": dialog["dialog_id"], "state": "done"})
        except (ValueError, SearchIndexError) as exc:
            dialog["state"] = "error"
            _save_dialog(request, dialog)
            request.session.save()
            yield _sse(
                "error",
                {
                    "code": "dialog_error",
                    "message": str(exc),
                    "retryable": isinstance(exc, SearchIndexError),
                },
            )

    response = StreamingHttpResponse(events(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
def dialog_retry(request: HttpRequest, message_id: str) -> JsonResponse:
    dialog = _get_dialog(request)
    previous = next((item for item in reversed(dialog["history"]) if item.get("id") == message_id and item.get("role") == "user"), None)
    if previous is None:
        return JsonResponse({"error": {"code": "message_not_found", "message": "User message was not found"}}, status=404)
    if previous.get("state") == "blocked" or contains_payment_data(previous.get("content")):
        previous["content"] = PAYMENT_DATA_REDACTED
        previous["state"] = "blocked"
        _save_dialog(request, dialog)
        return JsonResponse(
            {"dialog_id": dialog["dialog_id"], "state": "blocked", "retryable": False, "error": {"code": "payment_data_detected", "message": PAYMENT_DATA_MESSAGE}},
            status=400,
        )
    payload = {"text": previous["content"], "dialog_id": dialog["dialog_id"]}
    if isinstance(previous.get("attachment_id"), str):
        payload["attachment_id"] = previous["attachment_id"]
    request._body = __import__("json").dumps(payload).encode()
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
