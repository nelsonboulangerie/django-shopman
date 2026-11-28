"""Coleções exclusivas de grupo: quem enxerga qual coleção do cardápio.

A vantagem ``exclusive_collections`` do grupo (``PriceTierAdvantage.config
["collection_refs"]``, escrita pelo Gestor) diz que aquelas coleções do Offerman são
do grupo: o cardápio as mostra ao cliente identificado que é membro, e as esconde de
todo o resto, anônimo incluído.

Não acumula nem compete: cliente em dois grupos enxerga as coleções dos dois. A regra
"vale a melhor, sem acumular" é sobre vantagens concorrentes (dois descontos); duas
coleções não disputam nada.

Sem Django, sem banco: recebe as linhas ``(grupo, config)`` das vantagens ativas e os
grupos do cliente, e devolve o acesso. Quem lê o banco é
``shop/projections/exclusive_collections.py``, numa consulta.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


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

    def hides_product(self, collection_refs: Iterable[str]) -> bool:
        """O produto destas coleções é do grupo para este cliente?

        Só quando TODAS as coleções dele estão escondidas: o que também está numa
        coleção comum continua por ela, e o que não está em coleção nenhuma não é
        de grupo nenhum. É a mesma regra da subconsulta do cardápio
        (``exclusive_only_product_ids``), para um produto só: a página do produto
        e a sacola respondem o mesmo que o cardápio.
        """
        refs = {str(ref) for ref in collection_refs if ref}
        return bool(refs) and refs <= self.hidden


def collection_access(
    rows: Iterable[tuple[str, Mapping[str, Any] | None]],
    *,
    member_of: Iterable[str] = (),
) -> CollectionAccess:
    """O acesso de quem é membro de ``member_of``, dadas as vantagens ativas ``rows``."""
    groups = {str(ref) for ref in member_of if ref}
    exclusive: set[str] = set()
    granted: set[str] = set()
    for tier_ref, config in rows:
        refs = {str(ref).strip() for ref in ((config or {}).get("collection_refs") or []) if str(ref).strip()}
        exclusive |= refs
        if tier_ref in groups:
            granted |= refs
    return CollectionAccess(exclusive=frozenset(exclusive), granted=frozenset(granted))
