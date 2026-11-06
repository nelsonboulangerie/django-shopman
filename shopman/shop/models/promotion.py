"""Promoção e cupom — regra de preço do orquestrador, escopada por canal.

Estes dois models moram aqui, e não na superfície da loja nem no offerman, porque
promoção é **cross-domain por natureza**: `skus`/`collections` são offerman,
`customer_segments`/`birthday_only` são guestman, `fulfillment_types` é orderman. Levar
para um pacote kernel importaria três vocabulários alheios e o teste de fronteira
barraria na hora; a ADR-005 §3 diz que o orquestrador é o único lugar onde domínios se
encontram.

A §4.1 da constituição fica satisfeita sem contradição: offerman é dono do preço de
tabela e **declara o buraco** para preço contextual (`OFFERMAN["PRICING_BACKEND"]`), que
este deployment preenche. A deriva nunca foi "não está no offerman" — foi "está numa
superfície", de onde o orquestrador precisava de um adapter para alcançar a própria
regra de preço. Ver ADR-019.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Promotion(models.Model):
    """Promoção automática — aplica desconto a itens que atendem os critérios."""

    PERCENT = "percent"
    FIXED = "fixed"
    #: Entrega grátis é **renúncia da taxa por quem a calcula**, nunca linha de
    #: desconto. A distinção não é estilística: `_is_non_merchandise_line` blinda a
    #: linha `__DELIVERY_FEE__` contra desconto em dez pontos do `modifiers.py`, e é
    #: essa invariante que mantém a taxa com UM dono. Ver `_effective_fee_q`.
    FREE_DELIVERY = "free_delivery"
    TYPE_CHOICES = [
        (PERCENT, "Percentual"),
        (FIXED, "Valor fixo"),
        (FREE_DELIVERY, "Entrega grátis"),
    ]

    #: Identificador canônico exposto a operação, log e integração (constituição
    #: §3.1). É o que a `Campaign` aponta em `promotion_ref` (ADR-020): apontar para
    #: `Coupon.code` seria mais barato e estaria errado — cupom é o ATIVADOR de uma
    #: promoção, não a promoção. Relâmpago automática não tem código nenhum, e
    #: amarrar a campanha ao cupom obrigaria a inventar um só para poder anunciar.
    ref = models.SlugField(_("código"), max_length=64, unique=True, db_index=True)
    name = models.CharField("nome", max_length=200)
    type = models.CharField("tipo", max_length=16, choices=TYPE_CHOICES)
    #: Para `free_delivery` a coluna ganha semântica em vez de virar campo morto:
    #: `0` é renúncia total, `> 0` é o TETO da renúncia em centavos — "entrega grátis
    #: até R$ 8,00". Cobre a padaria que quer subsidiar frete curto sem bancar o longo,
    #: reusando a coluna que já existia.
    value = models.IntegerField(
        "valor",
        help_text=(
            "Percentual: de 1 a 100. Valor fixo: o desconto em centavos (1500 = R$ 15,00). "
            "Entrega grátis: o teto do frete em centavos, ou 0 para o frete inteiro."
        ),
    )
    valid_from = models.DateTimeField("válido de")
    valid_until = models.DateTimeField("válido até")
    skus = models.JSONField(
        "SKUs",
        default=list,
        blank=True,
        help_text='SKUs afetados (vazio = todos). Ex: ["PAO-FRANCES", "CROISSANT"]',
    )
    collections = models.JSONField(
        "coleções",
        default=list,
        blank=True,
        help_text='Coleções afetadas (vazio = todas). Ex: ["paes-artesanais", "confeitaria"]',
    )
    min_order_q = models.IntegerField(
        "pedido mínimo (centavos)",
        default=0,
        help_text="Valor mínimo do pedido em centavos (0 = sem mínimo)",
    )
    fulfillment_types = models.JSONField(
        "tipos de entrega",
        default=list,
        blank=True,
        help_text='Tipos de entrega (vazio = todos). Ex: ["delivery", "pickup"]',
    )
    customer_segments = models.JSONField(
        "segmentos de cliente",
        default=list,
        blank=True,
        help_text='Perfis de compra do cliente que recebem a promoção (vazio = todos). Ex: ["champions", "loyal"]',
    )
    birthday_only = models.BooleanField(
        "apenas aniversariantes",
        default=False,
        help_text="Se marcado, desconto aplicável somente no dia do aniversário do cliente.",
    )
    #: Canais onde a promoção vale. **Vazio = todos** — cópia exata da semântica de
    #: `RuleConfig.channels`, que é o precedente. Preserva o comportamento de toda
    #: promoção existente (nenhuma migração de dados) e permite a relâmpago valer só
    #: na web. Com a ADR-018 isto alcança canal `display`, então a promoção fica
    #: descobrível no Google, na Meta e no menuboard — impossível antes, porque o
    #: feed só conhecia preço de tabela.
    #:
    #: O nome é `channels`, nunca `platforms`: "platform" é a palavra que a ADR-018
    #: eliminou.
    channels = models.ManyToManyField(
        "shop.Channel", blank=True, verbose_name=_("canais"),
        help_text=_("Vazio = vale em todos os canais."),
    )
    is_active = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "promoção"
        verbose_name_plural = "promoções"
        ordering = ["-valid_from"]

    def __str__(self):
        return self.name

    def clean(self):
        """Barrar configuração que não quer dizer nada.

        Entrega grátis restrita a `pickup` é mentira configurável: não existe taxa de
        entrega em retirada, então a promoção nunca faria efeito e ninguém saberia por
        quê. Validar na borda é mais barato que investigar depois.
        """
        super().clean()
        errors: dict[str, str] = {}
        value = self.value
        if value is not None:
            if self.type == self.PERCENT and not 1 <= value <= 100:
                errors["value"] = "Percentual entre 1 e 100."
            elif self.type == self.FIXED and value < 1:
                errors["value"] = "Informe um desconto maior que zero."
            elif self.type == self.FREE_DELIVERY and value < 0:
                errors["value"] = "O teto do frete não pode ser negativo."
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            errors["valid_until"] = "O término precisa ser posterior ao início."
        if errors:
            raise ValidationError(errors)
        if self.type != self.FREE_DELIVERY:
            return
        types = [str(t).strip() for t in (self.fulfillment_types or []) if str(t).strip()]
        if types and "delivery" not in types:
            raise ValidationError({
                "fulfillment_types": (
                    "Entrega grátis precisa valer para entrega. Deixe vazio (todos) ou "
                    "inclua 'delivery'."
                )
            })

    def applies_to_channel(self, channel_ref: str) -> bool:
        """A promoção vale neste canal? Vazio = todos (mesma régua do RuleConfig)."""
        # ``.all()`` usa o prefetch de ``channels`` quando houver (o cardápio
        # carrega todas as promoções com ele); ``values_list`` o ignorava e fazia
        # uma consulta por promoção.
        refs = [channel.ref for channel in self.channels.all()]
        return not refs or channel_ref in refs


#: Mesma régua do cadastro de cupom do Marketing (``backstage/api/marketing.py``).
COUPON_CODE_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9_-]*")
COUPON_CODE_ERROR = "Use até 50 letras sem acento, números, hífen ou sublinhado, sem espaços."


def normalize_coupon_code(code: str | None) -> str:
    """O código como a loja o procura: sem espaço nas pontas e em maiúsculas."""
    return (code or "").strip().upper()


class Coupon(models.Model):
    """Cupom — código que ativa uma promoção.

    O código é guardado em maiúsculas: a loja passa o que o cliente digitou para
    maiúsculas antes de procurar (``validate_and_apply_coupon``), então um cupom
    gravado como "natal10" nunca seria encontrado.
    """

    code = models.CharField(
        "código",
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Letras sem acento, números, hífen ou sublinhado. Fica em maiúsculas.",
    )
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        related_name="coupons",
        verbose_name="promoção",
    )
    max_uses = models.PositiveIntegerField(
        "usos máximos",
        default=0,
        help_text="Quantas vezes o cupom pode ser usado. Deixe 0 para não ter limite.",
    )
    uses_count = models.PositiveIntegerField("usos realizados", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "cupom"
        verbose_name_plural = "cupons"

    def __str__(self):
        return self.code

    def clean(self):
        super().clean()
        self.code = normalize_coupon_code(self.code)
        if not COUPON_CODE_PATTERN.fullmatch(self.code):
            raise ValidationError({"code": COUPON_CODE_ERROR})

    def save(self, *args, **kwargs):
        self.code = normalize_coupon_code(self.code)
        super().save(*args, **kwargs)

    @property
    def is_available(self) -> bool:
        return self.is_active and (self.max_uses == 0 or self.uses_count < self.max_uses)
