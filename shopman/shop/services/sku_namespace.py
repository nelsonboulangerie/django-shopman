"""Um SKU é uma coisa só — e o porteiro da coerência dele mora aqui.

``offerman.Product.sku`` e ``buyman.Material.sku`` são únicos **cada um na sua
tabela**, e o mesmo SKU pode existir nas duas — é assim que se diz que uma
coisa comprada também se vende (o pote de geleia, o queijo, o chá em lata):

- o ``Material`` é o **cadastro de compra** do SKU (fornecedor, custo,
  conversão, mínimo, pedido de compra);
- o ``Product`` é o **cadastro de venda** do mesmo SKU (preço, listagens, foto).

O estoque do Stockman é indexado por SKU, então os dois cadastros contam **o
mesmo estoque**: o pote que entra pela nota é o pote que sai pelo PDV. Isso só
fecha se os dois lados falarem **a mesma unidade** — "3" num lado não pode ser
3 kg e no outro 3 potes. A regra do porteiro é, então, a de coerência:

    mesmo SKU nos dois lados → mesma unidade (normalizada por
    ``shopman.utils.units``: ``lt`` e ``l`` são a mesma unidade).

Dois SKUs que são coisas diferentes (a água do filtro e a garrafa do balcão)
têm SKUs diferentes, e esta regra não os alcança: ela não adivinha identidade,
só recusa a incoerência de quem já disse que é a mesma coisa.

Cores nunca se importam (ADR-001): nem o Buyman conhece o Offerman, nem o
contrário. A coerência é pergunta do **orquestrador**, que já compõe os dois
lados. Duas camadas:

1. ``refuse_incoherent_unit`` ligado em ``pre_save`` dos dois modelos
   (``shopman/shop/apps.py``): recusa em **toda** porta (admin, shell, seed,
   API) o SKU ou a unidade que, entrando ou mudando, divergir do outro lado.
2. ``check_sku_namespace_coherence`` (``shopman/shop/checks.py``, SHOPMAN_W015):
   varre o que já está no banco e grita no boot. Warning, não Error — dado
   preexistente não pode trancar o dono para fora do próprio conserto.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from shopman.utils.units import normalize


def _normalize_sku(sku: str | None) -> str:
    return (sku or "").strip()


def units_agree(first: str | None, second: str | None) -> bool:
    """Os dois cadastros do mesmo SKU contam na mesma unidade?"""
    return normalize(first) == normalize(second)


@dataclass(frozen=True)
class SkuIncoherence:
    """Um SKU com cadastro de venda e de compra em unidades diferentes."""

    sku: str
    product_unit: str
    material_unit: str

    def __str__(self) -> str:
        return f"{self.sku} (venda em {self.product_unit}, compra em {self.material_unit})"


def find_sku_incoherences() -> list[SkuIncoherence]:
    """SKUs com cadastro de venda e de compra que discordam da unidade."""
    from shopman.buyman.models import Material
    from shopman.offerman.models import Product

    material_units = dict(Material.objects.values_list("sku", "unit"))
    if not material_units:
        return []
    incoherent = []
    for sku, unit in Product.objects.filter(sku__in=material_units).values_list("sku", "unit").order_by("sku"):
        if not units_agree(unit, material_units[sku]):
            incoherent.append(SkuIncoherence(sku=sku, product_unit=unit, material_unit=material_units[sku]))
    return incoherent


def refuse_incoherent_unit(instance, *, other_model, this_label: str, other_label: str) -> None:
    """Recusa o SKU (ou a unidade) que diverge do cadastro do outro lado.

    Só olha quando o SKU ou a unidade estão **entrando ou mudando**: linha
    antiga já incoerente continua salvável em outros campos (é o único jeito de
    o dono consertá-la), e a varredura do boot é quem cobra o conserto.
    """
    sku = _normalize_sku(getattr(instance, "sku", ""))
    if not sku:
        return
    unit = getattr(instance, "unit", "")

    if instance.pk is not None:
        previous = type(instance).objects.filter(pk=instance.pk).values_list("sku", "unit").first()
        if previous is not None and _normalize_sku(previous[0]) == sku and units_agree(previous[1], unit):
            return

    other_unit = other_model.objects.filter(sku=sku).values_list("unit", flat=True).first()
    if other_unit is None or units_agree(unit, other_unit):
        return

    raise ValidationError({
        "unit": (
            f"O SKU '{sku}' já tem {other_label} em '{other_unit}', e aqui a unidade é '{unit}'. "
            f"{this_label} e {other_label} do mesmo SKU contam o mesmo estoque, "
            f"então falam a mesma unidade. Use '{other_unit}' aqui, ou corrija o outro lado primeiro."
        )
    })


def refuse_material_unit_incoherent_with_product(sender, instance, **kwargs) -> None:
    from shopman.offerman.models import Product

    refuse_incoherent_unit(
        instance,
        other_model=Product,
        this_label="O cadastro de compra",
        other_label="cadastro de venda",
    )


def refuse_product_unit_incoherent_with_material(sender, instance, **kwargs) -> None:
    from shopman.buyman.models import Material

    refuse_incoherent_unit(
        instance,
        other_model=Material,
        this_label="O cadastro de venda",
        other_label="cadastro de compra",
    )
