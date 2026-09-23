from django.urls import path

from assistant import views


urlpatterns = [
    path("api/chat/language", views.chat_language, name="chat-language"),
    path("api/chat/messages", views.chat_message, name="chat-message"),
]
