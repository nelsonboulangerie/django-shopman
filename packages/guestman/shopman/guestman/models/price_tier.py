"""PriceTier — a faixa comercial do cliente, e o preço que vem com ela.

⚠️ Chamava-se `CustomerGroup`, e o nome escondia o que ela faz: ela escolhe a TABELA DE
PREÇO (`listing_ref` → `Listing` do offerman) e serve de segmento para promoção
(`Promotion.customer_segments`). "Grupo" sugeria um ajuntamento qualquer de pessoas, então
quem lia o código não tinha como saber que mexer ali mudava quanto o cliente paga.

E é `price_tier`, não `tier`: `LoyaltyAccount.tier` (gold/platinum) já é dono da palavra
solta. Com as duas chamadas "tier", "qual o tier do cliente?" passaria a ter duas
respostas — a fidelidade dele e o preço dele.

Uma por cliente, e ela precifica. Não confundir com as **tags** (`Customer.tags`), que são
muitas por cliente, livres, criadas pelo operador e não mexem em preço nenhum.
"""

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


class PriceTier(models.Model):
    """Faixa comercial: qual tabela de preço o cliente enxerga."""

    # Identification
    ref = models.SlugField(_("referência"), max_length=50, unique=True)
    name = models.CharField(_("nome"), max_length=200)
    description = models.TextField(_("descrição"), blank=True)

    # Link to pricing (Offerman Listing)
    listing_ref = models.CharField(
        _("código da listagem"),
        max_length=50,
        blank=True,
        help_text=_("Código do Listing no Offerman (convenção: Listing.ref == Channel.ref)"),
    )

    # Configuration
    is_default = models.BooleanField(
        _("padrão"),
        default=False,
        help_text=_("Faixa padrão para novos clientes"),
    )

    # Priority (for business rules)
    priority = models.IntegerField(
        _("prioridade"),
        default=0,
        help_text=_("Maior = mais prioridade"),
    )

    # Extensible metadata
    metadata = models.JSONField(
        _("metadados"), default=dict, blank=True,
        help_text=_('Metadados da faixa. Ex: {"discount_percent": 10, "min_order_q": 5000}'),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("faixa de preço")
        verbose_name_plural = _("faixas de preço")
        ordering = ["-priority", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            with transaction.atomic():
                PriceTier.objects.select_for_update().filter(
                    is_default=True
                ).exclude(pk=self.pk).update(is_default=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
