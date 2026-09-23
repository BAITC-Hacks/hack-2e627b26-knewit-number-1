from django.urls import include, path

from config.observability import metrics_response, readiness_response


urlpatterns = [
    path("", include("cart.urls")),
    path("", include("gateway.urls")),
    path("", include("knowledge_base.urls")),
    path("", include("dialog.urls")),
    path("", include("catalog.urls")),
    path("", include("assistant.urls")),
    path("metrics", metrics_response, name="metrics"),
    path("ready", readiness_response, name="readiness"),
]
