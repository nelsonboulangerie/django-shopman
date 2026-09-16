"""Rotas canônicas de eventos e futuros callbacks do concierge."""

from django.urls import path

from .webhook import ConciergeEventView

app_name = "concierge"

urlpatterns = [
    # Callbacks de entrega terão uma rota irmã e normalizador próprio no adapter;
    # não compartilharão o contrato de eventos recebidos.
    path(
        "concierge/<slug:connection_key>/events/",
        ConciergeEventView.as_view(),
        name="connection-events",
    ),
]
