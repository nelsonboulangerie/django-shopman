"""O namespace de SKU é um só, e o porteiro dele mora aqui.

``offerman.Product.sku`` e ``buyman.Material.sku`` são únicos **cada um na sua
tabela**; nada no banco impede o mesmo SKU nas duas. Quando isso acontece, todo
caminho composto do orquestrador resolve o produto primeiro
(``shopman/shop/adapters/catalog_backend.py``, ``shopman/shop/adapters/sku_validator.py``)
e o insumo homônimo desaparece sem barulho: a ficha técnica passa a validar
contra a unidade do produto, a disponibilidade responde pela política de venda —
e, pior de tudo, o ledger do Stockman é indexado por SKU, então vender a garrafa
consome a água da massa no mesmo quant.

Cores nunca se importam (ADR-001): nem o Buyman conhece o Offerman, nem o
contrário. A colisão é, portanto, pergunta do **orquestrador** — que já é quem
compõe os dois lados. O porteiro tem três camadas:

1. ``refuse_sku_collision`` ligado em ``pre_save`` dos dois modelos
   (``shopman/shop/apps.py``): recusa a colisão em **toda** porta (admin, shell,
   seed, API), não só na do admin.
2. ``check_sku_namespace_collision`` (``shopman/shop/checks.py``): varre o que já
   está no banco e grita no boot. Warning, não Error — colisão preexistente não
   pode trancar o dono para fora do próprio conserto.
3. ``ComposedCatalogBackend.get_product``: se a colisão existir mesmo assim, a
   precedência segue determinística (produto) mas é **anunciada** em log de erro.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError


def _normalize(sku: str | None) -> str:
    return (sku or "").strip()


def find_sku_collisions() -> list[str]:
    """SKUs que existem ao mesmo tempo como produto vendável e como insumo."""
    from shopman.buyman.models import Material
    from shopman.offerman.models import Product

    material_skus = set(Material.objects.values_list("sku", flat=True))
    if not material_skus:
        return []
    return sorted(
        Product.objects.filter(sku__in=material_skus).values_list("sku", flat=True)
    )


def refuse_sku_collision(instance, *, other_model, other_label: str, field_label: str) -> None:
    """Recusa um SKU que já pertence ao outro lado do namespace.

    Só olha quando o SKU está **entrando ou mudando**: linha antiga com colisão
    preexistente continua salvável (é o único jeito de o dono consertá-la), e a
    varredura do boot é quem cobra o conserto.
    """
    sku = _normalize(getattr(instance, "sku", ""))
    if not sku:
        return

    if instance.pk is not None:
        previous = (
            type(instance)
            .objects.filter(pk=instance.pk)
            .values_list("sku", flat=True)
            .first()
        )
        if previous is not None and _normalize(previous) == sku:
            return

    if not other_model.objects.filter(sku=sku).exists():
        return

    raise ValidationError({
        "sku": (
            f"O SKU '{sku}' já existe como {other_label}. "
            f"{field_label} e {other_label} dividem um único namespace de SKU — "
            "o estoque, a ficha técnica e o catálogo indexam por ele. "
            "Escolha outro SKU."
        )
    })


def refuse_material_sku_taken_by_product(sender, instance, **kwargs) -> None:
    from shopman.offerman.models import Product

    refuse_sku_collision(
        instance,
        other_model=Product,
        other_label="produto vendável (Offerman)",
        field_label="Insumo (Buyman)",
    )


def refuse_product_sku_taken_by_material(sender, instance, **kwargs) -> None:
    from shopman.buyman.models import Material

    refuse_sku_collision(
        instance,
        other_model=Material,
        other_label="insumo (Buyman)",
        field_label="Produto vendável (Offerman)",
    )
