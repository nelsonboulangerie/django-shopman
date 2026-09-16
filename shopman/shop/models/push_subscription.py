"""Assinaturas Web Push dos aparelhos autenticados do backstage."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class PushSurface(models.TextChoices):
    HUB = "hub", "Central"
    ORDERS = "orders", "Pedidos"
    POS = "pos", "PDV"
    PRODUCTION = "production", "Produção"
    MARKETING = "marketing", "Marketing"
    PURCHASE = "purchase", "Compras"
    BI = "bi", "BI"


PUSH_CATEGORIES = frozenset({
    "campaign",
    "production",
    "order",
    "purchase",
    "report",
    "sign_in",
    "system",
})

PUSH_SURFACE_CATEGORIES = {
    PushSurface.HUB: PUSH_CATEGORIES,
    PushSurface.ORDERS: frozenset({"order"}),
    PushSurface.POS: frozenset({"order", "system"}),
    PushSurface.PRODUCTION: frozenset({"production", "system"}),
    PushSurface.MARKETING: frozenset({"campaign"}),
    PushSurface.PURCHASE: frozenset({"purchase"}),
    PushSurface.BI: frozenset({"report"}),
}


class PushSubscription(models.Model):
    """Um endpoint do Push API pertencente a uma pessoa e a uma surface."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
        verbose_name="usuário",
    )
    endpoint = models.TextField("endereço de entrega", unique=True)
    p256dh = models.TextField("chave pública do aparelho")
    auth = models.TextField("segredo de autenticação do aparelho")
    surface_ref = models.CharField(
        "surface",
        max_length=32,
        choices=PushSurface.choices,
    )
    device_label = models.CharField("aparelho", max_length=120)
    categories = models.JSONField("categorias", default=list)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    last_success_at = models.DateTimeField("último sucesso em", null=True, blank=True)
    failures = models.PositiveSmallIntegerField("falhas consecutivas", default=0)
    disabled_at = models.DateTimeField("removida em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "assinatura Web Push"
        verbose_name_plural = "assinaturas Web Push"
        indexes = [
            models.Index(fields=["user", "disabled_at"]),
            models.Index(fields=["surface_ref", "disabled_at"]),
        ]

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.categories, list):
            raise ValidationError({"categories": "Categorias precisam ser uma lista."})
        normalized = [str(category).strip() for category in self.categories]
        if any(not category or category not in PUSH_CATEGORIES for category in normalized):
            raise ValidationError({"categories": "A lista contém uma categoria inválida."})
        if len(normalized) != len(set(normalized)):
            raise ValidationError({"categories": "Não repita categorias no mesmo aparelho."})
        allowed = PUSH_SURFACE_CATEGORIES.get(self.surface_ref, frozenset())
        if any(category not in allowed for category in normalized):
            raise ValidationError({"categories": "A surface não aceita uma das categorias escolhidas."})

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.device_label} · {self.get_surface_ref_display()} · usuário {self.user_id}"


__all__ = [
    "PUSH_CATEGORIES",
    "PUSH_SURFACE_CATEGORIES",
    "PushSubscription",
    "PushSurface",
]
