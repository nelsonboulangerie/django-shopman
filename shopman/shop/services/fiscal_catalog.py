"""Completude fiscal do catálogo — porteiro na publicação e leitura de auditoria.

A pergunta ("este vendável pode virar item de nota?") é do Fiscalman
(``shopman.fiscalman.classification.validate_for_emission``). O que vive aqui é
o **quando** perguntar, que é assunto do orquestrador: quem sabe o que é "canal
de venda" é o ``Channel``, e quem sabe o que é "publicado num canal" é o par
``Listing``/``ListingItem`` do Offerman (convenção da casa: ``Listing.ref ==
Channel.ref``).

Dois consumidores:

- **Porteiro** (``publication_errors``): recusa publicar vendável fiscalmente
  incompleto num canal de venda. Ligado por
  ``SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH``, **desligado por padrão**
  no pré-go-live — o catálogo ainda está sendo classificado com o contador. A
  chave vira na virada, junto com o adapter fiscal. Wiring dos signals em
  ``shopman/shop/handlers/fiscal_gate.py``.
- **Auditoria** (``incomplete_published_products``): responde "quais vendáveis
  publicados estão fiscalmente incompletos?" ANTES do primeiro dia de emissão
  obrigatória, em vez de a cada nota recusada. Comando:
  ``manage.py fiscal_audit_catalog``.

A guarda tardia do adapter (``fiscal_focusnfe._map_item`` recusa item sem NCM)
continua onde está: última linha, não a única.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

SETTING_REQUIRE_ON_PUBLISH = "SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH"


@dataclass(frozen=True)
class IncompleteProduct:
    """Um vendável publicado que ainda não pode virar item de nota."""

    sku: str
    name: str
    listing_refs: tuple[str, ...]
    errors: tuple[str, ...]


def publication_gate_enabled() -> bool:
    """O porteiro está ligado neste deployment?"""
    return bool(getattr(settings, SETTING_REQUIRE_ON_PUBLISH, False))


def product_errors(product) -> list[str]:
    """Erros fiscais do produto, perguntados ao dono do schema (Fiscalman)."""
    from shopman.fiscalman.classification import validate_for_emission

    return validate_for_emission(getattr(product, "metadata", None))


def selling_channel_refs() -> set[str]:
    """Refs dos canais ATIVOS que fecham venda — os que podem gerar documento fiscal.

    ``commerce_policy=display`` (menuboard, catálogo do Google/Meta) mostra preço
    e nunca transaciona: não emite nota, logo não tem porteiro fiscal.
    """
    from shopman.shop.models import Channel

    return set(
        Channel.objects.filter(
            is_active=True, commerce_policy=Channel.CommercePolicy.ORDER
        ).values_list("ref", flat=True)
    )


def _published_items_qs(*, product_id: int | None = None):
    """Itens de vitrine publicados+vendáveis em vitrine ativa de canal de venda.

    Não filtra o estado do **produto** de propósito: o porteiro precisa avaliar o
    produto que está sendo salvo (cujo estado novo ainda não está no banco).
    """
    from shopman.offerman.models import ListingItem

    qs = ListingItem.objects.filter(
        is_published=True,
        is_sellable=True,
        listing__is_active=True,
        listing__ref__in=selling_channel_refs(),
    )
    if product_id is not None:
        qs = qs.filter(product_id=product_id)
    return qs


def has_selling_publication(product_id: int) -> bool:
    """O produto está publicado em alguma vitrine de canal de venda?"""
    return _published_items_qs(product_id=product_id).exists()


def publication_errors(product, *, listing_ref: str = "") -> list[str]:
    """Erros que impedem publicar este vendável num canal de venda.

    Vazio quando o porteiro está desligado, quando o produto não está
    publicado+vendável (produto despublicado não vende, logo não emite), ou
    quando a classificação está completa.
    """
    if not publication_gate_enabled():
        return []
    if not (getattr(product, "is_published", False) and getattr(product, "is_sellable", False)):
        return []
    if listing_ref and listing_ref not in selling_channel_refs():
        return []
    return product_errors(product)


def incomplete_published_products() -> list[IncompleteProduct]:
    """Vendáveis publicados em canal de venda que ainda não podem virar nota.

    Independe do porteiro estar ligado: a auditoria existe justamente para
    responder o que aconteceria se ligasse (e o que a SEFAZ recusaria).
    """
    items = (
        _published_items_qs()
        .filter(product__is_published=True, product__is_sellable=True)
        .select_related("product", "listing")
        .order_by("product__sku", "listing__ref")
    )

    by_product: dict[int, tuple[object, set[str]]] = {}
    for item in items:
        product, refs = by_product.setdefault(item.product_id, (item.product, set()))
        refs.add(item.listing.ref)

    incomplete = []
    for product, refs in by_product.values():
        errors = product_errors(product)
        if not errors:
            continue
        incomplete.append(
            IncompleteProduct(
                sku=product.sku,
                name=product.name,
                listing_refs=tuple(sorted(refs)),
                errors=tuple(errors),
            )
        )
    return sorted(incomplete, key=lambda p: p.sku)
