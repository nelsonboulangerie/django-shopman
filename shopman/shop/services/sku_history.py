"""Que código este produto já teve, e qual ele é hoje.

O catálogo trocou de código duas vezes: em agosto os nomes inventados pela
geração automática viraram os códigos do Yooga (``CROISSANT`` → ``CT``), e em
setembro os do Yooga viraram os curados (``CT`` → ``CRO``). Quem precisa
responder *"para onde foi este código?"* — o cardápio do iFood, o 301 da loja,
a herança de peso do B.I. — tem de olhar as **duas** levas, e encadeadas.

As tabelas moram nos comandos que as aplicam, que é onde a curadoria as edita.
Este módulo é a porta para quem só quer perguntar: um serviço do orquestrador,
importável do caminho de request sem arrastar ``config.management.commands``.

**A cadeia se resolve contra o catálogo vivo, nunca no papel.** Ela encadeia
(``BAGUETE → BF → TRADI``) e chega a **voltar**: ``FENDU`` virou ``FE`` em
agosto, e ``FE`` voltou a ``FENDU`` em setembro. No papel isso é um ciclo, e
qualquer desempate seria chute; contra o catálogo não há dúvida — para-se no
código que EXISTE. É o que impede um 301 de mandar a página boa do ``FENDU``
para o ``FE``, que é 404.
"""

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


def live_product_skus() -> frozenset[str]:
    """Os SKUs do catálogo agora. Consulta — quem chama em laço que guarde."""
    from shopman.offerman.models import Product

    return frozenset(Product.objects.values_list("sku", flat=True))


def retired_skus(known=None) -> dict[str, str]:
    """{código aposentado: código de hoje} — só os que levam a produto vivo.

    É o mapa que um redirect permanente quer: a chave não existe mais, o valor
    existe. Código que não chega a lugar nenhum fica de fora, porque para ele
    não há destino honesto — o produto saiu do catálogo, e isso é 410, não 301.
    """
    if known is None:
        known = live_product_skus()
    destino = rename_map()
    return {
        antigo: atual
        for antigo in destino
        if antigo not in known and (atual := current_sku(antigo, known)) in known
    }
