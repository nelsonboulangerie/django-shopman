"""Os dois cadastros de um SKU: o de compra e o de venda.

Um SKU é uma coisa só. Ele pode ter:

- **cadastro de compra** (``buyman.Material``) — é o que o torna *comprável*:
  fornecedor, custo, conversão, mínimo, pedido de compra;
- **cadastro de venda** (``offerman.Product``) — é o que o torna *vendável*,
  e vender é decisão estratégica explícita, nunca inferida.

A coisa comprada que também se vende (o pote de geleia, o queijo, o chá em
lata) tem os dois, com o mesmo SKU e a mesma unidade, e por isso o mesmo
estoque (ver ``shopman/shop/services/sku_namespace.py``).

Cores não se importam (ADR-001): criar um cadastro a partir do outro é
composição, e mora no orquestrador.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from shopman.utils.units import normalize


def purchase_unit_for(unit: str | None) -> str:
    """A unidade do cadastro de compra para a unidade de venda ``unit``.

    O cadastro de compra fala só a tabela fechada de ``Material.Unit``; unidade
    fora dela (``dz``, texto livre) é recusada em vez de adivinhada.
    """
    from shopman.buyman.models import Material

    canonical = normalize(unit)
    if canonical not in Material.Unit.values:
        known = ", ".join(Material.Unit.values)
        raise ValidationError({
            "unit": (
                f"A unidade '{unit}' não serve para o cadastro de compra ({known}). "
                "Acerte a unidade do produto antes de torná-lo comprável."
            )
        })
    return canonical


def is_produced_here(sku: str) -> bool:
    """Existe ficha ATIVA que produz este SKU?"""
    from shopman.craftsman.models import Recipe

    return Recipe.objects.filter(output_sku=sku, is_active=True).exists()


def ensure_purchase_record(product, *, refuse_if_produced: bool = True):
    """Garante o cadastro de compra do SKU de ``product``. Devolve ``(material, mudou)``.

    Cria o ``Material`` com o mesmo SKU, nome, unidade e validade do produto,
    ou reativa o que existia inativo. O que já existe ativo não é tocado: o
    cadastro de compra tem dono próprio (nome da nota, validade do fornecedor).

    Com ``refuse_if_produced`` (padrão), recusa o SKU que tem ficha ativa: o
    estoque dele entra pela Produção, e a mesma peça pelas duas portas
    dobraria o estoque sem ninguém perceber.
    """
    from shopman.buyman.models import Material

    if refuse_if_produced and is_produced_here(product.sku):
        raise ValidationError({
            "sku": (
                f"{product.name} é produzido aqui: tem ficha ativa, e o estoque dele "
                "entra pela Produção, não pela compra."
            )
        })

    material = Material.objects.filter(sku=product.sku).first()
    if material is None:
        material = Material(
            sku=product.sku,
            name=product.name,
            unit=purchase_unit_for(product.unit),
            shelf_life_days=product.shelf_life_days,
        )
        material.full_clean()
        material.save()
        return material, True
    if not material.is_active:
        material.is_active = True
        material.save(update_fields=["is_active", "updated_at"])
        return material, True
    return material, False
