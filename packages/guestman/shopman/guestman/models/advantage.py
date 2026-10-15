"""Vantagem tipada do grupo comercial do cliente.

Um grupo (`PriceTier`) pode carregar várias vantagens, uma por TIPO. Quem pertence a mais
de um grupo não acumula o mesmo tipo: vale a melhor, e o desempate é `priority` (maior
vence). O desconto e a lista de preço NÃO moram aqui porque já têm dono canônico: o
desconto é a `Promotion` `grupo-<ref>` (domínio de preço do shop, com canal e janela) e a
lista é `PriceTier.listing_ref` (cascata do Offerman). Este modelo guarda o que o grupo
ganha ALÉM disso, tipado, para o gestor editar e para o motor resolver o melhor por tipo.

Chaves de `config` por `kind` documentadas em `docs/reference/data-schemas.md` antes do uso.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class PriceTierAdvantage(models.Model):
    """Uma vantagem tipada do grupo. No máximo uma por (grupo, tipo)."""

    class Kind(models.TextChoices):
        FREE_SHIPPING = "free_shipping", _("Frete grátis")
        EXCLUSIVE_COLLECTIONS = "exclusive_collections", _("Coleções exclusivas")
        EXCLUSIVE_NOTIFICATIONS = "exclusive_notifications", _("Notificações exclusivas")

    tier = models.ForeignKey(
        "guestman.PriceTier",
        on_delete=models.CASCADE,
        related_name="advantages",
        verbose_name=_("grupo"),
    )
    kind = models.CharField(_("tipo"), max_length=32, choices=Kind.choices)
    priority = models.IntegerField(
        _("prioridade"),
        default=0,
        help_text=_("Maior vence quando dois grupos do mesmo cliente dão a mesma vantagem."),
    )
    is_active = models.BooleanField(_("ativa"), default=True)
    config = models.JSONField(
        _("configuração"),
        default=dict,
        blank=True,
        help_text=_("Chaves por tipo, documentadas em docs/reference/data-schemas.md."),
    )

    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizada em"), auto_now=True)

    class Meta:
        verbose_name = _("vantagem do grupo")
        verbose_name_plural = _("vantagens do grupo")
        ordering = ["tier", "-priority", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["tier", "kind"],
                name="guestman_price_tier_advantage_uq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tier_id}:{self.kind}"
