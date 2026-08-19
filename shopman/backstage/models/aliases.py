"""De-paras do B.I. — mapeamento é DADO, não código (BI-DATA-FOUNDATION-PLAN, P1).

Três tabelas dizem como o que veio de fora se traduz no vocabulário da casa:

- ``ProductAlias``: produto de uma fonte (SKU e nome como o export os escreve)
  → ``offerman.Product``. Por fonte, porque SKU externo colide entre sistemas.
- ``CategoryAlias``: categoria crua → o que ela diz sobre a cesta
  (``reading``) e, quando faz sentido, a coleção do catálogo. Independente de
  fonte: "Pães Finos" é viennoiserie venha de onde vier.
- ``PaymentMethodAlias``: forma de pagamento crua → chave canônica da casa
  (``cash``, ``pix``, ``credit``…). Também independente de fonte.

Duas delas (categoria e pagamento) são **vocabulários por trecho, em ordem**:
``pattern`` é minúsculo, casa por "contém", e a primeira linha que casa vence —
por isso o específico tem ``position`` menor que o genérico ("pães finos"
antes de "pão", senão 38 mil linhas de viennoiserie cairiam em "leva"). Era
exatamente assim que as regras viviam em código; agora vivem em linha editável,
com quem confirmou e quando.

**Sugestão é máquina, confirmação é gente.** Todo alias nasce ``proposed``
(escrito à mão no Admin ou sugerido pelo ``suggest_aliases``, com ``score``);
a leitura só usa ``confirmed``. Nunca se mescla em silêncio: uma sugestão
errada que ninguém viu não muda número nenhum.

⚠️ As regras padrão desta loja NÃO moram em migração: moram no seed e no
``setup_bi_reference`` (referência é dado do tenant; ``migrate`` cria tabela
vazia). Sem elas, categoria sem etiqueta de SKU sai "sem etiqueta" e forma de
pagamento desconhecida sai como texto cru — declarado, nunca inventado.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .consumption import Reading


class AliasStatus(models.TextChoices):
    PROPOSED = "proposed", "proposto"
    CONFIRMED = "confirmed", "confirmado"
    REJECTED = "rejected", "rejeitado"


class AliasQuerySet(models.QuerySet):
    def confirmed(self):
        return self.filter(status=AliasStatus.CONFIRMED)


class Alias(models.Model):
    """O que toda tabela de de-para carrega: estado, sugestão, assinatura."""

    status = models.CharField(
        "estado", max_length=10, choices=AliasStatus.choices, default=AliasStatus.PROPOSED,
    )
    score = models.PositiveSmallIntegerField(
        "confiança da sugestão", null=True, blank=True,
        help_text="0–100 quando a máquina sugeriu; vazio quando alguém escreveu à mão.",
    )
    note = models.CharField("observação", max_length=200, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="confirmado por",
    )
    confirmed_at = models.DateTimeField("confirmado em", null=True, blank=True)

    objects = AliasQuerySet.as_manager()

    class Meta:
        abstract = True

    def mark_confirmed(self, user) -> None:
        """A assinatura da curadoria: quem e quando. Não salva."""
        self.status = AliasStatus.CONFIRMED
        self.confirmed_by = user
        self.confirmed_at = timezone.now()

    def mark_rejected(self) -> None:
        self.status = AliasStatus.REJECTED
        self.confirmed_by = None
        self.confirmed_at = None


class ProductAlias(Alias):
    source = models.CharField("origem", max_length=16, db_index=True)
    external_sku = models.CharField(
        "SKU na origem", max_length=64, blank=True, db_index=True,
        help_text="Vazio quando a linha da origem não traz SKU: aí o de-para é pelo nome.",
    )
    external_name = models.CharField("nome na origem", max_length=200, blank=True)
    # PROTECT: apagar um produto com de-para confirmado apagaria a tradução de
    # anos de histórico em silêncio. Produto extinto fica com FK vazia — o
    # alias segue existindo, e a leitura usa o nome da origem.
    product = models.ForeignKey(
        "offerman.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_aliases",
        verbose_name="produto do catálogo",
        help_text="Vazio = produto extinto ou ainda sem correspondência.",
    )

    class Meta:
        verbose_name = "de-para de produto"
        verbose_name_plural = "de-paras de produto"
        ordering = ["source", "external_sku", "external_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_sku"],
                condition=~models.Q(external_sku=""),
                name="backstage_productalias_source_sku",
            ),
            models.UniqueConstraint(
                fields=["source", "external_name"],
                condition=models.Q(external_sku=""),
                name="backstage_productalias_source_name",
            ),
            models.CheckConstraint(
                condition=~models.Q(external_sku="", external_name=""),
                name="backstage_productalias_has_key",
            ),
        ]

    def __str__(self):
        key = self.external_sku or self.external_name
        return f"{self.source}:{key} → {self.product.sku if self.product_id else '—'}"

    def clean(self):
        if not self.external_sku and not self.external_name:
            raise ValidationError("Informe o SKU ou o nome na origem.")


class CategoryAlias(Alias):
    pattern = models.CharField(
        "trecho da categoria", max_length=100, unique=True,
        help_text="Minúsculo; casa por 'contém'. A primeira linha que casa (menor posição) vence.",
    )
    position = models.PositiveSmallIntegerField(
        "posição", default=0,
        help_text="O específico vem antes do genérico: 'pães finos' antes de 'pão'.",
    )
    reading = models.CharField(
        "o que diz sobre a cesta", max_length=16, choices=Reading.choices, blank=True,
        help_text="Reserva para linha sem etiqueta de SKU. Vazio = a categoria não decide.",
    )
    collection = models.ForeignKey(
        "offerman.Collection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_category_aliases",
        verbose_name="coleção do catálogo",
        help_text="A categoria canônica, quando existe. Opcional.",
    )

    class Meta:
        verbose_name = "de-para de categoria"
        verbose_name_plural = "de-paras de categoria"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.pattern} → {self.reading or '—'}"

    def clean(self):
        self.pattern = (self.pattern or "").strip().lower()
        if not self.pattern:
            raise ValidationError({"pattern": "O trecho não pode ficar vazio."})
        if self.status == AliasStatus.CONFIRMED and not (self.reading or self.collection_id):
            raise ValidationError("Para confirmar, diga o que a categoria significa: leitura ou coleção.")


class PaymentMethodAlias(Alias):
    pattern = models.CharField(
        "trecho da forma de pagamento", max_length=100, unique=True,
        help_text="Minúsculo; casa por 'contém'. A primeira linha que casa (menor posição) vence.",
    )
    position = models.PositiveSmallIntegerField(
        "posição", default=0,
        help_text="O específico vem antes do genérico: 'vale refeição' antes de 'vale'.",
    )
    method_key = models.CharField(
        "forma canônica", max_length=32, blank=True,
        help_text="Chave da casa: cash, pix, credit, debit, voucher, ifood, card, external.",
    )

    class Meta:
        verbose_name = "de-para de forma de pagamento"
        verbose_name_plural = "de-paras de forma de pagamento"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.pattern} → {self.method_key or '—'}"

    def clean(self):
        self.pattern = (self.pattern or "").strip().lower()
        if not self.pattern:
            raise ValidationError({"pattern": "O trecho não pode ficar vazio."})
        if self.status == AliasStatus.CONFIRMED and not self.method_key:
            raise ValidationError({"method_key": "Para confirmar, informe a forma canônica."})
