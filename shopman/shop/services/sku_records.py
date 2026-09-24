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

from dataclasses import dataclass

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


def stop_buying(sku: str):
    """Desliga a compra: o cadastro de compra fica inativo, não some.

    Custo, conversão e histórico de recebimento continuam lá; religar é
    ``ensure_purchase_record`` de novo.
    """
    from shopman.buyman.models import Material

    material = Material.objects.filter(sku=sku).first()
    if material is None or not material.is_active:
        return material
    material.is_active = False
    material.save(update_fields=["is_active", "updated_at"])
    return material


# ── Os papéis do SKU (selos derivados) ─────────────────────────────────────


@dataclass(frozen=True)
class SkuRoles:
    """O que um SKU é, derivado do que existe — nunca guardado à parte.

    - ``purchasable`` (Comprável): tem cadastro de compra ativo;
    - ``sellable`` (Vendável): tem cadastro de venda com a venda ligada;
    - ``produced`` (Produzido): tem ficha ativa que o produz;
    - ``used_in_recipe`` (Usado em receita): alguma ficha ativa o consome.
    """

    purchasable: bool = False
    sellable: bool = False
    produced: bool = False
    used_in_recipe: bool = False


def sku_roles_map(skus) -> dict[str, SkuRoles]:
    """Papéis de vários SKUs em quatro consultas, para listas."""
    from shopman.buyman.models import Material
    from shopman.craftsman.models import Recipe, RecipeItem
    from shopman.offerman.models import Product

    skus = [sku for sku in dict.fromkeys(skus) if sku]
    if not skus:
        return {}
    purchasable = set(Material.objects.filter(sku__in=skus, is_active=True).values_list("sku", flat=True))
    sellable = set(Product.objects.filter(sku__in=skus, is_sellable=True).values_list("sku", flat=True))
    produced = set(Recipe.objects.filter(output_sku__in=skus, is_active=True).values_list("output_sku", flat=True))
    used = set(
        RecipeItem.objects.filter(input_sku__in=skus, recipe__is_active=True).values_list("input_sku", flat=True)
    )
    return {
        sku: SkuRoles(
            purchasable=sku in purchasable,
            sellable=sku in sellable,
            produced=sku in produced,
            used_in_recipe=sku in used,
        )
        for sku in skus
    }


def sku_roles(sku: str) -> SkuRoles:
    return sku_roles_map([sku]).get(sku, SkuRoles())


# ── Onde a coisa vendida aparece ───────────────────────────────────────────

#: A listagem do balcão: todo vendável entra aqui.
POS_LISTING = "pdv"


