"""Coleções exclusivas de grupo: quem enxerga qual coleção do cardápio.

A vantagem ``exclusive_collections`` do grupo (``PriceTierAdvantage.config
["collection_refs"]``, escrita pelo Gestor) diz que aquelas coleções do Offerman são
do grupo: o cardápio as mostra ao cliente identificado que é membro, e a esconde de
todo o resto, anônimo incluído.

Não acumula nem compete: cliente em dois grupos enxerga as coleções dos dois. A regra
"vale a melhor, sem acumular" é sobre vantagens concorrentes (dois descontos); duas
coleções não disputam nada.

Uma consulta resolve o cardápio inteiro, qualquer que seja o número de coleções, de
grupos ou de produtos: a tabela de vantagens é lida de uma vez e o resto é conjunto.
O cardápio anônimo não depende de quem pede, então continua igual para todos e
cacheável na borda (``storefront/api/public_cache.py``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionAccess:
    """As coleções exclusivas de algum grupo, e quais delas este cliente enxerga."""

    exclusive: frozenset[str]
    granted: frozenset[str]

    @property
    def hidden(self) -> frozenset[str]:
        return self.exclusive - self.granted

    def is_hidden(self, collection_ref: str | None) -> bool:
        return bool(collection_ref) and collection_ref in self.hidden


NO_EXCLUSIVES = CollectionAccess(exclusive=frozenset(), granted=frozenset())


def collection_access(price_tier_refs=()) -> CollectionAccess:
    """Quais coleções são exclusivas e quais o cliente dos grupos ``price_tier_refs`` vê."""
    from shopman.guestman.models import PriceTierAdvantage

    member_of = {str(ref) for ref in (price_tier_refs or ()) if ref}
    exclusive: set[str] = set()
    granted: set[str] = set()
    rows = PriceTierAdvantage.objects.filter(
        kind=PriceTierAdvantage.Kind.EXCLUSIVE_COLLECTIONS, is_active=True,
    ).values_list("tier__ref", "config")
    for tier_ref, config in rows:
        refs = {str(ref).strip() for ref in ((config or {}).get("collection_refs") or []) if str(ref).strip()}
        exclusive |= refs
        if tier_ref in member_of:
            granted |= refs
    if not exclusive:
        return NO_EXCLUSIVES
    return CollectionAccess(exclusive=frozenset(exclusive), granted=frozenset(granted))


def customer_collection_access(customer) -> CollectionAccess:
    """O acesso do cliente (ou do anônimo, com ``None``)."""
    if customer is None:
        return collection_access(())
    return collection_access(customer.price_tiers.values_list("ref", flat=True))


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
