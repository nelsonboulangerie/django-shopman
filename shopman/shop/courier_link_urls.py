"""Rotas públicas da página do entregador da casa (DEV-2026-030). Montadas em ``api/v1/courier/``."""

from __future__ import annotations

from django.urls import path

from shopman.shop.views.courier_link import CourierRideClaimView, CourierRideEventView, CourierRideView

urlpatterns = [
    path("rides/<str:token>/", CourierRideView.as_view(), name="courier-ride-link"),
    path("rides/<str:token>/claim/", CourierRideClaimView.as_view(), name="courier-ride-link-claim"),
    path("rides/<str:token>/events/", CourierRideEventView.as_view(), name="courier-ride-link-events"),
]
