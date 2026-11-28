from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils.translation import gettext_lazy as _

# O dinheiro de insumo miúdo se lê E SE GUARDA por quilo (ou litro): "R$ 91,67
# / kg", nunca "R$ 0,09 / g". Centavo inteiro por grama arredonda R$ 0,0917 para
# R$ 0,09 (9% de erro numa reposição; beta 05/11, CMP-07). Fator = quantas
# unidades-base cabem na unidade de leitura.
READING_UNIT_FOR_BASE: dict[str, tuple[Decimal, str]] = {
    "g": (Decimal(1000), "kg"),
    "mg": (Decimal(1_000_000), "kg"),
    "ml": (Decimal(1000), "l"),
}


def reading_unit(base_unit: str | None) -> tuple[Decimal, str]:
    """``(fator, rótulo)`` da unidade em que o dinheiro de ``base_unit`` se lê.

    Grama e miligrama viram quilo; mililitro vira litro; o resto fica na própria
    base, com fator 1.
    """
    unit = base_unit or ""
    return READING_UNIT_FOR_BASE.get(unit, (Decimal(1), unit))


def priced_unit_factor(material, conversion) -> Decimal:
    """Quantas unidades-base o ``cost_q`` paga.

    Com conversão, a embalagem da nota ("saco 25 kg" = 25 000 g). Sem conversão,
    a unidade de leitura da base: o quilo de um insumo em grama, o litro de um em
    mililitro, a própria unidade do resto. É o divisor único de todo custo de
    insumo: ``cost_q / priced_unit_factor`` é o custo por unidade-base.
    """
    if conversion is not None:
        return Decimal(conversion.to_base_factor)
    return reading_unit(getattr(material, "unit", ""))[0]


def priced_unit_label(material, conversion) -> str:
    """O nome da unidade que o ``cost_q`` paga: "saco 25 kg", "kg", "l", "un"."""
    if conversion is not None:
        return conversion.label
    return reading_unit(getattr(material, "unit", ""))[1]

class SupplierMaterialCost(models.Model):
    """Custo de um insumo por fornecedor, em centavos **da unidade de preço**.

    Uma linha por par (fornecedor, insumo). ``is_preferred`` marca o custo
    canônico daquele insumo — o que alimenta o custeio de receita: o custo vivo
    do orquestrador (``RecipeCostBackend``, ADR-023) lê daqui pelo
    ``CostBackend`` do Offerman.
    Histórico de preço fica para uma fase futura.

    **O operador nunca divide** (ADR-024, R2). Ele copia da nota os três números
    impressos nela — "1 saco", "R$ 180,00", e o rótulo do saco — e quem divide é
    a máquina: ``conversion`` aponta para a linha de :class:`MaterialConversion`
    que diz quanto aquele saco vale na unidade-base, e
    :attr:`cost_per_base_unit` deriva o resto em ``Decimal``. Sem conversão, o
    preço é da **unidade de leitura** da base (:func:`reading_unit`): por quilo
    quando a base é grama, por litro quando é mililitro, pela própria unidade no
    resto. Centavo inteiro por grama não existe (R$ 110 por 1200 g é R$ 91,67 o
    quilo, e não R$ 0,09 o grama; beta 05/11, CMP-07).

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
            "Custo de UMA unidade de compra (a embalagem da conversão) em "
            "centavos: o número da nota. Sem conversão, o custo do kg (insumo em "
            "g) ou do litro (insumo em ml), ou da própria unidade."
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
        """Em que unidade se CONTA o que se compra: a embalagem, ou a própria base."""
        if self.conversion_id:
            return self.conversion.label
        return getattr(self.material, "unit", "") if self.material_id else ""

    @property
    def base_factor(self) -> Decimal:
        """Quanto uma unidade de compra vale na unidade-base. Sem conversão, 1.

        É fator de QUANTIDADE. O de dinheiro é :attr:`priced_unit_factor`.
        """
        if self.conversion_id:
            return Decimal(self.conversion.to_base_factor)
        return Decimal(1)

    @property
    def priced_unit_factor(self) -> Decimal:
        """Quantas unidades-base o ``cost_q`` paga (ver :func:`priced_unit_factor`)."""
        return priced_unit_factor(
            self.material if self.material_id else None,
            self.conversion if self.conversion_id else None,
        )

    @property
    def priced_unit_label(self) -> str:
        """A unidade do ``cost_q`` na tela: "saco 25 kg", "kg", "l", "un"."""
        return priced_unit_label(
            self.material if self.material_id else None,
            self.conversion if self.conversion_id else None,
        )

    @property
    def cost_per_base_unit(self) -> Decimal:
        """Centavos por unidade-base, em ``Decimal``, **sem arredondar**."""
        return Decimal(self.cost_q) / self.priced_unit_factor

    def cost_for_base_qty_q(self, base_qty) -> int:
        """Centavos de ``base_qty`` unidades-base, arredondado uma vez só, no fim.

        300 g a R$ 91,67/kg = R$ 27,50; com o custo por grama arredondado antes
        da conta, dava R$ 27,00.
        """
        value = Decimal(self.cost_q) * Decimal(str(base_qty)) / self.priced_unit_factor
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def cost_per_base_unit_q(self) -> int:
        """Centavos por unidade-base, inteiro. É aqui, e só aqui, que arredonda.

        ⚠️ Com base em GRAMA (ADR-024, emenda de 24/09/2026) este inteiro é quase
        sempre zero: farinha a R$ 4/kg vale 0,4 centavo/g. Conta usa
        :attr:`cost_per_base_unit`; tela de insumo pesado usa
        :meth:`cost_per_display_unit_q`, que fala em R$/kg.
        """
        return int(self.cost_per_base_unit.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def cost_per_display_unit_q(self) -> tuple[int, str]:
        """``(centavos, unidade)`` na unidade em que o dinheiro se lê.

        Grama e miligrama viram quilo; mililitro vira litro; o resto fica na
        própria base. Sem conversão, é o próprio ``cost_q``.
        """
        unit = getattr(self.material, "unit", "") if self.material_id else ""
        scale, shown = reading_unit(unit)
        value = (self.cost_per_base_unit * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(value), shown

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
                    "O insumo '%(sku)s' está inativo, e um insumo aposentado não pode "
                    "ter custo canônico. Reative o insumo ou marque outro custo."
                ) % {"sku": self.material.sku}
            })
        if self.supplier_id and not self.supplier.is_active:
            raise ValidationError({
                "is_preferred": _(
                    "O fornecedor '%(ref)s' está inativo, e o custo canônico não pode "
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
                    "'%(supplier)s': o saco de cada fornecedor pode ter um peso."
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
