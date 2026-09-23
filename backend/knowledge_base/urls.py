from django.urls import path

from .views import knowledge_answer


urlpatterns = [path("api/knowledge-base", knowledge_answer, name="knowledge-base-answer")]
