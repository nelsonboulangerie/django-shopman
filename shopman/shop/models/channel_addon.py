"""Complementos de um produto num canal externo (hoje, o iFood).

O Offerman só conhece produto vendável e não tem complemento; o Core não ganha
campo para isso (CLAUDE.md). O complemento é um anúncio do CANAL: o grupo
("Escolha o molho") pendura num SKU da casa, e cada opção tem nome, preço, foto e
estado próprios. A identidade remota (UUID no iFood) é derivada de
``(merchant, sku, ref)`` em ``shop.adapters.catalog_projection_ifood``, como a do
item, então não mora aqui.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from shopman.utils.refs import RefField


class ChannelAddonGroup(models.Model):
    """Grupo de complementos de um SKU num canal."""

    channel = models.ForeignKey(
        "shop.Channel",
        on_delete=models.CASCADE,
        related_name="addon_groups",
        verbose_name="canal",
    )
    sku = RefField(ref_type="SKU", verbose_name="SKU do produto", max_length=100, db_index=True)
    ref = models.SlugField("referência", max_length=64)
    name = models.CharField("nome", max_length=128)
    min_choices = models.PositiveSmallIntegerField("mínimo de escolhas", default=0)
    max_choices = models.PositiveSmallIntegerField(
        "máximo de escolhas", default=1, validators=[MinValueValidator(1)]
    )
    index = models.PositiveSmallIntegerField("posição", default=0)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "shop"
        verbose_name = "grupo de complementos"
        verbose_name_plural = "grupos de complementos"
        ordering = ("channel", "sku", "index", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("channel", "sku", "ref"), name="shop_addon_group_unique_ref"
            ),
            models.CheckConstraint(
                condition=models.Q(max_choices__gte=models.F("min_choices")),
                name="shop_addon_group_min_le_max",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} · {self.name}"


class ChannelAddon(models.Model):
    """Uma opção dentro de um grupo de complementos."""

    group = models.ForeignKey(
        ChannelAddonGroup,
        on_delete=models.CASCADE,
        related_name="addons",
        verbose_name="grupo",
    )
    ref = models.SlugField("referência", max_length=64)
    name = models.CharField("nome", max_length=128)
    price_q = models.PositiveIntegerField("preço (centavos)", default=0)
    image_url = models.CharField("foto (URL)", max_length=500, blank=True, default="")
    index = models.PositiveSmallIntegerField("posição", default=0)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "shop"
        verbose_name = "complemento"
        verbose_name_plural = "complementos"
        ordering = ("group", "index", "pk")
        constraints = [
            models.UniqueConstraint(fields=("group", "ref"), name="shop_addon_unique_ref"),
        ]

    def __str__(self) -> str:
        return f"{self.group.name} · {self.name}"
