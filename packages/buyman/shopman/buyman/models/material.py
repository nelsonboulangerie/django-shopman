from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.refs.fields import RefField


class Material(models.Model):
    """O cadastro de compra de um SKU — tudo que a casa compra tem um.

    Nome, unidade-base e validade padrão do que chega pela porta dos fundos:
    a farinha da massa e também o pote de geleia que vai para a prateleira.
    Ter ``Material`` é o que faz um SKU ser **comprável** (fornecedor, custo,
    conversão, mínimo e pedido penduram aqui), mesmo antes de ter fornecedor.

    Vender é outra decisão, e mora em outro pacote: quando a coisa comprada
    também se vende, o catálogo de venda tem um produto com **o mesmo SKU** —
    e o mesmo estoque, porque o ledger indexa por SKU. Este pacote não conhece o
    de venda; quem garante que os dois cadastros falem a mesma unidade é o
    orquestrador que compõe os dois.
    """

    class Unit(models.TextChoices):
        UNIT = "un", _("unidade")
        KG = "kg", _("quilograma")
        G = "g", _("grama")
        L = "l", _("litro")
        ML = "ml", _("mililitro")

    sku = RefField(
        ref_type="SKU",
        unique=True,
        verbose_name=_("SKU"),
        help_text=_("Identificador do insumo (ex.: FARINHA-NOVARA-T55)."),
    )
    name = models.CharField(max_length=200, verbose_name=_("Nome"))
    unit = models.CharField(
        max_length=8, choices=Unit.choices, default=Unit.UNIT, verbose_name=_("Unidade"),
    )
    shelf_life_days = models.IntegerField(
        null=True, blank=True, verbose_name=_("Validade padrão (dias)"),
        help_text=_("Validade padrão do insumo em dias. Vazio = não perecível."),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Ativo"))
    metadata = models.JSONField(
        default=dict, blank=True, verbose_name=_("Metadados"),
        help_text=_("Perfil opcional (nutrição, alérgenos, etc.)."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("insumo")
        verbose_name_plural = _("insumos")
        ordering = ["sku"]

    @property
    def is_perishable(self) -> bool:
        return self.shelf_life_days is not None

    def __str__(self) -> str:
        return f"{self.sku} · {self.name}"
