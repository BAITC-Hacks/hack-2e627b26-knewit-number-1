from django.urls import include, path


urlpatterns = [
    path("", include("cart.urls")),
    path("", include("catalog.urls")),
    path("", include("assistant.urls")),
]
