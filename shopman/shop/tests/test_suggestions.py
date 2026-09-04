"""O motor de sugestão: portões, pesos, regras configuráveis e `reasons`.

O teste que fecha o gate do WP está no fim: **a sacola do piloto** (2 Baguette
de Tradition + 1 Shokupan) tem de receber café ou acompanhamento, e nunca a
Água — que é o que a regra antiga ofereceu, por ser a mais popular.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import ProductAffinity, RuleConfig
from shopman.shop.projections.suggestions import COMPLEMENT, suggest
from shopman.shop.rules.suggestion import ComplementRule, SuggestionRuleError
from shopman.shop.services import attributes

pytestmark = pytest.mark.django_db

CHANNEL = "loja"


@pytest.fixture(autouse=True)
def _fresh_caches():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def listing():
    return Listing.objects.create(ref=CHANNEL, name="Loja", is_active=True)


def _product(sku, name, *, price_q=1000, listing=None, **attrs):
    product = Product.objects.create(
        sku=sku, name=name, base_price_q=price_q, is_published=True, is_sellable=True,
        # Sempre adicionável: estes testes são sobre a ESCOLHA da sugestão. Que
        # o portão de disponibilidade recusa esgotado tem teste próprio, em
        # test_projections_cart.py::test_upsell_never_suggests_what_cannot_be_added.
        availability_policy="demand_ok",
    )
    if listing is not None:
        ListingItem.objects.create(
            listing=listing, product=product, price_q=price_q,
            is_published=True, is_sellable=True,
        )
    for ref, value in attrs.items():
        attributes.set(product, ref, value)
    return product


def _affinity(a, b, lift, *, count=10):
    for x, y in ((a, b), (b, a)):
        ProductAffinity.objects.create(
            sku_a=x, sku_b=y, together_count=count, score=float(count),
            lift=lift, window_days=365, computed_at=timezone.now(),
        )


def _rule(params, *, ref="suggestion.complement"):
    return RuleConfig.objects.create(
        ref=ref, label="Adicional",
        rule_path="shopman.shop.rules.suggestion.ComplementRule",
        params=params, enabled=True,
    )


# --- portões ----------------------------------------------------------------


def test_an_item_already_in_the_cart_is_not_suggested(listing):
    _product("PAO", "Pão", listing=listing)
    _product("CAFE", "Café", listing=listing)
    _affinity("PAO", "CAFE", 3.0)

    found = suggest(COMPLEMENT, cart_skus={"PAO", "CAFE"}, channel_ref=CHANNEL)
    assert found == ()


def test_an_unpublished_product_is_not_suggested(listing):
    _product("PAO", "Pão", listing=listing)
    cafe = _product("CAFE", "Café", listing=listing)
    Product.objects.filter(pk=cafe.pk).update(is_published=False)
    _affinity("PAO", "CAFE", 3.0)

    assert suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL) == ()


def test_a_product_outside_the_channel_listing_is_not_suggested(listing):
    _product("PAO", "Pão", listing=listing)
    _product("CAFE", "Café")  # sem ListingItem: não aparece neste canal
    _affinity("PAO", "CAFE", 3.0)

    assert suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL) == ()


def test_an_empty_cart_has_nothing_to_pair_with(listing):
    _product("CAFE", "Café", listing=listing)
    assert suggest(COMPLEMENT, cart_skus=set(), channel_ref=CHANNEL) == ()


# --- regra em branco --------------------------------------------------------


def test_with_no_rule_the_engine_still_runs_on_co_occurrence(listing):
    """Regra em branco não quebra nada — é o contrato do WP."""
    _product("PAO", "Pão", listing=listing)
    _product("CAFE", "Café", listing=listing)
    _affinity("PAO", "CAFE", 4.0)

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)

    assert [s.sku for s in found] == ["CAFE"]
    assert found[0].reasons == ("affinity:PAO",)


def test_without_a_reason_nothing_is_suggested(listing):
    """Item de catálogo sem afinidade e sem pareamento não é sugestão.

    Sem isto, o motor devolveria o primeiro SKU em ordem alfabética — que é
    exatamente o tipo de "sugestão" que não significa nada.
    """
    _product("PAO", "Pão", listing=listing)
    _product("ALGO", "Algo", listing=listing)
    _rule({"pairings": [], "affinity_weight": 3})

    assert suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL) == ()


# --- pareamentos configuráveis ---------------------------------------------


def test_a_pairing_suggests_a_product_with_no_history_at_all(listing):
    """Produto novo não tem cesta, e mesmo assim precisa poder ser sugerido."""
    _product("PAO", "Pão", listing=listing, natureza="comida")
    _product("MANTEIGA", "Manteiga", listing=listing, natureza="acompanhamento")
    _rule({"pairings": [{
        "when": {"attr": "natureza", "value": "comida"},
        "suggest": {"attr": "natureza", "in": ["acompanhamento", "bebida"]},
        "weight": 3,
    }]})

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)

    assert [s.sku for s in found] == ["MANTEIGA"]
    assert found[0].reasons == ("pairing:natureza=comida→natureza=acompanhamento",)


def test_a_pairing_can_point_at_a_keyword(listing):
    _product("MAD", "Madeleine", listing=listing, sabor="doce")
    cafe = _product("CAFE", "Café", listing=listing)
    cafe.keywords.add("café")
    _rule({"pairings": [
        {"when": {"attr": "sabor", "value": "doce"}, "suggest": {"tag": "café"}, "weight": 2},
    ]})

    found = suggest(COMPLEMENT, cart_skus={"MAD"}, channel_ref=CHANNEL)

    assert [s.sku for s in found] == ["CAFE"]
    assert found[0].reasons == ("pairing:sabor=doce→tag:café",)


def test_the_hot_to_cold_pairing_the_owner_asked_for(listing):
    _product("CAFE", "Café", listing=listing, temperatura="quente")
    _product("SUCO", "Suco gelado", listing=listing, temperatura="gelado")
    _rule({"pairings": [
        {"when": {"attr": "temperatura", "value": "quente"},
         "suggest": {"attr": "temperatura", "value": "gelado"}, "weight": 2},
    ]})

    found = suggest(COMPLEMENT, cart_skus={"CAFE"}, channel_ref=CHANNEL)
    assert [s.sku for s in found] == ["SUCO"]


def test_a_heavier_pairing_outranks_a_lighter_one(listing):
    _product("PAO", "Pão", listing=listing, natureza="comida", sabor="neutro")
    _product("MANTEIGA", "Manteiga", listing=listing, natureza="acompanhamento")
    _product("AGUA", "Água", listing=listing, natureza="bebida")
    _rule({"pairings": [
        {"when": {"attr": "natureza", "value": "comida"},
         "suggest": {"attr": "natureza", "value": "acompanhamento"}, "weight": 5},
        {"when": {"attr": "natureza", "value": "comida"},
         "suggest": {"attr": "natureza", "value": "bebida"}, "weight": 1},
    ]})

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL, limit=2)
    assert [s.sku for s in found] == ["MANTEIGA", "AGUA"]


# --- contexto é portão, preço é preferência --------------------------------


def test_context_excludes_a_cold_item_from_a_delivery(listing):
    _product("PAO", "Pão", listing=listing, natureza="comida")
    _product("SORVETE", "Sorvete", listing=listing, natureza="comida", temperatura="gelado")
    _affinity("PAO", "SORVETE", 5.0)
    _rule({
        "affinity_weight": 3,
        "context": {"delivery": {"exclude": {"attr": "temperatura", "value": "gelado"}}},
    })

    assert suggest(
        COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL,
        context={"fulfillment": "delivery"},
    ) == ()
    # Sem contexto de entrega, a mesma sugestão sai normalmente.
    assert suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL) != ()


def test_price_is_a_preference_and_never_silences_a_suggestion(listing):
    """Preço não é portão: um filtro duro calaria a sugestão numa sacola barata."""
    _product("PAO", "Pão", price_q=500, listing=listing)
    _product("CAVIAR", "Caviar", price_q=90000, listing=listing)
    _affinity("PAO", "CAVIAR", 4.0)
    _rule({"affinity_weight": 3, "price": "below_cart_average"})

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)

    assert [s.sku for s in found] == ["CAVIAR"]
    assert "price:below_cart_average" not in found[0].reasons


def test_a_cheaper_item_earns_the_price_reason(listing):
    _product("PAO", "Pão", price_q=2000, listing=listing)
    _product("CAFE", "Café", price_q=500, listing=listing)
    _affinity("PAO", "CAFE", 4.0)
    _rule({"affinity_weight": 3, "price": "below_cart_average"})

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)
    assert "price:below_cart_average" in found[0].reasons


# --- por superfície ---------------------------------------------------------


def test_each_surface_gets_its_own_limit(listing):
    _product("PAO", "Pão", listing=listing, natureza="comida")
    for i in range(3):
        _product(f"B{i}", f"Bebida {i}", listing=listing, natureza="bebida")
    _rule({
        "pairings": [{
            "when": {"attr": "natureza", "value": "comida"},
            "suggest": {"attr": "natureza", "value": "bebida"}, "weight": 2,
        }],
        "per_surface": {"web": 1, "concierge": 2},
    })

    assert len(suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL, surface="web")) == 1
    assert len(
        suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL, surface="concierge")
    ) == 2


# --- validação da regra -----------------------------------------------------


def test_a_rule_citing_an_attribute_that_does_not_exist_is_refused():
    with pytest.raises(SuggestionRuleError, match="sabour"):
        ComplementRule.validate_params({"pairings": [
            {"when": {"attr": "sabour", "value": "doce"},
             "suggest": {"attr": "natureza", "value": "bebida"}},
        ]})


def test_a_rule_citing_an_option_that_does_not_exist_is_refused():
    with pytest.raises(SuggestionRuleError, match="azedo"):
        ComplementRule.validate_params({"pairings": [
            {"when": {"attr": "sabor", "value": "azedo"},
             "suggest": {"attr": "natureza", "value": "bebida"}},
        ]})


def test_a_key_outside_the_schema_is_refused():
    # O limite existe para o Admin não virar editor de fluxo.
    with pytest.raises(SuggestionRuleError, match="fluxo_maluco"):
        ComplementRule.validate_params({"fluxo_maluco": True})


def test_the_admin_refuses_to_save_a_broken_rule():
    """A recusa tem de acontecer no save, não no dia em que a regra não casar."""
    with pytest.raises(ValidationError) as exc:
        _rule({"pairings": [
            {"when": {"attr": "sabor", "value": "azedo"},
             "suggest": {"attr": "natureza", "value": "bebida"}},
        ]})
    assert "params" in exc.value.message_dict


def test_a_valid_rule_saves():
    rule = _rule({"pairings": [
        {"when": {"attr": "sabor", "value": "doce"}, "suggest": {"tag": "café"}, "weight": 2},
    ]})
    assert rule.pk is not None


def test_the_substitute_rule_schema_is_validated():
    from shopman.shop.rules.suggestion import SubstituteRule

    SubstituteRule.validate_params({
        "must_match": ["sabor"], "prefer": ["collection"],
        "approximate": ["peso_unidade_g"], "price_band": 0.30,
        "cross_collection_when_empty": True,
    })
    with pytest.raises(SuggestionRuleError, match="price_band"):
        SubstituteRule.validate_params({"price_band": 3})


# --- objetivos --------------------------------------------------------------


def test_substitute_says_it_is_not_here_yet_instead_of_lying():
    # Devolver vazio diria "não há substituto", que é falso.
    with pytest.raises(NotImplementedError, match="F2"):
        suggest("substitute", cart_skus=set(), channel_ref=CHANNEL)


def test_an_unknown_objective_is_refused():
    with pytest.raises(ValueError, match="Objetivo desconhecido"):
        suggest("astrologia", cart_skus=set(), channel_ref=CHANNEL)


# --- O GATE DO WP -----------------------------------------------------------


def test_the_pilot_cart_gets_coffee_and_never_water(listing):
    """A sacola do piloto: 2 Baguette de Tradition + 1 Shokupan.

    Foi ela que recebeu **Água** da regra antiga ("o item mais popular que não
    está na sacola"), e foi essa oferta que originou o WP. A água é o item mais
    vendido da casa; oferecê-la a quem leva pão não é sugestão, é estatística
    mal lida.

    Aqui os dois sinais empurram na mesma direção: o histórico diz que quem
    leva pão leva café, e o pareamento diz que comida pede acompanhamento ou
    bebida. A água passa nos portões — está publicada, listada e disponível — e
    mesmo assim não ganha, porque nada a associa a pão além da popularidade,
    que este motor não lê.
    """
    _product("BAG", "Baguette de Tradition", price_q=1400, listing=listing,
             natureza="comida", sabor="neutro")
    _product("SHOKU", "Shokupan", price_q=2600, listing=listing,
             natureza="comida", sabor="neutro")
    _product("CAFE", "Café coado", price_q=700, listing=listing,
             natureza="bebida", temperatura="quente")
    _product("MANTEIGA", "Manteiga da casa", price_q=1800, listing=listing,
             natureza="acompanhamento")
    agua = _product("AGUA", "Água mineral", price_q=500, listing=listing,
                    natureza="bebida", temperatura="gelado")

    # O histórico: pão e café andam juntos. A água aparece com todo mundo, e
    # por isso o lift dela fica no acaso.
    _affinity("BAG", "CAFE", 3.4, count=180)
    _affinity("BAG", "AGUA", 1.02, count=140)
    _affinity("SHOKU", "AGUA", 1.01, count=60)

    _rule({
        "pairings": [
            {"when": {"attr": "natureza", "value": "comida"},
             "suggest": {"attr": "natureza", "in": ["acompanhamento", "bebida"]},
             "weight": 3},
        ],
        "affinity_weight": 3,
        "price": "below_cart_average",
        "per_surface": {"web": 1, "concierge": 1},
    })

    found = suggest(
        COMPLEMENT, cart_skus={"BAG", "SHOKU"}, channel_ref=CHANNEL, limit=3,
    )
    skus = [s.sku for s in found]

    assert skus, "a sacola do piloto tem de receber alguma sugestão"
    assert skus[0] in {"CAFE", "MANTEIGA"}, (
        f"esperava café ou acompanhamento no topo, veio {skus[0]}"
    )
    assert skus[0] != agua.sku, "a Água de novo não"

    # E a sugestão diz POR QUE saiu — é o que torna o ajuste no Admin mensurável.
    assert found[0].reasons
    assert any(r.startswith(("affinity:", "pairing:")) for r in found[0].reasons)


def test_the_pilot_cart_still_works_with_no_rule_at_all(listing):
    """O mesmo resultado sem regra cadastrada: a co-ocorrência sozinha basta."""
    _product("BAG", "Baguette de Tradition", price_q=1400, listing=listing)
    _product("SHOKU", "Shokupan", price_q=2600, listing=listing)
    _product("CAFE", "Café coado", price_q=700, listing=listing)
    _product("AGUA", "Água mineral", price_q=500, listing=listing)

    _affinity("BAG", "CAFE", 3.4, count=180)
    _affinity("BAG", "AGUA", 1.02, count=140)

    found = suggest(COMPLEMENT, cart_skus={"BAG", "SHOKU"}, channel_ref=CHANNEL)
    assert [s.sku for s in found] == ["CAFE"]
