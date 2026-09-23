from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from assistant.errors import AssistantApiError
from dialog.payment_safety import PAYMENT_DATA_MESSAGE, contains_payment_data
from assistant.service import generate_reply, resolve_dialog_language


def _error_response(error: AssistantApiError) -> JsonResponse:
    return JsonResponse({"error": {"code": error.code, "message": error.message}, **error.extra}, status=error.status_code)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
    if content_type != "application/json":
        raise AssistantApiError(415, "unsupported_media_type", "Content-Type must be application/json")
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssistantApiError(400, "invalid_json", "Request body must contain valid JSON") from exc
    if not isinstance(body, dict):
        raise AssistantApiError(400, "invalid_request", "Request body must be a JSON object")
    return body


def _language_result(request: HttpRequest, payload: dict[str, Any], *, message: Any = None) -> dict[str, Any]:
    try:
        result = resolve_dialog_language(
            request,
            dialog_id=payload.get("dialog_id"),
            explicit_language=payload.get("language"),
            message=message,
        )
    except ValueError as exc:
        raise AssistantApiError(400, "invalid_request", str(exc)) from exc
    return result


@require_POST
def chat_language(request: HttpRequest) -> JsonResponse:
    try:
        return JsonResponse(_language_result(request, _json_body(request)))
    except AssistantApiError as exc:
        return _error_response(exc)


@require_POST
def chat_message(request: HttpRequest) -> JsonResponse:
    try:
        payload = _json_body(request)
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise AssistantApiError(400, "invalid_request", "text must be a non-empty string up to 4000 characters")
        text = text.strip()
        if contains_payment_data(text):
            raise AssistantApiError(400, "payment_data_detected", PAYMENT_DATA_MESSAGE)
        response = _language_result(request, payload, message=text)
        response["reply"] = generate_reply(text=text, language=response["language"])
        return JsonResponse(response)
    except AssistantApiError as exc:
        return _error_response(exc)
