"""De-para histórico para comandos de curadoria e importação do BI."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def rename_map() -> dict[str, str]:
    """Todo código que já foi nosso → o código que ele virou, nas duas levas.

    Em cache porque são tabelas literais, editadas por commit e não em runtime.
    """
    from config.management.commands.apply_product_skus import AJUSTES, RENAMES
    from config.management.commands.rename_skus_to_real import RENAMES as PRIMEIRA

    return dict(tuple(PRIMEIRA) + tuple(RENAMES) + tuple(AJUSTES))


def current_sku(sku: str, known) -> str:
    """Segue a cadeia de renames até um código que EXISTE em ``known``.

    ``known`` é o conjunto do que existe hoje — normalmente os SKUs do
    catálogo. Devolve o próprio ``sku`` quando ele já existe, ou quando não há
    para onde ir.
    """
    destino = rename_map()
    atual, visitados = sku, {sku}
    while atual not in known and atual in destino and destino[atual] not in visitados:
        atual = destino[atual]
        visitados.add(atual)
    return atual
