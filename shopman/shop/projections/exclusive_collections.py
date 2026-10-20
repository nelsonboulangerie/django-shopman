"""Leitura das coleções exclusivas de grupo para o cardápio: UMA consulta por pedido.

A decisão (quem enxerga o quê) é ``shop/policies/exclusive_collections.py``. Aqui só
se lê a tabela de vantagens ativas de uma vez e se monta a subconsulta dos produtos
que só existem em coleção escondida. Qualquer que seja o tamanho do cardápio, do
número de grupos ou de coleções, o custo é o mesmo. O cardápio anônimo não depende de
quem pede, então segue igual para todos e cacheável na borda
(``storefront/api/public_cache.py``).
"""

from __future__ import annotations

from typing import Any

from shopman.shop.policies.exclusive_collections import CollectionAccess, collection_access


def access_for_tiers(price_tier_refs=()) -> CollectionAccess:
    """O acesso de quem é membro dos grupos ``price_tier_refs`` (vazio = anônimo)."""
    from shopman.guestman.models import PriceTierAdvantage

    rows = PriceTierAdvantage.objects.filter(
        kind=PriceTierAdvantage.Kind.EXCLUSIVE_COLLECTIONS, is_active=True,
    ).values_list("tier__ref", "config")
    return collection_access(rows, member_of=price_tier_refs or ())


def access_for_customer(customer: Any) -> CollectionAccess:
    """O acesso do cliente identificado, ou do anônimo com ``None``."""
    if customer is None:
        return access_for_tiers(())
    return access_for_tiers(list(customer.price_tiers.values_list("ref", flat=True)))


def exclusive_only_product_ids(access: CollectionAccess):
    """Subconsulta dos produtos que só existem em coleções escondidas deste cliente.

    Produto que está numa coleção exclusiva E numa comum continua no cardápio pela
    comum; o que está só nas exclusivas é do grupo.
    """
    from shopman.offerman.models import CollectionItem

    hidden = access.hidden
    in_hidden = CollectionItem.objects.filter(collection__ref__in=hidden).values("product_id")
    in_visible = CollectionItem.objects.exclude(collection__ref__in=hidden).values("product_id")
    return in_hidden.exclude(product_id__in=in_visible)
