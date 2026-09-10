"""Entidades do backstage no cofre de dados curados.

Entram só as tabelas de curadoria manual — os de-paras confirmados a mão
(tradução de anos de histórico), o vocabulário de consumo do B.I. e o mapa do
salão. O transacional do backstage (tickets, fechamentos, episódios, histórico
importado) fica com o backup do banco, como todo transacional.

A direção de import respeita a regra dos 3 apps: backstage → shop, nunca o
contrário — o registro do cofre mora no shop e o backstage se inscreve nele.
"""

from __future__ import annotations

from import_export import resources
from shopman.offerman.models import Product

from shopman.backstage.models import (
    CategoryAlias,
    ConsumptionRole,
    PaymentMethodAlias,
    ProductAlias,
    ProductConsumptionTag,
    SeatingSpot,
)
from shopman.shop.backup import registry
from shopman.shop.backup.resources import NaturalKeyMeta, _fk


class ConsumptionRoleResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = ConsumptionRole
        import_id_fields = ("ref",)


class ProductConsumptionTagResource(resources.ModelResource):
    role = _fk(ConsumptionRole, "ref", "role")

    class Meta(NaturalKeyMeta):
        model = ProductConsumptionTag
        import_id_fields = ("sku",)


class SeatingSpotResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = SeatingSpot
        import_id_fields = ("ref",)


#: FKs de assinatura (``confirmed_by`` → User) ficam fora, como todo usuário.
class _AliasMeta(NaturalKeyMeta):
    exclude = NaturalKeyMeta.exclude + ("confirmed_by",)


class ProductAliasResource(resources.ModelResource):
    product = _fk(Product, "sku", "product")

    class Meta(_AliasMeta):
        model = ProductAlias
        import_id_fields = ("source", "external_sku", "external_name")


class CategoryAliasResource(resources.ModelResource):
    class Meta(_AliasMeta):
        model = CategoryAlias
        import_id_fields = ("pattern",)


class PaymentMethodAliasResource(resources.ModelResource):
    class Meta(_AliasMeta):
        model = PaymentMethodAlias
        import_id_fields = ("pattern",)


def register_backstage_resources() -> None:
    for name, resource, tier in (
        ("consumption_roles", ConsumptionRoleResource, 0),
        ("seating_spots", SeatingSpotResource, 0),
        ("category_aliases", CategoryAliasResource, 0),
        ("payment_method_aliases", PaymentMethodAliasResource, 0),
        ("product_consumption_tags", ProductConsumptionTagResource, 1),
        ("product_aliases", ProductAliasResource, 1),
    ):
        registry.register(name, resource, tier=tier)
