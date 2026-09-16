"""Admin somente leitura para aparelhos inscritos em Web Push."""

import hashlib

from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin

from shopman.shop.models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(ModelAdmin):
    list_display = (
        "device_label",
        "user",
        "surface_ref",
        "created_at",
        "last_success_at",
        "failures",
        "disabled_at",
    )
    list_filter = ("surface_ref", "disabled_at", "created_at")
    search_fields = ("device_label", "user__username", "user__email")
    ordering = ("-created_at", "-pk")
    actions = ("remove_subscriptions",)
    readonly_fields = (
        "user",
        "endpoint_fingerprint",
        "surface_ref",
        "device_label",
        "categories",
        "created_at",
        "last_success_at",
        "failures",
        "disabled_at",
    )
    exclude = ("endpoint", "p256dh", "auth")

    @admin.display(description="endpoint (fingerprint)")
    def endpoint_fingerprint(self, obj):
        return hashlib.sha256(obj.endpoint.encode()).hexdigest()[:16]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Remover assinaturas selecionadas", permissions=["view"])
    def remove_subscriptions(self, request, queryset):
        changed = queryset.filter(disabled_at__isnull=True).update(disabled_at=timezone.now())
        self.message_user(request, f"{changed} assinatura(s) removida(s).")
