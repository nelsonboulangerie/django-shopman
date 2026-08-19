from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils.translation import gettext_lazy as _


class SupplierMaterialCost(models.Model):
    """Custo de um insumo por fornecedor, em centavos **da unidade de compra**.

    Uma linha por par (fornecedor, insumo). ``is_preferred`` marca o custo
    canônico daquele insumo — o que **vai alimentar** o custeio de receita e o
    ``CostBackend`` do Offerman. Hoje esta tabela não tem leitor no repositório:
    o backend só será escrito depois da decisão de custo vivo × congelado
    (docs/decisions/adr-023-cost-live-and-frozen.md).
    Histórico de preço fica para uma fase futura.

    **O operador nunca divide** (ADR-024, R2). Ele copia da nota os três números
    impressos nela — "1 saco", "R$ 180,00", e o rótulo do saco — e quem divide é
    a máquina: ``conversion`` aponta para a linha de :class:`MaterialConversion`
    que diz quanto aquele saco vale na unidade-base, e
    :attr:`cost_per_base_unit` deriva o resto em ``Decimal``. Sem conversão, a
    unidade de compra **é** a base, e o fator é 1.

    O custo por unidade-base é **derivado, nunca gravado**: corrigir o fator do
    saco (o moinho passou de 25 kg para 20) reprecifica tudo sozinho, sem
    migração de dado de dinheiro. E o arredondamento para centavo inteiro
    acontece só na ponta em que o número vai para a tela ou para o custeio
    (:attr:`cost_per_base_unit_q`), nunca no meio da conta.

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
    conversion = models.ForeignKey(
        "buyman.MaterialConversion", on_delete=models.PROTECT, related_name="costs",
        null=True, blank=True, verbose_name=_("Unidade de compra"),
        help_text=_(
            "A conversão declarada que descreve como este insumo foi comprado "
            "('saco 25 kg', 'cartela'). Vazio = comprado na própria unidade-base."
        ),
    )
    cost_q = models.BigIntegerField(
        verbose_name=_("Custo (centavos)"),
        help_text=_(
            "Custo de UMA unidade de compra, em centavos — o número da nota. "
            "O custo por unidade-base é derivado pela conversão."
        ),
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

    @property
    def purchase_unit_label(self) -> str:
        """Como o operador chama a unidade que ele digitou o preço."""
        if self.conversion_id:
            return self.conversion.label
        return getattr(self.material, "unit", "") if self.material_id else ""

    @property
    def base_factor(self) -> Decimal:
        """Quanto uma unidade de compra vale na unidade-base. Sem conversão, 1."""
        if self.conversion_id:
            return Decimal(self.conversion.to_base_factor)
        return Decimal(1)

    @property
    def cost_per_base_unit(self) -> Decimal:
        """Centavos por unidade-base, em ``Decimal`` — **sem arredondar**."""
        return Decimal(self.cost_q) / self.base_factor

    @property
    def cost_per_base_unit_q(self) -> int:
        """Centavos por unidade-base, inteiro. É aqui, e só aqui, que arredonda."""
        return int(self.cost_per_base_unit.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def is_approximate(self) -> bool:
        """``True`` quando o custo por base atravessou uma equivalência aproximada.

        Compra-se ovo por cartela e consome-se ovo por peso: a ponte entre os
        dois lados é necessariamente aproximada, e o número que sai dela é
        **estimado**. A regra R3 da ADR-024 não proíbe a ponte — proíbe que ela
        vire um número liso, do qual ninguém mais consegue perguntar se foi
        pesado ou convertido.
        """
        return bool(self.conversion_id) and self.conversion.is_approximate

    def clean(self):
        super().clean()
        self._refuse_preferred_of_retired_pair()
        self._refuse_incoherent_conversion()

    def save(self, *args, **kwargs):
        """Promove o preferencial de forma atômica: demove o anterior e assume.

        A unicidade continua sendo do banco; o gesto de troca é que passa a ser
        nosso, e não um ``IntegrityError`` na cara de quem marcou a caixinha.
        """
        self._refuse_preferred_of_retired_pair()
        self._refuse_incoherent_conversion()
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

    def _refuse_incoherent_conversion(self) -> None:
        """A conversão apontada tem de ser deste insumo, deste fornecedor, e viva.

        Sem estes três, o ``cost_q`` estaria dividido por um fator que não é o
        desta compra — e o erro seria caro e silencioso (fator 25× errado é
        custo 25× errado). Regra R4: recusa com a mensagem dizendo o que fazer,
        nunca "assume 1:1".
        """
        if not self.conversion_id:
            return
        conversion = self.conversion
        if self.material_id and conversion.material_id != self.material_id:
            raise ValidationError({
                "conversion": _(
                    "A conversão '%(label)s' é do insumo '%(other)s'. Cadastre a "
                    "unidade de compra no próprio insumo '%(sku)s'."
                ) % {
                    "label": conversion.label,
                    "other": conversion.material.sku,
                    "sku": self.material.sku,
                }
            })
        if (
            conversion.supplier_id
            and self.supplier_id
            and conversion.supplier_id != self.supplier_id
        ):
            raise ValidationError({
                "conversion": _(
                    "A conversão '%(label)s' vale só para o fornecedor "
                    "'%(other)s'. Cadastre a mesma unidade de compra para "
                    "'%(supplier)s' — o saco de cada fornecedor pode ter um peso."
                ) % {
                    "label": conversion.label,
                    "other": conversion.supplier.name or conversion.supplier.ref,
                    "supplier": self.supplier.name or self.supplier.ref,
                }
            })
        if not conversion.is_active:
            raise ValidationError({
                "conversion": _(
                    "A conversão '%(label)s' está inativa. Reative-a ou escolha a "
                    "unidade de compra que este fornecedor usa hoje."
                ) % {"label": conversion.label}
            })

    def __str__(self) -> str:
        return f"{self.material_id}@{self.supplier_id}: {self.cost_q}"
