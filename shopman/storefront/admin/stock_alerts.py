"""Canonical Unfold changelists for stock-alert audit and diagnosis."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.storefront.models import (
    StockAlertDelivery,
    StockAlertOccurrence,
    StockAlertSubscription,
)


class PendingAlertFilter(admin.SimpleListFilter):
    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [
            ("ativa", "Ativa"),
            ("pausada", "Pausada"),
            ("sem_prova", "Sem prova válida"),
            ("cancelada", "Cancelada"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "ativa":
            return queryset.active()
        if self.value() == "pausada":
            return queryset.filter(
                revoked_at__isnull=True,
                paused_at__isnull=False,
                proof_status="verified",
            )
        if self.value() == "sem_prova":
            return queryset.filter(revoked_at__isnull=True).exclude(proof_status="verified")
        if self.value() == "cancelada":
            return queryset.filter(revoked_at__isnull=False)
        return queryset


@admin.register(StockAlertSubscription)
class StockAlertSubscriptionAdmin(ModelAdmin):
    list_display = ("sku", "who_display", "channel_ref", "status_badge", "subscribed_at")
    list_filter = (PendingAlertFilter, "channel_ref")
    search_fields = ("sku", "customer_ref", "contact_phone")
    ordering = ("-subscribed_at",)
    date_hierarchy = "subscribed_at"
    readonly_fields = (
        "sku",
        "alert_type",
        "channel_ref",
        "customer_ref",
        "contact_phone",
        "subscribed_at",
        "notified_at",
        "paused_at",
        "revoked_at",
        "expires_at",
    )
    list_fullwidth = True
    compressed_fields = True

    @admin.display(description="quem espera")
    def who_display(self, obj):
        return obj.customer_ref or obj.contact_phone or "—"

    @display(
        description="situação",
        label={
            "Ativa": "success",
            "Pausada": "warning",
            "Sem prova": "danger",
            "Cancelada": "danger",
        },
    )
    def status_badge(self, obj):
        if obj.revoked_at:
            return "Cancelada"
        if obj.proof_status != "verified":
            return "Sem prova"
        if obj.paused_at:
            return "Pausada"
        return "Ativa"

    def has_add_permission(self, request):
        # A fila é populada pela loja (cliente pede "me avise"); nunca à mão.
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ReadOnlyAlertAdmin(ModelAdmin):
    list_fullwidth = True
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StockAlertOccurrence)
class StockAlertOccurrenceAdmin(ReadOnlyAlertAdmin):
    list_display = ("event_type", "sku", "channel_ref", "status", "status_reason", "created_at")
    list_filter = ("event_type", "status", "channel_ref")
    search_fields = ("sku", "semantic_key", "source_ref")
    ordering = ("-created_at",)


@admin.register(StockAlertDelivery)
class StockAlertDeliveryAdmin(ReadOnlyAlertAdmin):
    list_display = ("status", "delivery_channel", "purpose", "occurrence", "updated_at")
    list_filter = ("status", "delivery_channel", "purpose")
    search_fields = ("ref", "occurrence__sku", "occurrence__semantic_key")
    ordering = ("-created_at",)
