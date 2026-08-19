from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils.translation import gettext_lazy as _


class SupplierMaterialCost(models.Model):
    """Custo de um insumo por fornecedor, em centavos.

    Uma linha por par (fornecedor, insumo). ``is_preferred`` marca o custo
    canônico daquele insumo — o que **vai alimentar** o custeio de receita e o
    ``CostBackend`` do Offerman. Hoje esta tabela não tem leitor no repositório:
    o backend só será escrito depois da decisão de custo vivo × congelado
    (docs/decisions/adr-023-cost-live-and-frozen.md), e a unidade em que este
    ``cost_q`` é expresso está em aberto na
    docs/decisions/adr-024-material-unit-base-and-purchase.md.
    Histórico de preço fica para uma fase futura.

    Três invariantes, e cada uma tem um guarda à altura:

    - **custo é positivo** — ``CheckConstraint`` no banco (dinheiro zero ou
      negativo aqui é erro de digitação, não desconto);
    - **um preferencial por insumo** — ``UniqueConstraint`` parcial; marcar um
      novo **demove o anterior na mesma transação**, para o operador nunca ver
      ``IntegrityError`` cru na tela do inline;
    - **o preferencial aponta para par vivo** — insumo ou fornecedor inativo é
      recusado com mensagem, porque custo canônico de par aposentado é uma
      resposta errada esperando para ser lida.
    """

    supplier = models.ForeignKey(
        "buyman.Supplier", on_delete=models.CASCADE, related_name="material_costs",
        verbose_name=_("Fornecedor"),
    )
    material = models.ForeignKey(
        "buyman.Material", on_delete=models.CASCADE, related_name="supplier_costs",
        verbose_name=_("Insumo"),
    )
    cost_q = models.BigIntegerField(
        verbose_name=_("Custo (centavos)"),
        help_text=_("Custo por unidade do insumo, em centavos."),
    )
    is_preferred = models.BooleanField(
        default=False, verbose_name=_("Preferencial"),
        help_text=_("Marca o custo canônico deste insumo (alimenta o custeio)."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("custo de insumo por fornecedor")
        verbose_name_plural = _("custos de insumo por fornecedor")
        ordering = ["material", "supplier"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "material"],
                name="buyman_supplier_material_unique",
            ),
            models.UniqueConstraint(
                fields=["material"],
                condition=models.Q(is_preferred=True),
                name="buyman_one_preferred_cost_per_material",
            ),
            models.CheckConstraint(
                condition=models.Q(cost_q__gt=0),
                name="buyman_cost_positive",
                violation_error_message=_("O custo precisa ser maior que zero."),
            ),
        ]

    def clean(self):
        super().clean()
        self._refuse_preferred_of_retired_pair()

    def save(self, *args, **kwargs):
        """Promove o preferencial de forma atômica: demove o anterior e assume.

        A unicidade continua sendo do banco; o gesto de troca é que passa a ser
        nosso, e não um ``IntegrityError`` na cara de quem marcou a caixinha.
        """
        self._refuse_preferred_of_retired_pair()
        with transaction.atomic():
            if self.is_preferred and self.material_id:
                (
                    type(self)
                    .objects.filter(material_id=self.material_id, is_preferred=True)
                    .exclude(pk=self.pk)
                    .update(is_preferred=False)
                )
            try:
                super().save(*args, **kwargs)
            except IntegrityError as exc:
                if "buyman_one_preferred_cost_per_material" not in str(exc):
                    raise  # custo não positivo, par duplicado: cada um com seu erro
                # Duas promoções no mesmo instante: a constraint decide, e a
                # mensagem continua sendo a nossa.
                raise ValidationError({
                    "is_preferred": _(
                        "Outro custo deste insumo foi marcado como preferencial ao "
                        "mesmo tempo. Recarregue a página e tente de novo."
                    )
                }) from exc

    def _refuse_preferred_of_retired_pair(self) -> None:
        if not self.is_preferred:
            return
        if self.material_id and not self.material.is_active:
            raise ValidationError({
                "is_preferred": _(
                    "O insumo '%(sku)s' está inativo — um insumo aposentado não pode "
                    "ter custo canônico. Reative o insumo ou marque outro custo."
                ) % {"sku": self.material.sku}
            })
        if self.supplier_id and not self.supplier.is_active:
            raise ValidationError({
                "is_preferred": _(
                    "O fornecedor '%(ref)s' está inativo — o custo canônico não pode "
                    "apontar para um fornecedor aposentado. Reative o fornecedor ou "
                    "promova outro custo."
                ) % {"ref": self.supplier.ref}
            })

    def __str__(self) -> str:
        return f"{self.material_id}@{self.supplier_id}: {self.cost_q}"