def remote_listing_refs() -> tuple[str, ...]:
    """Canais onde o cliente compra de longe — só com foto (regra do #1056)."""
    from django.conf import settings

    return (getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web"), "whatsapp", "ifood")


def sync_sale_listings(product, price_q: int, *, reactivate: bool = False) -> tuple[list[str], list[str]]:
    """PDV sempre; canal remoto só com foto. Devolve ``(listados, deslistados)``.

    Sem foto, nenhum item fica em canal onde o cliente decide pela imagem: ele
    sai de lá. Com ``reactivate``, o item que já estava listado mas pausado
    volta a vender, com o preço dado — é o gesto de quem ligou a venda.
    """
    from shopman.offerman.models import Listing, ListingItem

    remote = remote_listing_refs()
    listings = {lst.ref: lst for lst in Listing.objects.filter(ref__in=(POS_LISTING, *remote))}
    if POS_LISTING not in listings:
        raise ValidationError("A listagem do PDV (`pdv`) não existe neste banco: onde a casa venderia?")
    wanted = [POS_LISTING] + ([ref for ref in remote if ref in listings] if product.image_url else [])
    listed: list[str] = []
    for ref in wanted:
        item, created = ListingItem.objects.get_or_create(
            listing=listings[ref], product=product,
            defaults={"price_q": price_q, "is_published": True, "is_sellable": True},
        )
        if created:
            listed.append(ref)
        elif reactivate and (not item.is_published or not item.is_sellable or item.price_q != price_q):
            item.is_published = True
            item.is_sellable = True
            item.price_q = price_q
            item.save()
            listed.append(ref)
    unlisted: list[str] = []
    if not product.image_url:
        removed = ListingItem.objects.filter(product=product, listing__ref__in=remote)
        unlisted = list(removed.values_list("listing__ref", flat=True))
        removed.delete()
    return listed, unlisted


# ── Ligar e desligar a venda ────────────────────────────────────────────────


def _sale_metadata(material) -> dict:
    """O que o cadastro de compra já sabe e o de venda precisa: marca, GTIN, NCM."""
    from shopman.offerman import ProductSocialAttributes, set_social_attributes

    source = material.metadata if isinstance(material.metadata, dict) else {}
    metadata: dict = {}
    brand = str(source.get("brand") or "").strip()
    gtin = str(source.get("gtin") or "").strip()
    if brand or gtin:
        metadata = set_social_attributes(metadata, ProductSocialAttributes(brand=brand, gtin=gtin))
    ncm = str(source.get("ncm") or "").strip()
    if ncm:
        metadata["fiscal"] = {"profile": "own_production", "ncm": ncm, "unit": "UN"}
    return metadata


def start_selling(material, *, price_q: int | None):
    """Liga a venda do SKU de ``material`` — 1 gesto, que pede só o preço.

    Cria o cadastro de venda com o mesmo SKU, copiando nome, unidade, validade,
    marca, GTIN, NCM e foto de referência do cadastro de compra — ou religa o
    que existia com a venda pausada. Entra no PDV; nos canais remotos só com
    foto. Nasce fora do catálogo publicado da loja (``is_published=False``):
    alérgenos, ingredientes e tabela nutricional são dado da embalagem, e
    publicar é passo do gestor depois dela.

    Recusa o SKU com ficha ativa: o que é produzido aqui se vende pelo
    catálogo, não nasce do Compras.
    """
    from shopman.offerman.models import AvailabilityPolicy, Collection, CollectionItem, Product

    if price_q is None or price_q <= 0:
        raise ValidationError({"price_q": "Informe o preço de venda para ligar a venda."})
    if is_produced_here(material.sku):
        raise ValidationError({
            "sku": f"{material.name} é produzido aqui: a venda dele é do catálogo, não do Compras."
        })

    product = Product.objects.filter(sku=material.sku).first()
    if product is None:
        source = material.metadata if isinstance(material.metadata, dict) else {}
        product = Product(
            sku=material.sku,
            name=material.name,
            unit=material.unit,
            shelf_life_days=material.shelf_life_days,
            base_price_q=price_q,
            is_published=False,
            is_sellable=True,
            availability_policy=AvailabilityPolicy.PLANNED_OK,
            image_url=str(source.get("image_url") or "").strip(),
            metadata=_sale_metadata(material),
        )
        product.full_clean()
        product.save()
        collection = Collection.objects.filter(ref="mercearia").first()
        if collection is not None and not CollectionItem.objects.filter(product=product).exists():
            last = CollectionItem.objects.filter(collection=collection).order_by("-sort_order").first()
            CollectionItem.objects.create(
                collection=collection, product=product, is_primary=True,
                sort_order=(last.sort_order + 1) if last else 0,
            )
    else:
        product.is_sellable = True
        product.base_price_q = price_q
        product.save()
    sync_sale_listings(product, price_q, reactivate=True)
    return product


def stop_selling(sku: str):
    """Desliga a venda: pausa e deslista. Não apaga — o histórico de venda fica."""
    from shopman.offerman.models import ListingItem, Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        return None
    ListingItem.objects.filter(product=product).update(is_published=False, is_sellable=False)
    product.is_sellable = False
    product.save()
    return product

