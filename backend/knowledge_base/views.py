from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .engine import answer_query


@require_GET
def knowledge_answer(request):
    try:
        result = answer_query(
            request.GET.get("q", ""),
            request.GET.get("lang", "ru"),
            request.GET.get("intent") or None,
        )
    except ValueError as exc:
        return JsonResponse({"error": {"code": "invalid_query", "message": str(exc)}}, status=400)
    return JsonResponse(result, safe=True)
