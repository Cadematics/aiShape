



from django.urls import path
from . import views

urlpatterns = [
    path('oauth/callback/', views.onshape_callback, name='onshape_callback'),
    path('api/chat/', views.api_chat, name='api_chat'),
    path('api/logs/', views.view_agent_logs, name='view_agent_logs'),
    path('api/logs/clear/', views.clear_agent_logs, name='clear_agent_logs'),
]