"""URL do webhook do concierge, montada em ``/api/webhooks/`` pelo ``config/urls.py``."""

from django.urls import path

from .webhook import ConciergeInboundView

app_name = "concierge"

urlpatterns = [
    path("manychat/conversation/", ConciergeInboundView.as_view(), name="manychat-conversation"),
]
