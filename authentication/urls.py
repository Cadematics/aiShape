from django.urls import path
from .views import onshape_callback

urlpatterns = [
    path('oauth/callback/', onshape_callback, name='onshape_callback'),
]
