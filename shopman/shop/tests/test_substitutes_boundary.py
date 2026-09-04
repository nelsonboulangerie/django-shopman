"""A fronteira do tenant sobre a similaridade do Core: doce não substitui salgado.

O Offerman sabe o que se PARECE com o quê (palavra-chave, coleção, gramatura,
preço de tabela). Quem decide o que a casa pode oferecer no lugar é o
orquestrador — e a fronteira que ele aplica é declarada em
``suggestion.substitute.must_match``, não escrita em código.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.shop.models import Channel, RuleConfig
from shopman.shop.services import attributes, substitutes

pytestmark = pytest.mark.django_db

CHANNEL = "web"


@pytest.fixture(autouse=True)
def _fresh_caches():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def loja():
    Channel.objects.get_or_create(ref=CHANNEL, defaults={"name": "Web"})
    return Listing.objects.create(ref=CHANNEL, name="Web", is_active=True)


def _product(sku, name, *, listing, sabor=None, price_q=1000):
    product = Product.objects.create(
        sku=sku, name=name, base_price_q=price_q,
        is_published=True, is_sellable=True, availability_policy="demand_ok",
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=price_q,
        is_published=True, is_sellable=True,
    )
    if sabor is not None:
        attributes.set(product, "sabor", sabor)
    return product


def _in(collection_ref, *products):
    collection, _ = Collection.objects.get_or_create(
        ref=collection_ref, defaults={"name": collection_ref},
    )
    for i, p in enumerate(products):
        CollectionItem.objects.create(
            collection=collection, product=p, sort_order=i, is_primary=True,
        )


def _find(sku):
    return [r["sku"] for r in substitutes.find(sku, qty=Decimal("1"), channel=CHANNEL)]


# --- a fronteira ------------------------------------------------------------


def test_a_sweet_is_not_replaced_by_a_savoury(loja):
    doce = _product("MAD", "Madeleine", listing=loja, sabor="doce")
    outro_doce = _product("FIN", "Financier", listing=loja, sabor="doce")
    salgado = _product("QQ", "Queijo quente", listing=loja, sabor="salgado")
    _in("doces", doce, outro_doce, salgado)

    found = _find("MAD")

    assert "FIN" in found
    assert "QQ" not in found, "salgado atravessou a fronteira do doce"


def test_absence_of_data_is_not_divergence(loja):
    """Produto sem sabor cadastrado NÃO perde o direito de substituir.

    Cortá-lo recriaria, uma camada acima, o defeito que o refino do Core acabou
    de remover: exigir um dado curado para o produto ter substituto.
    """
    doce = _product("MAD", "Madeleine", listing=loja, sabor="doce")
    sem_sabor = _product("SEM", "Sem sabor cadastrado", listing=loja)
    _in("doces", doce, sem_sabor)

    assert "SEM" in _find("MAD")


def test_a_reference_without_the_attribute_filters_nothing(loja):
    sem_sabor = _product("REF", "Referencia sem sabor", listing=loja)
    salgado = _product("QQ", "Queijo quente", listing=loja, sabor="salgado")
    _in("doces", sem_sabor, salgado)

    assert "QQ" in _find("REF")


# --- a regra manda ----------------------------------------------------------


def test_turning_the_rule_off_removes_the_boundary(loja):
    """A fronteira é configuração, não código."""
    RuleConfig.objects.filter(ref="suggestion.substitute").update(enabled=False)

    doce = _product("MAD", "Madeleine", listing=loja, sabor="doce")
    salgado = _product("QQ", "Queijo quente", listing=loja, sabor="salgado")
    _in("doces", doce, salgado)

    assert "QQ" in _find("MAD")


def test_the_rule_is_enabled_by_the_migration():
    """A 0030 cadastrou desligada; a 0031 liga, porque agora alguém a lê."""
    rule = RuleConfig.objects.get(ref="suggestion.substitute")
    assert rule.enabled is True


def test_an_empty_must_match_filters_nothing(loja):
    rule = RuleConfig.objects.get(ref="suggestion.substitute")
    rule.params = {**rule.params, "must_match": []}
    rule.save()

    doce = _product("MAD", "Madeleine", listing=loja, sabor="doce")
    salgado = _product("QQ", "Queijo quente", listing=loja, sabor="salgado")
    _in("doces", doce, salgado)

    assert "QQ" in _find("MAD")


def test_a_rule_naming_an_attribute_that_vanished_does_not_silence_substitutes(loja):
    """Atributo saiu do registro depois de a regra citá-lo.

    A regra perdeu o sentido; cortar por ela seria pior que não cortar — o
    cliente veria "sem substituto" por causa de uma configuração órfã.
    """
    from shopman.shop.models import AttributeDefinition

    AttributeDefinition.objects.filter(ref="sabor").update(is_active=False)
    attributes.invalidate_cache()

    doce = _product("MAD", "Madeleine", listing=loja)
    outro = _product("FIN", "Financier", listing=loja)
    _in("doces", doce, outro)

    assert "FIN" in _find("MAD")
