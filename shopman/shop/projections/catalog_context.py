"""Canonical catalog read context for Shopman surfaces.

This module is the shop-level boundary for catalog, listing, price, and basic
availability reads. Storefront projections/services should depend on this file
instead of importing Offerman or Stockman directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import models

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasicAvailability:
    """Small availability shape shared by catalog UI and neutral exports."""

    status: str
    available_qty: int | None
    can_add_to_cart: bool


@dataclass(frozen=True)
class CommercialIdentity:
    """Quem fabrica o produto e como ele se identifica no comércio.

    É o mesmo dado que o feed do Google/Meta publica (``Product.metadata['social']``,
    editado no Catálogo do Gestor). Vazio quer dizer "não informado" — não é licença
    para supor que a marca é a da loja: a loja também revende produto de terceiro.
    """

    brand: str
    gtin: str
    mpn: str
    condition: str


CHOICE_GROUP_KEY = "choice_group"


def choice_group(product) -> str:
    """Nome do cartão de escolha que reúne este produto a outros (ou ``""``).

    Dado, não código: ``Product.metadata["choice_group"]`` é o NOME que o
    cliente e o balcão leem no cartão ("Chás da casa"), escrito no Admin. Os
    produtos com o mesmo nome viram um cartão só, que abre a escolha entre eles;
    cada escolha continua sendo o próprio SKU (preço, estoque, ficha, nota e KDS
    não mudam). O nome é a identidade do grupo: espaços repetidos não separam
    dois grupos. Ausente, vazio ou malformado = o produto aparece sozinho.
    """
    metadata = getattr(product, "metadata", None)
    if not isinstance(metadata, dict):
        return ""
    raw = metadata.get(CHOICE_GROUP_KEY)
    if not isinstance(raw, str):
        return ""
    return " ".join(raw.split())


def choice_group_label(product) -> str:
    """O que se escolhe no cartão de escolha ("Sabor"), ou ``""``.

    ``Product.metadata["choice_group_label"]``, escrito na aba Escolhas do Admin.
    """
    from shopman.shop import product_options

    return product_options.choice_group_label(product)


def option_groups(product) -> list[dict]:
    """Escolhas do produto no formato público (sem o insumo que cada opção gasta).

    ``[{ref, label, min, max, options: [{ref, label, price_q, available}]}]``;
    ``[]`` quando o produto não tem escolha. Fonte: ``shopman.shop.product_options``.
    """
    from shopman.shop import product_options

    return product_options.public_groups(product)


def commercial_identity(product) -> CommercialIdentity:
    from shopman.offerman import get_social_attributes

    attrs = get_social_attributes(product)
    return CommercialIdentity(
        brand=attrs.brand.strip(),
        gtin=attrs.gtin.strip(),
        mpn=attrs.mpn.strip(),
        condition=attrs.condition,
    )


def products_queryset():
    from shopman.offerman.models import Product

    return Product.objects.all()


def active_collections_queryset():
    from shopman.offerman.models import Collection

    return Collection.objects.filter(is_active=True)


def active_collections() -> list[Any]:
    return list(active_collections_queryset().order_by("sort_order", "name"))


def get_active_collection(collection_ref: str):
    return active_collections_queryset().filter(ref=collection_ref).first()


def listing_exists(listing_ref: str) -> bool:
    from shopman.offerman.models import Listing

    return Listing.objects.filter(ref=listing_ref, is_active=True).exists()


def get_product(sku: str):
    return products_queryset().filter(sku=sku).first()


def product_exists(sku: str) -> bool:
    return products_queryset().filter(sku=sku).exists()


def get_published_product(sku: str):
    return products_queryset().filter(sku=sku, is_published=True).first()


def get_sellable_published_product(sku: str):
    return products_queryset().filter(sku=sku, is_published=True, is_sellable=True).first()


def comes_out_of_the_oven(sku: str) -> bool:
    """Este SKU nasce de uma fornada, ou chega pronto na prateleira?

    Duas evidências, nesta ordem, porque nenhuma sozinha basta:

    1. ``Product.is_batch_produced`` — a declaração do gestor. É a resposta
       autoritativa quando alguém a deu.
    2. Uma ``Recipe`` ativa com ``output_sku`` igual a este SKU — a evidência
       operacional. Existe porque a declaração NÃO é preenchida na prática: no
       banco vivo do alpha (05/09/2026) todo produto tem ``is_batch_produced``
       em ``False``, inclusive os pães. Confiar só na flag entregaria uma
       derivação que nunca dispara, e o defeito voltaria calado.

    A receita ativa é também exatamente o conjunto de SKUs que algum dia vai
    disparar ``production_changed`` — que é o evento por trás do aviso "saiu do
    forno". Perguntar por outra coisa prometeria um aviso que nunca chega.

    Falha para ``False``: na dúvida o produto é de prateleira, e o eixo de
    prateleira (chegada de estoque) tem mais caminhos de chegada.
    """
    product = products_queryset().filter(sku=sku).only("sku", "is_batch_produced").first()
    if product is not None and product.is_batch_produced:
        return True
    try:
        from shopman.craftsman.models import Recipe

        return Recipe.objects.filter(output_sku=sku, is_active=True).exists()
    except Exception:
        logger.debug("catalog_context.comes_out_of_the_oven degraded sku=%s", sku, exc_info=True)
        return False


def products_by_sku(skus: list[str], *, only_published: bool = True) -> dict[str, Any]:
    # Carrega de uma vez o que o card lê de cada produto (as tags, por
    # ``product_tags``; os componentes, por ``is_bundle``) para listas avulsas de
    # SKU (substitutos e cross-sell da PDP, trilhos da home) não caírem em N+1.
    qs = products_queryset().filter(sku__in=skus).prefetch_related("components")
    if only_published:
        qs = qs.filter(is_published=True)
    products = list(qs)
    attach_tag_names(products)
    return {product.sku: product for product in products}


# Atributo onde ``attach_tag_names`` deixa os nomes das tags de cada produto,
# já ordenados, para ``product_tags`` não ir ao banco por produto.
_TAG_NAMES_ATTR = "_catalog_tag_names"


def attach_tag_names(products: list[Any]) -> None:
    """Lê as tags (``keywords``) de todos os ``products`` numa consulta só.

    O ``prefetch_related("keywords")`` fazia o mesmo número de consultas, mas
    materializava um ``Tag`` por vínculo (≈200 no cardápio) para o card ler
    só o ``name``. Aqui sai o par ``(produto, nome)`` direto do banco.
    """
    if not products:
        return
    from django.contrib.contenttypes.models import ContentType

    model = type(products[0])
    names_by_pk: dict[Any, list[str]] = {}
    for object_id, name in model.keywords.through.objects.filter(
        content_type=ContentType.objects.get_for_model(model),
        object_id__in=[product.pk for product in products],
    ).values_list("object_id", "tag__name"):
        names_by_pk.setdefault(object_id, []).append(name)
    for product in products:
        setattr(product, _TAG_NAMES_ATTR, tuple(sorted(names_by_pk.get(product.pk, ()))))


def published_products(listing_ref: str | None = None):
    qs = products_queryset().filter(is_published=True)
    if listing_ref:
        qs = qs.filter(
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
        )
    return qs


def active_collections_with_counts() -> list[dict]:
    from shopman.offerman.models import CollectionItem

    data = []
    for collection in active_collections():
        count = CollectionItem.objects.filter(
            collection=collection,
            product__is_published=True,
        ).count()
        data.append({
            "ref": collection.ref,
            "name": collection.name,
            "description": getattr(collection, "description", None) or "",
            "product_count": count,
        })
    return data


def keywords_by_sku(skus: list[str]) -> dict[str, list[str]]:
    if not skus:
        return {}

    result: dict[str, list[str]] = {}
    for product in products_queryset().filter(sku__in=skus).prefetch_related("keywords"):
        try:
            result[product.sku] = [str(tag.name) for tag in product.keywords.all()]
        except Exception:
            logger.debug("catalog_context.keywords_by_sku degraded; using fallback", exc_info=True)
            result[product.sku] = []
    return result


def related_skus(sku: str, *, limit: int = 6) -> list[str]:
    """SKUs for lateral discovery ("Você também pode gostar"), keyword-scored.

    This is **cross-sell**, NOT substitution: it does not restrict to the same
    collection (lateral = across categories) and is shown regardless of the
    reference's availability. Ranking = number of shared keywords (descending);
    ties keep the catalog's natural order. Returns ``[]`` when the product has
    no keywords to relate on.
    """
    from shopman.offerman.service import CatalogService

    product = CatalogService.get(sku)
    if product is None:
        return []
    own_keywords = {str(name) for name in product.keywords.names()}
    if not own_keywords:
        return []

    candidates = CatalogService.search(keywords=list(own_keywords), limit=limit * 4)
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        if candidate.sku == sku:
            continue
        shared = len(own_keywords & {str(name) for name in candidate.keywords.names()})
        if shared:
            scored.append((shared, candidate.sku))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate_sku for _, candidate_sku in scored[:limit]]


def image_urls_by_sku(skus) -> dict[str, str | None]:
    sku_list = [sku for sku in skus if sku]
    if not sku_list:
        return {}
    return {
        product.sku: (product.image_url or None)
        for product in products_queryset().filter(sku__in=sku_list).only("sku", "image_url")
    }


def collection_refs_by_sku(skus: list[str]) -> dict[str, list[str]]:
    from shopman.offerman.models import CollectionItem

    result: dict[str, list[str]] = {}
    if not skus:
        return result
    for sku, collection_ref in CollectionItem.objects.filter(product__sku__in=skus).values_list(
        "product__sku", "collection__ref",
    ):
        result.setdefault(sku, []).append(collection_ref)
    return result


def primary_collection_id_by_sku(skus: list[str]) -> dict[str, int]:
    from shopman.offerman.models import CollectionItem

    result: dict[str, int] = {}
    for item in CollectionItem.objects.filter(
        product__sku__in=skus,
        is_primary=True,
    ).select_related("collection", "product"):
        result[item.product.sku] = item.collection_id
    return result


def primary_collection_by_sku(skus: list[str]) -> dict:
    """Coleção primária (``CollectionItem.is_primary``) por SKU, em lote.

    Devolve o objeto ``Collection`` inteiro — quem projeta escolhe o que expor
    (ref, name, ``metadata["color"]``/``metadata["icon"]``). SKU sem coleção
    primária fica fora do dict.
    """
    from shopman.offerman.models import CollectionItem

    result: dict = {}
    if not skus:
        return result
    # Só o SKU do produto: anotado, sem materializar o ``Product`` inteiro.
    for item in (
        CollectionItem.objects.filter(product__sku__in=skus, is_primary=True)
        .select_related("collection")
        .annotate(product_sku=models.F("product__sku"))
    ):
        result[item.product_sku] = item.collection
    return result


def breadcrumb_collection(product):
    from shopman.offerman.models import CollectionItem

    item = (
        CollectionItem.objects.filter(product=product, collection__is_active=True)
        .select_related("collection")
        .order_by("collection__sort_order", "collection__name")
        .first()
    )
    return item.collection if item else None


def filter_by_collection(qs, collection_ref: str):
    """Filtra um queryset de Product por ref de coleção.

    Smart collections (com ``rule``) resolvem por regra; manuais usam
    ``CollectionItem``. Coleção inexistente/inativa → queryset vazio.
    """
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref, is_active=True).first()
    if coll is None:
        return qs.none()
    if coll.is_smart:
        return qs.filter(pk__in=coll.product_queryset().values("pk"))
    return qs.filter(collection_items__collection=coll)


def published_products_by_collection(
    *,
    listing_ref: str,
    active_collection: Any | None = None,
) -> list[tuple[str | None, list[Any]]]:
    """Return ordered (collection_ref | None, products) groups for a listing."""
    # O que o montador do cardápio lê de cada produto no laço vem junto, para não
    # virar N+1: ``components`` (lido por ``is_bundle`` → ``components.exists()``,
    # que usa o cache do prefetch) e as tags (``attach_tag_names``, lidas por
    # ``product_tags``).
    base = published_products(listing_ref).prefetch_related("components")

    if active_collection is not None:
        products = list(
            base.filter(collection_items__collection=active_collection)
            .order_by("collection_items__sort_order", "name")
            .distinct()
        )
        attach_tag_names(products)
        return [(active_collection.ref, products)]

    # Visão completa: UMA leitura de produtos e UMA de vínculos com coleção, e o
    # agrupamento em Python. Eram três consultas por coleção ativa (produto +
    # dois prefetches), 27 no cardápio de nove coleções, relendo os mesmos
    # produtos a cada volta. A ordem continua sendo a do banco: a posição de cada
    # produto em ``order_by("name")`` desempata o ``sort_order`` do vínculo, com a
    # collation do banco, e não com a comparação de string do Python.
    from shopman.offerman.models import CollectionItem

    products = list(base.order_by("name").distinct())
    if not products:
        return []
    attach_tag_names(products)
    name_rank = {p.pk: index for index, p in enumerate(products)}
    by_pk = {p.pk: p for p in products}

    links_by_collection: dict[Any, list[tuple[int, int, Any]]] = {}
    has_any_collection: set[Any] = set()
    for collection_id, product_id, sort_order in CollectionItem.objects.filter(
        product_id__in=list(by_pk),
    ).values_list("collection_id", "product_id", "sort_order"):
        has_any_collection.add(product_id)
        links_by_collection.setdefault(collection_id, []).append(
            (sort_order, name_rank[product_id], product_id),
        )

    groups: list[tuple[str | None, list[Any]]] = []
    for collection in active_collections():
        links = sorted(links_by_collection.get(collection.pk, ()))
        if links:
            groups.append((collection.ref, [by_pk[product_id] for _, _, product_id in links]))

    # Sem coleção nenhuma (nem inativa): mesmo critério do antigo
    # ``exclude(collection_items__isnull=False)``.
    uncategorized = [p for p in products if p.pk not in has_any_collection]
    if uncategorized:
        groups.append((None, uncategorized))
    return groups


def listing_price_map(
    skus: list[str],
    listing_ref: str,
    *,
    only_published: bool = True,
    only_sellable: bool = True,
) -> dict[str, int]:
    from shopman.offerman.models import ListingItem

    filters: dict[str, Any] = {
        "listing__ref": listing_ref,
        "listing__is_active": True,
        "product__sku__in": skus,
    }
    if only_published:
        filters["is_published"] = True
    if only_sellable:
        filters["is_sellable"] = True

    price_map: dict[str, int] = {}
    for sku, price_q in (
        ListingItem.objects.filter(**filters)
        .order_by("-min_qty")
        .values_list("product__sku", "price_q")
    ):
        price_map.setdefault(sku, price_q)
    return price_map


def listing_price_for_product(product, listing_ref: str) -> int | None:
    return listing_price_map([product.sku], listing_ref, only_published=True, only_sellable=False).get(product.sku)


def listing_sellable_map(
    skus: list[str],
    listing_ref: str,
    *,
    only_published: bool = True,
) -> dict[str, bool]:
    """Channel-level sellability by SKU for an active listing.

    Product-level ``is_sellable`` is not enough for storefront cards: a SKU can
    stay published in a channel while the operator pauses only that surface.
    Missing rows are intentionally omitted so ad-hoc callers can preserve their
    existing fallback behavior.
    """
    from shopman.offerman.models import ListingItem

    if not skus or not listing_ref:
        return {}

    filters: dict[str, Any] = {
        "listing__ref": listing_ref,
        "listing__is_active": True,
        "product__sku__in": skus,
    }
    if only_published:
        filters["is_published"] = True

    result: dict[str, bool] = {}
    for row in ListingItem.objects.filter(**filters).values("product__sku", "is_sellable"):
        sku = row["product__sku"]
        result[sku] = result.get(sku, False) or bool(row["is_sellable"])
    return result


def visible_skus_in_channel(skus: list[str], channel_ref: str) -> set[str] | None:
    """Quais destes SKUs APARECEM no canal, em lote. ``None`` = canal sem listing.

    Mesmo eixo de :func:`visible_in_channel` (só ``is_published``), na forma que
    as listas ad-hoc precisam: favoritos, cross-sell e trilhos da home montam
    cards a partir de um conjunto explícito de SKUs, sem passar pelo filtro de
    listing que o cardápio usa. Sem esta leitura, um SKU que nunca foi para a
    vitrine nascia com card, preço e botão "Adicionar" ativo — e o toque caía
    em 404. ``None`` (canal sem ``Listing``) mantém canais internos funcionando.
    """
    from shopman.offerman.models import ListingItem

    if not skus or not channel_ref or not listing_exists(channel_ref):
        return None

    return set(
        ListingItem.objects.filter(
            listing__ref=channel_ref,
            listing__is_active=True,
            product__sku__in=skus,
            is_published=True,
        ).values_list("product__sku", flat=True)
    )


def price_q_for_product(product, *, listing_ref: str | None) -> int | None:
    """List price (``_q`` cents) for a product on a channel listing.

    Surface-agnostic read facade: the caller supplies ``listing_ref`` (the
    storefront passes its channel ref). Falls back to ``base_price_q`` when the
    listing has no entry — keeps callers from re-implementing the fallback.
    """
    if listing_ref:
        price_q = listing_price_for_product(product, listing_ref)
        if price_q is not None:
            return price_q
    return product.base_price_q


def visible_in_channel(product, channel_ref: str, *, fallback_when_listing_missing: bool = True) -> bool:
    """O produto APARECE neste canal?

    ⚠️ Só ``is_published``. Ocultar (o antigo "despublicar") é o eixo do sumiço:
    item oculto não é listado, não é buscado e a URL direta devolve 404. Pausar
    (``is_sellable=False``) é outro eixo — o item continua na vitrine, dizendo
    "Indisponível". Misturar os dois fazia o card aparecer no cardápio e a PDP
    do mesmo item devolver 404 no toque.

    Canal sem ``Listing`` configurado cai em ``True``, para canais internos/de
    fallback (ex.: PDV) seguirem funcionando.
    """
    from shopman.offerman.models import ListingItem

    if fallback_when_listing_missing and not listing_exists(channel_ref):
        return True

    return ListingItem.objects.filter(
        listing__ref=channel_ref,
        listing__is_active=True,
        product=product,
        is_published=True,
    ).exists()


def active_promotions(channel_ref: str) -> list[Any]:
    """Promoções automáticas ativas que alcançam ``channel_ref`` — leitura.

    Existe para a projeção do cardápio pré-carregar o conjunto uma vez (uma query
    para o menu inteiro em vez de uma por SKU) **sem montar a própria consulta**: a
    régua de escopo de canal tem um dono só, ``services.promotions``, o mesmo que o
    ``DiscountModifier`` usa para DECIDIR o desconto. Quando a vitrine tinha a sua
    query e o carrinho a dele, a loja anunciava promoção de outro canal e a sacola
    cobrava o preço cheio.

    A presentation não pode importar ``shop.services`` (fronteira read/write, ver
    ``test_import_boundaries``), então a leitura passa por aqui — que é read-side.
    """
    from django.utils import timezone

    from shopman.shop.services import promotions as promotion_service

    return promotion_service.get_active_promotions(timezone.now(), channel_ref=channel_ref)


def contextual_price(
    sku: str,
    *,
    qty: Decimal | int = 1,
    listing_ref: str | None = None,
    context: dict | None = None,
    list_unit_price_q: int | None = None,
):
    from shopman.offerman.service import CatalogService

    return CatalogService.get_price(
        sku,
        qty=Decimal(str(qty)),
        listing=listing_ref,
        context=context,
        list_unit_price_q=list_unit_price_q,
    )


def expand_bundle(sku: str, qty: Decimal = Decimal("1")) -> list[dict]:
    from shopman.offerman.service import CatalogService

    return CatalogService.expand(sku, qty)


def _componentes_do_bundle(sku: str) -> list[dict]:
    """Componentes do bundle, ou lista vazia se o SKU for produto simples."""
    from shopman.offerman.exceptions import CatalogError
    from shopman.offerman.service import CatalogService

    try:
        return CatalogService.expand(sku, Decimal("1"))
    except CatalogError:
        return []


def availability_for_sku(
    sku: str,
    *,
    channel_ref: str,
    target_date: date | None = None,
) -> dict | None:
    try:
        from shopman.stockman.services.availability import availability_for_sku as _availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter
        from shopman.shop.services import waitlist

        scope = stock_adapter.get_channel_scope(channel_ref)
        explicit_target = target_date

        def leitura(um_sku: str, on_date: date) -> dict | None:
            return _availability_for_sku(
                um_sku,
                target_date=on_date,
                safety_margin=scope["safety_margin"],
                allowed_positions=scope["allowed_positions"],
                excluded_positions=scope.get("excluded_positions"),
                expiry_margin_days=scope.get("expiry_margin_days", 0),
                include_nonconforming=scope.get("sells_nonconforming", True),
                allowed_quality_grade_refs=scope.get("allowed_quality_grade_refs"),
            )

        def promessa(um_sku: str) -> dict | None:
            if explicit_target is not None:
                return leitura(um_sku, explicit_target)

            # O cardápio faz duas perguntas distintas: o que pode ser reservado
            # hoje e qual é a capacidade da PRIMEIRA fornada elegível. Somar o
            # horizonte inteiro produziria um teto que nenhum hold de data única
            # consegue honrar.
            from django.utils import timezone

            today = timezone.localdate()
            current = leitura(um_sku, today)
            if current is None:
                return current
            next_batch = waitlist.next_batch_availability(
                um_sku,
                channel_ref=channel_ref,
            )
            if next_batch is None:
                return current
            _target_date, future = next_batch
            return _merge_waitlist_availability(
                current,
                future,
            )

        # ⚠️ O stockman não sabe o que é bundle — ele conta quant por SKU, e
        # bundle não tem quant. Sem expandir aqui, TODO bundle lia zero: o combo
        # só não parecia quebrado porque a política `demand_ok` deixa pedir sem
        # estoque, o que mascarava o número. Pacote de pão não pode se apoiar
        # nisso: ele é limitado pelo pão que o compõe, e pão acaba todo dia.
        componentes = _componentes_do_bundle(sku)
        if not componentes:
            return promessa(sku)

        propria = promessa(sku) or {}
        possiveis: list[Decimal] = []
        prontos: list[Decimal] = []
        prontos_fisicos: list[Decimal] = []
        from django.utils import timezone

        component_target = explicit_target or timezone.localdate()
        for componente in componentes:
            # Bundle não tem Quant/fornada própria para ancorar um hold futuro.
            # Até existir uma promessa multi-componente de data comum, ele falha
            # fechado para o pronto da data pedida (hoje no catálogo sem target).
            parte = leitura(componente["sku"], component_target)
            if parte is None:
                return None
            por_pacote = Decimal(str(componente["qty"])) or Decimal("1")
            possiveis.append(
                Decimal(str(parte.get("total_promisable", 0))) // por_pacote
            )
            prontos.append(
                Decimal(str(parte.get("available", 0))) // por_pacote
            )
            prontos_fisicos.append(
                Decimal(str(parte.get("ready_physical", 0))) // por_pacote
            )
            propria.setdefault("availability_policy", parte.get("availability_policy"))
            if parte.get("is_paused"):
                propria["is_paused"] = True
            if parte.get("is_planned"):
                propria["is_planned"] = True
        propria["total_promisable"] = min(possiveis) if possiveis else Decimal("0")
        propria["available"] = min(prontos) if prontos else Decimal("0")
        propria["ready_physical"] = (
            min(prontos_fisicos) if prontos_fisicos else Decimal("0")
        )
        return propria
    except Exception as exc:
        logger.warning("availability_lookup_failed sku=%s channel=%s: %s", sku, channel_ref, exc, exc_info=True)
        return None


def availability_for_skus(
    skus: list[str],
    *,
    channel_ref: str,
    target_date: date | None = None,
) -> dict[str, dict | None]:
    if not skus:
        return {}
    if target_date is not None:
        try:
            from shopman.shop.services.availability import stock_on_dates

            return stock_on_dates(
                skus,
                [target_date],
                **_channel_scope_kwargs(channel_ref),
            )[target_date]
        except Exception as exc:
            logger.warning("batch_availability_failed channel=%s: %s", channel_ref, exc, exc_info=True)
            return {}
    return availability_and_today_for_skus(skus, channel_ref=channel_ref)[0]


def warm_availability_for_skus(skus: list[str], *, channel_ref: str) -> None:
    """Lê de uma vez, para o memo do request, o que vários chamadores vão pedir.

    A sacola lê as linhas dela e o trilho de sugestão lê os candidatos: dois
    conjuntos que não se cruzam, e cada leitura do Stockman tem um custo fixo
    de ~10 consultas. Quem já sabe os dois conjuntos chama isto com a união
    ANTES; depois cada chamador faz a própria pergunta, do jeito de sempre
    (:func:`availability_for_skus` com os seus SKUs, as suas datas candidatas
    da fila), e encontra tudo no memo.

    Nada é devolvido nem decidido aqui: é só leitura antecipada. Sem memo ativo
    (fora de GET, ou depois de uma escrita no request) não faz nada, para não
    pagar uma leitura que ninguém vai reaproveitar.
    """
    from shopman.shop import request_memo

    unique = list(dict.fromkeys(sku for sku in skus if sku))
    if not unique or not request_memo.stock_reads_active():
        return
    availability_and_today_for_skus(unique, channel_ref=channel_ref)


def _channel_scope_kwargs(channel_ref: str) -> dict:
    from shopman.shop.adapters import stock as stock_adapter

    scope = stock_adapter.get_channel_scope(channel_ref)
    return {
        "safety_margin": scope["safety_margin"],
        "allowed_positions": scope["allowed_positions"],
        "excluded_positions": scope.get("excluded_positions"),
        "expiry_margin_days": scope.get("expiry_margin_days", 0),
        "include_nonconforming": scope.get("sells_nonconforming", True),
        "allowed_quality_grade_refs": scope.get("allowed_quality_grade_refs"),
    }


def _same_scope_kwargs(left: dict, right: dict) -> bool:
    """Iguais em valor E em tipo: ``0`` e ``0.0`` somam diferente com ``Decimal``."""
    if left.keys() != right.keys():
        return False
    return all(
        type(left[key]) is type(right[key]) and left[key] == right[key]
        for key in left
    )


def availability_and_today_for_skus(
    skus: list[str],
    *,
    channel_ref: str,
    also_today: list[str] | tuple[str, ...] = (),
) -> tuple[dict[str, dict | None], dict[str, dict]]:
    """Disponibilidade do cardápio (hoje + fila de espera) e o pronto de HOJE cru.

    Devolve ``(disponibilidade, hoje)``:

    - ``disponibilidade`` é o que :func:`availability_for_skus` sem data
      devolve: a leitura de hoje, com a próxima fornada da fila de espera
      mesclada quando a fila está ligada;
    - ``hoje`` é a leitura crua do Stockman para hoje, de ``skus`` e de
      ``also_today`` — o que o bundle precisa dos componentes, sem pedir ao
      Stockman uma segunda vez.

    Hoje e as datas candidatas da fila saem de UMA leitura do Stockman
    (:func:`availability_for_skus_on_dates`), em vez de uma leitura inteira
    por data. As datas candidatas continuam sendo as dos ``skus`` do
    cardápio: ``also_today`` só pega carona na leitura de hoje.
    """
    if not skus:
        return {}, {}
    try:
        from django.utils import timezone

        from shopman.shop.services import waitlist
        from shopman.shop.services.availability import stock_on_dates

        kwargs = _channel_scope_kwargs(channel_ref)
        today = timezone.localdate()
        read_skus = list(dict.fromkeys([*skus, *(sku for sku in also_today if sku)]))

        combined = _read_today_and_next_batches(
            skus,
            read_skus,
            channel_ref=channel_ref,
            today=today,
            kwargs=kwargs,
        )
        if combined is not None:
            current, next_batches = combined
        else:
            current = stock_on_dates(read_skus, [today], **kwargs)[today]
            next_batches = waitlist.next_batch_availability_for_skus(
                skus,
                channel_ref=channel_ref,
            )
        today_raw = {sku: current[sku] for sku in read_skus}
        if not next_batches:
            return {sku: current[sku] for sku in skus}, today_raw
        return (
            {
                sku: _merge_waitlist_availability(
                    current.get(sku),
                    next_batches.get(sku, (None, None))[1],
                )
                for sku in skus
            },
            today_raw,
        )
    except Exception as exc:
        logger.warning("batch_availability_failed channel=%s: %s", channel_ref, exc, exc_info=True)
        return {}, {}


def _read_today_and_next_batches(
    skus: list[str],
    read_skus: list[str],
    *,
    channel_ref: str,
    today: date,
    kwargs: dict,
) -> tuple[dict[str, dict], dict[str, tuple[date, dict]]] | None:
    """Hoje e as fornadas candidatas da fila numa leitura só do Stockman.

    ``None`` manda o chamador pelo caminho de duas leituras (hoje e, à parte,
    ``waitlist.next_batch_availability_for_skus``), que é o comportamento de
    referência. Isso acontece quando a leitura única não é garantidamente a
    mesma pergunta: sem canal, com o recorte do canal diferente tipo a tipo do
    que a fila lê (ela normaliza para ``int``/``bool``), ou se a leitura das
    datas futuras falhar — a fila degrada sozinha para vazio, e o pronto de
    hoje não pode cair junto com ela.
    """
    from shopman.shop.services import waitlist
    from shopman.shop.services.availability import stock_on_dates

    if not channel_ref:
        return None
    candidates = waitlist.candidate_batch_dates(skus, channel_ref=channel_ref)
    if not candidates:
        # Fila desligada, ou nenhuma fornada no horizonte: não há o que mesclar.
        return stock_on_dates(read_skus, [today], **kwargs)[today], {}
    try:
        if not _same_scope_kwargs(waitlist.scope_kwargs(channel_ref), kwargs):
            return None
        by_date = stock_on_dates(read_skus, [today, *candidates], **kwargs)
        next_batches = waitlist.first_batch_with_planned(skus, candidates, by_date)
    except Exception:
        logger.debug("catalog_availability.single_read degraded; reading separately", exc_info=True)
        return None
    return by_date[today], next_batches


def _merge_waitlist_availability(
    current: dict | None,
    future: dict | None,
) -> dict | None:
    """Escolhe o maior teto integralmente reservável hoje ou na próxima fornada."""
    if current is None:
        return future
    if future is None:
        return current

    merged = dict(current)
    planned = Decimal(str(future.get("planned") or 0))
    current_promisable = Decimal(str(current.get("total_promisable") or 0))
    future_promisable = Decimal(str(future.get("total_promisable") or 0))
    policy = str(current.get("availability_policy") or "planned_ok")
    merged["planned"] = planned
    merged["is_planned"] = bool(future.get("is_planned"))
    merged["is_tracked"] = bool(
        current.get("is_tracked") or future.get("is_tracked")
    )
    if policy == "stock_only":
        merged["total_promisable"] = Decimal(str(current.get("available") or 0))
    else:
        # Cada hold carrega uma única target_date. O maior destes dois tetos é
        # reservável inteiro em uma data; a soma não é (pronto que vence hoje e
        # fornadas de dias diferentes não podem sustentar o mesmo hold).
        merged["total_promisable"] = max(current_promisable, future_promisable)
    breakdown = dict(current.get("breakdown") or {})
    breakdown["planned"] = planned
    merged["breakdown"] = breakdown
    return merged


def bundle_availability_from_components(
    component_entries: list[tuple[Decimal, dict | None]],
) -> dict | None:
    """Synthesize a bundle's raw availability from its components.

    Um bundle so pode ser montado tantas vezes quanto o seu componente MAIS
    escasso permite: ``min(floor(component_promisable / qty_por_bundle))``.
    Cada entrada e ``(qty_por_bundle, component_raw_avail)``.

    Regras (espelham ``basic_availability`` no nivel do componente):
    - componente sem dado de estoque (``None``) ou ``demand_ok`` → nao limita;
    - qualquer componente pausado → bundle pausado (nao ha como montar);
    - senao, o componente que rende menos bundles vira o gargalo, e seus flags
      (``is_planned``) definem se o zero-fisico e PLANNED_OK ou UNAVAILABLE.

    Retorna um dict no mesmo shape do stockman (para ``basic_availability`` /
    ``_resolve_availability`` resolverem sem caso especial), ou ``None`` quando
    nenhum componente limita o bundle (→ confia no flag do produto → available).
    """
    binding: tuple[int, dict] | None = None
    ready_limits: list[int] = []
    physical_limits: list[int] = []
    is_planned = False
    for qty_per_bundle, raw in component_entries:
        if qty_per_bundle is None or qty_per_bundle <= 0:
            continue
        if raw is None:
            continue  # componente sem tracking de estoque: nao e gargalo
        if raw.get("is_paused", False):
            return {
                "is_paused": True,
                "total_promisable": Decimal("0"),
                "available": Decimal("0"),
                "ready_physical": Decimal("0"),
            }
        if raw.get("availability_policy", "planned_ok") == "demand_ok":
            continue  # ilimitado: nao e gargalo
        is_planned = is_planned or bool(raw.get("is_planned", False))
        promisable = raw.get("total_promisable") or Decimal("0")
        if not isinstance(promisable, Decimal):
            promisable = Decimal(str(promisable))
        bundles = int(promisable // qty_per_bundle)
        ready_limits.append(
            int(Decimal(str(raw.get("available") or 0)) // qty_per_bundle)
        )
        physical_limits.append(
            int(Decimal(str(raw.get("ready_physical") or 0)) // qty_per_bundle)
        )
        if binding is None or bundles < binding[0]:
            binding = (bundles, raw)

    if binding is None:
        return None
    bundles, raw = binding
    return {
        "total_promisable": Decimal(bundles),
        "availability_policy": "planned_ok",
        "is_planned": is_planned,
        "is_paused": False,
        "available": Decimal(min(ready_limits)) if ready_limits else Decimal("0"),
        "ready_physical": (
            Decimal(min(physical_limits)) if physical_limits else Decimal("0")
        ),
    }


def bundle_components_for_skus(bundle_skus: list[str]) -> dict[str, list[dict]]:
    """Componentes de cada bundle (``expand_bundle``); falha de expansão vira lista vazia."""
    expanded: dict[str, list[dict]] = {}
    for sku in bundle_skus:
        try:
            components = expand_bundle(sku)
        except Exception:
            logger.warning("bundle_expand_failed sku=%s", sku, exc_info=True)
            components = []
        expanded[sku] = components
    return expanded


def bundle_component_skus(expanded: dict[str, list[dict]]) -> list[str]:
    """SKUs de componente de um ``bundle_components_for_skus``, ordenados e sem repetição."""
    return sorted(
        {
            str(c.get("sku") or "")
            for components in expanded.values()
            for c in components
            if c.get("sku")
        }
    )


def bundle_availability_for_skus(
    bundle_skus: list[str],
    *,
    channel_ref: str,
    expanded: dict[str, list[dict]] | None = None,
    today_availability: dict[str, dict] | None = None,
) -> dict[str, dict | None]:
    """Availability for bundle SKUs, derived from their components' stock.

    Um bundle nao tem quant proprio — sem isto o card resolveria para AVAILABLE
    (``raw_avail is None`` → "confia no flag"), mostrando "Disponivel" mesmo com
    um componente esgotado. Expande cada bundle, faz batch da disponibilidade dos
    componentes e sintetiza o raw via ``bundle_availability_from_components``.

    ``expanded`` (de :func:`bundle_components_for_skus`) e ``today_availability``
    (o pronto de hoje cru, de :func:`availability_and_today_for_skus`) deixam o
    cardápio reaproveitar o que já leu: componente que já está em
    ``today_availability`` não é lido de novo, e só o que falta vai ao Stockman.
    """
    if not bundle_skus:
        return {}
    if expanded is None:
        expanded = bundle_components_for_skus(bundle_skus)
    component_skus = bundle_component_skus(expanded)

    from django.utils import timezone

    known = today_availability or {}
    comp_avail: dict[str, dict | None] = {sku: known[sku] for sku in component_skus if sku in known}
    missing = [sku for sku in component_skus if sku not in known]
    if missing:
        comp_avail.update(
            availability_for_skus(
                missing,
                channel_ref=channel_ref,
                target_date=timezone.localdate(),
            )
        )

    result: dict[str, dict | None] = {}
    for sku, components in expanded.items():
        if not components:
            result[sku] = None
            continue
        entries = [
            (Decimal(str(c.get("qty") or 0)), comp_avail.get(str(c.get("sku") or "")))
            for c in components
        ]
        result[sku] = bundle_availability_from_components(entries)
    return result


def planned_supply_for_skus(skus: list[str], *, horizon_days: int = 2) -> dict[str, int]:
    """Suprimento planejado (fornadas futuras) por SKU até ``horizon_days`` dias.

    Produção planejada vira **quant com ``target_date`` futura** (o que ``craft.plan``
    materializa). Isto é uma consulta SEPARADA da disponibilidade-agora: aqui só o que
    está a caminho pela produção — sem contaminar ``sold_out`` com o que ainda não chegou.
    Batch, silencioso sem Stockman.
    """
    if not skus:
        return {}
    try:
        from datetime import timedelta

        from django.db.models import Sum
        from django.utils import timezone
        from shopman.stockman.models import Quant

        today = timezone.localdate()
        rows = (
            Quant.objects.filter(
                sku__in=skus,
                target_date__gt=today,
                target_date__lte=today + timedelta(days=max(horizon_days, 1)),
                _quantity__gt=0,
            )
            .values("sku")
            .annotate(total=Sum("_quantity"))
        )
        return {r["sku"]: int(r["total"] or 0) for r in rows}
    except Exception as exc:
        logger.warning("planned_supply_failed: %s", exc, exc_info=True)
        return {}


def availability_with_own_hold(raw_avail: dict | None, own_hold: int) -> dict | None:
    if raw_avail is None or own_hold <= 0:
        return raw_avail
    adjusted = dict(raw_avail)
    if adjusted.get("total_promisable") is not None:
        adjusted["total_promisable"] = Decimal(str(adjusted["total_promisable"])) + Decimal(own_hold)
    if adjusted.get("total_available") is not None:
        adjusted["total_available"] = Decimal(str(adjusted["total_available"])) + Decimal(own_hold)
    return adjusted


def own_holds_by_sku(session_key: str, skus: list[str]) -> dict[str, Decimal]:
    """This session's active hold quantity per SKU (read facade).

    Lets the storefront read paths (cart, PDP) tell "unavailable to the
    public" apart from "this session already holds all of it" without
    reaching into the write-side; delegates to the canonical availability
    read helper.
    """
    from shopman.shop.services import availability

    return availability.own_holds_by_sku(session_key, skus)


def basic_availability(
    raw_avail: dict | None,
    *,
    is_sellable: bool,
    low_stock_threshold: Decimal,
) -> BasicAvailability:
    if not is_sellable:
        return BasicAvailability("unavailable", 0, False)
    if raw_avail is None:
        return BasicAvailability("available", None, True)
    if raw_avail.get("is_paused", False):
        return BasicAvailability("unavailable", 0, False)

    policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable") or Decimal("0")
    if not isinstance(total_promisable, Decimal):
        total_promisable = Decimal(str(total_promisable))

    if policy == "demand_ok":
        return BasicAvailability("available", None, True)

    available_qty = int(total_promisable)
    if total_promisable <= 0:
        return BasicAvailability("unavailable", 0, False)

    ready_available = Decimal(
        str(raw_avail.get("available", raw_avail.get("ready_physical")) or 0)
    )
    if (
        policy == "planned_ok"
        and raw_avail.get("is_planned", False)
        and ready_available <= 0
    ):
        # A fila é limitada pela quantidade realmente planejada. ``is_planned``
        # sem saldo prometível não abre o stepper; com saldo, a apresentação
        # distingue a fornada futura de produto pronto na prateleira.
        return BasicAvailability("planned_ok", available_qty, True)

    if total_promisable <= low_stock_threshold:
        return BasicAvailability("low_stock", available_qty, True)

    return BasicAvailability("available", available_qty, True)


def storefront_availability(raw_avail: dict | None, *, is_sellable: bool) -> dict | None:
    if raw_avail is None:
        return None

    is_paused = raw_avail.get("is_paused", False) or not is_sellable
    policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable", Decimal("0"))
    can_order = ((policy == "demand_ok") or total_promisable > 0) and not is_paused
    had_stock = can_order or raw_avail.get("is_planned", False) or total_promisable > 0
    if can_order:
        state = "available"
    elif had_stock and not is_paused:
        state = "sold_out"
    else:
        state = "unavailable"
    return {
        "available_qty": total_promisable,
        "can_order": can_order,
        "is_paused": is_paused,
        "had_stock": had_stock,
        "state": state,
        "availability_policy": policy,
    }


def promisable_int(raw_avail: dict | None) -> int | None:
    if raw_avail is None:
        return None
    total = raw_avail.get("total_promisable")
    if total is None:
        return None
    try:
        return int(Decimal(str(total)))
    except (ValueError, ArithmeticError):
        return None


def orderable_ceiling(raw_avail: dict | None, *, can_add: bool) -> int | None:
    """Teto do stepper: quantas unidades ainda cabem, ou ``None`` (sem teto).

    ``None`` é "sem teto conhecido", e é a resposta certa para ``demand_ok`` (a
    promessa não é prateleira) e para pausado (a porta já fechou por outro eixo).
    Uma fornada planejada tem teto conhecido e deve expô-lo: é justamente quantas
    unidades ainda cabem na fila.

    Projetar ``0`` num item que PODE ser adicionado é o pior dos dois mundos: o
    "+" morre no primeiro toque com "Só temos 0 disponíveis" enquanto o selo ao
    lado promete a fornada. É a mesma armadilha que a sacola já corrigiu em
    ``cart._line_availability`` (WP-P2E F1); aqui ela sobrevivia no card e na
    PDP, que ainda liam ``total_promisable`` cru.
    """
    if raw_avail is None or raw_avail.get("is_paused", False):
        return None
    if raw_avail.get("availability_policy", "planned_ok") == "demand_ok":
        return None
    total = promisable_int(raw_avail)
    if total is None:
        return None
    return total


def product_tags(product) -> tuple[str, ...]:
    # Sorted for a deterministic order: tags are a search-only index (never a
    # price or badge), and taggit's default ``.all()`` order is the through-table
    # PK — which flips depending on whether ``keywords`` was prefetched and on the
    # order tags were first created. Sorting pins the output regardless.
    names = getattr(product, _TAG_NAMES_ATTR, None)
    if names is not None:
        return names
    try:
        return tuple(sorted(tag.name for tag in product.keywords.all()))
    except Exception:
        logger.debug("catalog_context.product_tags degraded; using fallback", exc_info=True)
        return ()


def nutrition_facts(product):
    from shopman.offerman.nutrition import NutritionFacts

    return NutritionFacts.from_dict(product.nutrition_facts or {})


def nutrient_label(field_name: str) -> str:
    from shopman.offerman.nutrition import NUTRIENT_LABELS_PT

    return NUTRIENT_LABELS_PT[field_name]


def visible_listing_items(listing_ref: str):
    from shopman.offerman.models import ListingItem

    return (
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            listing__is_active=True,
        )
        .select_related("listing", "product")
        .prefetch_related("product__keywords", "product__collection_items__collection")
        .order_by("product__sku", "min_qty")
    )


def listing_validity_q(prefix: str = "listing_items__listing__") -> models.Q:
    from django.utils import timezone

    today = timezone.localdate()
    return (
        models.Q(**{f"{prefix}valid_from__isnull": True}) | models.Q(**{f"{prefix}valid_from__lte": today})
    ) & (
        models.Q(**{f"{prefix}valid_until__isnull": True}) | models.Q(**{f"{prefix}valid_until__gte": today})
    )


def label_attributes_by_sku(products) -> dict[str, dict]:
    """Rotulagem de compra remota por SKU: alérgenos, dieta e porção.

    Existe aqui, e não no service, porque **presentation lê projection, nunca
    service** (é o contrato que `test_import_boundaries` guarda). O registro de
    atributos é escrita e política; o que a vitrine precisa é o lado de leitura.

    As chaves do retorno seguem em inglês — convenção da casa para contrato de
    projection. O ``ref`` do atributo é dado do tenant, em português.
    """
    from shopman.shop.services import attributes

    allergens = attributes.get_many(products, "alergenos")
    dietary = attributes.get_many(products, "dieta")
    serves = attributes.get_many(products, "porcoes")

    return {
        p.sku: {
            "allergens": tuple(str(a) for a in (allergens.get(p.sku) or []) if a),
            "dietary_info": tuple(str(d) for d in (dietary.get(p.sku) or []) if d),
            "serves": str(serves.get(p.sku) or "") or None,
        }
        for p in products
    }


def label_attributes(product) -> dict:
    """A rotulagem de UM produto — a forma singular de :func:`label_attributes_by_sku`."""
    return label_attributes_by_sku([product])[product.sku]
