from django.urls import path

from gateway import views


urlpatterns = [path("api/session", views.session_info, name="session-info")]
