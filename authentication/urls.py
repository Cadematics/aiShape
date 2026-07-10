from django.urls import path
from .views import onshape_callback
from . import views  # <--- THIS IS THE MISSING IMPORT FIX

urlpatterns = [
    path('oauth/callback/', onshape_callback, name='onshape_callback'),
    path('api/chat/', views.api_chat, name='api_chat'), # <-- The new pipeline link

    path('api/logs/', views.view_agent_logs, name='view_agent_logs'),
    path('api/logs/clear/', views.clear_agent_logs, name='clear_agent_logs'),
]
