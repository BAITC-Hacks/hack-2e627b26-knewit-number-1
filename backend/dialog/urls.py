from django.urls import path

from dialog import views


urlpatterns = [
    path("api/dialog", views.dialog_state, name="dialog-state"),
    path("api/dialog/messages", views.dialog_message, name="dialog-message"),
    path("api/dialog/messages/stream", views.dialog_message_stream, name="dialog-message-stream"),
    path("api/dialog/messages/<str:message_id>/retry", views.dialog_retry, name="dialog-retry"),
    path("api/dialog/cancel", views.dialog_cancel, name="dialog-cancel"),
    path("api/dialog/history", views.dialog_clear, name="dialog-clear"),
    path("api/dialog/clear", views.dialog_clear, name="dialog-clear-alias"),
]
