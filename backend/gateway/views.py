from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def session_info(request):
    user = getattr(request, "user", None)
    authenticated = bool(user is not None and user.is_authenticated)
    return JsonResponse(
        {
            "session_type": "authenticated" if authenticated else "guest",
            "authenticated": authenticated,
            "session_active": bool(request.session.session_key),
        }
    )
