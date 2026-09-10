"""Produto que sumiu do cardápio porque a categoria dele foi desativada.

O agrupamento do cardápio (``catalog_context.published_products_by_collection``)
tem dois baldes: o produto entra no grupo de cada coleção **ativa** a que
pertence, e quem não pertence a coleção nenhuma cai no balde "sem categoria" —
que é literalmente ``exclude(collection_items__isnull=False)``.

Falta um terceiro caso, e é justamente o silencioso: o produto cujo **único**
vínculo é com uma coleção **inativa**. Ele não entra em grupo nenhum (nenhuma
coleção ativa o contém) e também não é "descategorizado" (vínculo ele tem).
Some do cardápio inteiro — publicado, listado na vitrine, com preço e com
estoque — porque alguém desmarcou a categoria.

A política do cardápio fica como está: este módulo **não** muda o que o cliente
vê. Ele torna o estado VISÍVEL para quem pode consertar, em dois lugares:

* a linha do produto no Gestor (``backstage.projections.catalog``);
* o sino do operador (``check_catalog_visibility``, no ciclo de manutenção).

A regra mora aqui uma vez só de propósito. Escrita duas vezes, ela diverge — e
divergir aqui significa a tela dizer uma coisa e o alerta outra sobre o mesmo
produto.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HiddenProduct:
    """Um produto invisível-por-categoria, com as coleções que o seguram."""

    sku: str
    name: str
    #: Coleções (inativas) às quais o produto está vinculado — o que consertar.
    collection_refs: tuple[str, ...]
    collection_names: tuple[str, ...]


def menu_visible_queryset(listing_ref: str | None = None):
    """Produtos que passariam pelo filtro do cardápio.

    Reaproveita ``catalog_context.published_products`` — o MESMO filtro que monta
    o ``base`` do agrupamento — em vez de reescrevê-lo. Sem ``listing_ref``, a
    pergunta vira "está em alguma vitrine ativa?", com o mesmo predicado de
    listing que aquela função aplica quando recebe um ref.
    """
    from shopman.shop.projections import catalog_context

    qs = catalog_context.published_products(listing_ref)
    if not listing_ref:
        qs = qs.filter(
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
        )
    return qs


def hidden_by_inactive_collection_queryset(listing_ref: str | None = None):
    """Produtos vendáveis que nenhuma coleção ativa alcança — mas que TÊM coleção.

    Os dois lados da regra importam. ``filter(collection_items__isnull=False)``
    deixa de fora o "sem categoria" legítimo, que o cardápio já mostra no balde
    final. O ``exclude`` é sobre relação multivalorada, então o Django gera um
    ``NOT IN (subquery)``: sai quem tem **qualquer** vínculo com coleção ativa —
    exatamente quem o cardápio consegue agrupar.
    """
    return (
        menu_visible_queryset(listing_ref)
        .filter(collection_items__isnull=False)
        .exclude(collection_items__collection__is_active=True)
        .order_by("name")
        .distinct()
    )


def hidden_by_inactive_collection_skus(listing_ref: str | None = None) -> set[str]:
    """Só os SKUs — uma consulta para a matriz inteira do Gestor."""
    return set(
        hidden_by_inactive_collection_queryset(listing_ref)
        .order_by()
        .values_list("sku", flat=True)
    )


def hidden_by_inactive_collection(listing_ref: str | None = None) -> list[HiddenProduct]:
    """Os produtos invisíveis com as coleções inativas que os seguram.

    Ordenado por nome (o mesmo do queryset) para a mensagem do alerta sair
    estável entre varreduras — mensagem que muda de ordem a cada ciclo parece
    novidade e derrota o dedupe.
    """
    products = list(
        hidden_by_inactive_collection_queryset(listing_ref).prefetch_related(
            "collection_items__collection"
        )
    )
    result: list[HiddenProduct] = []
    for product in products:
        collections = sorted(
            {
                (item.collection.ref, item.collection.name)
                for item in product.collection_items.all()
                if not item.collection.is_active
            }
        )
        result.append(
            HiddenProduct(
                sku=product.sku,
                name=product.name,
                collection_refs=tuple(ref for ref, _ in collections),
                collection_names=tuple(name for _, name in collections),
            )
        )
    return result
