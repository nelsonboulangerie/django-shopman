"""O motor de sugestão: portões, pesos, regras configuráveis e `reasons`.

O teste que fecha o gate do WP está no fim: **a sacola do piloto** (2 Baguette
de Tradition + 1 Shokupan) tem de receber café ou acompanhamento, e nunca a
Água — que é o que a regra antiga ofereceu, por ser a mais popular.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

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
    """Reescreve a regra que a migração já cadastrou.

    ``update_or_create`` e não ``create``: os defaults do dono nascem com o
    deploy (migração 0030), então todo teste começa com a regra real no banco —
    que é o estado de produção, e o certo para testar contra.
    """
    rule, _ = RuleConfig.objects.update_or_create(
        ref=ref,
        defaults={
            "label": "Adicional",
            "rule_path": "shopman.shop.rules.suggestion.ComplementRule",
            "params": params,
            "enabled": True,
        },
    )
    return rule


def _no_rule():
    """Desliga a regra seedada — o cenário "regra em branco" do contrato."""
    RuleConfig.objects.filter(ref="suggestion.complement").update(enabled=False)


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
    _no_rule()
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
        RuleConfig.objects.create(
            ref="suggestion.complement.teste", label="Adicional",
            rule_path="shopman.shop.rules.suggestion.ComplementRule",
            params={"pairings": [
                {"when": {"attr": "sabor", "value": "azedo"},
                 "suggest": {"attr": "natureza", "value": "bebida"}},
            ]},
        )
    assert "params" in exc.value.message_dict


def test_a_valid_rule_saves():
    rule = RuleConfig.objects.create(
        ref="suggestion.complement.teste", label="Adicional",
        rule_path="shopman.shop.rules.suggestion.ComplementRule",
        params={"pairings": [
            {"when": {"attr": "sabor", "value": "doce"}, "suggest": {"tag": "café"}, "weight": 2},
        ]},
    )
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
    _no_rule()
    _product("BAG", "Baguette de Tradition", price_q=1400, listing=listing)
    _product("SHOKU", "Shokupan", price_q=2600, listing=listing)
    _product("CAFE", "Café coado", price_q=700, listing=listing)
    _product("AGUA", "Água mineral", price_q=500, listing=listing)

    _affinity("BAG", "CAFE", 3.4, count=180)
    _affinity("BAG", "AGUA", 1.02, count=140)

    found = suggest(COMPLEMENT, cart_skus={"BAG", "SHOKU"}, channel_ref=CHANNEL)
    assert [s.sku for s in found] == ["CAFE"]


# --- os defaults que a migração cadastra ------------------------------------


def test_the_owner_defaults_are_seeded_and_valid():
    """As duas regras nascem com o deploy, e a validação as aceita.

    Regra seedada que não passa na própria validação seria pior que regra
    nenhuma: ela carrega, não casa nunca, e ninguém descobre.
    """
    from shopman.shop.rules.suggestion import ComplementRule, SubstituteRule

    complement = RuleConfig.objects.get(ref="suggestion.complement")
    substitute = RuleConfig.objects.get(ref="suggestion.substitute")

    assert complement.enabled is True
    # Nasceu desligada na 0030 (o motor de substituto era da F2) e foi LIGADA
    # pela 0031, quando `shop/services/substitutes.find` passou a ler o
    # `must_match`. Regra ligada que ninguém lê é ruído; fronteira declarada que
    # o sistema ignora é pior.
    assert substitute.enabled is True

    ComplementRule.validate_params(complement.params)
    SubstituteRule.validate_params(substitute.params)


def test_the_seeded_pairings_are_the_ones_the_owner_dictated():
    """Os critérios do dono (23/09), lidos na regra que o deploy deixa no banco.

    O comportamento é provado em `test_suggestion_stress.py`; aqui só se
    confere que a regra viva carrega as decisões — e não as que ele desfez.
    """
    params = RuleConfig.objects.get(ref="suggestion.complement").params

    def side(value):
        items = value if isinstance(value, list) else [value]
        return {(c.get("attr") or "tag", c.get("value") or c.get("tag")) for c in items}

    rules = [
        (side(p["when"]), side(p.get("when_absent") or []), side(p["suggest"]), p["weight"])
        for p in params["pairings"]
    ]
    no_drink = {("natureza", "bebida")}
    no_food = {("natureza", "comida")}

    # A frente é bebida ↔ comida, e vale mais que qualquer preferência.
    assert ({("natureza", "comida")}, no_drink, {("natureza", "bebida")}, 3) in rules
    assert ({("natureza", "bebida")}, no_food, {("natureza", "comida")}, 3) in rules
    # As preferências dele: somam, não filtram.
    assert ({("sabor", "salgado")}, no_drink,
            {("natureza", "bebida"), ("temperatura", "gelado")}, 2) in rules
    assert ({("sabor", "doce")}, no_drink,
            {("natureza", "bebida"), ("temperatura", "quente")}, 2) in rules
    # "Se já tem salgado e já tem bebida, oferece um doce, claro!"
    assert ({("sabor", "salgado"), ("natureza", "bebida")}, set(), {("sabor", "doce")}, 3) in rules
    # O que ele desfez: quente → gelado (bebida com bebida) e doce → tag café.
    assert not any(s == {("temperatura", "gelado")} for _, _, s, _ in rules)
    assert not any(("tag", "café") in s for _, _, s, _ in rules)

    assert params["one_per_cart"] == [{"attr": "natureza", "value": "bebida"}]
    assert params["distinct_from_cart"] == ["natureza", "sabor"]
    assert params["affinity_weight"] == 3
    assert params["price"] == "below_cart_average"


def test_the_migration_and_the_seed_agree_on_the_defaults():
    """Os defaults existem em DOIS lugares, e não podem divergir.

    A migração 0030 guarda uma cópia congelada — é o que toda migração deve
    fazer, porque ela representa um momento do banco e não pode mudar de
    sentido quando o código muda. O `seed --flush` usa as constantes vivas,
    porque `_flush` apaga toda `RuleConfig` e precisa reconstruí-las.

    Se alguém mudar as constantes sem escrever uma migração nova, é aqui que
    fica vermelho — e a mensagem diz o que fazer.
    """
    from shopman.shop.rules.suggestion import (
        DEFAULT_COMPLEMENT_PARAMS,
        DEFAULT_SUBSTITUTE_PARAMS,
    )

    complement = RuleConfig.objects.get(ref="suggestion.complement")
    substitute = RuleConfig.objects.get(ref="suggestion.substitute")

    assert complement.params == DEFAULT_COMPLEMENT_PARAMS, (
        "os defaults vivos mudaram e a migração ficou para trás — "
        "escreva uma migração de dados nova (o banco no ar não re-roda a 0030)"
    )
    assert substitute.params == DEFAULT_SUBSTITUTE_PARAMS


def test_the_seeded_rule_offers_a_drink_to_someone_carrying_bread(listing):
    """Ponta a ponta com a regra REAL: sem afinidade nenhuma, só o pareamento."""
    _product("PAO", "Pão", listing=listing, natureza="comida", sabor="neutro")
    _product("CAFE", "Café", listing=listing, natureza="bebida", temperatura="quente")

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)

    assert [s.sku for s in found] == ["CAFE"]
    assert found[0].reasons == ("pairing:natureza=comida→natureza=bebida",)


# --- adicional é complemento, não substituto (dono, 23/09) -----------------


def _in_collection(product, ref):
    collection, _ = Collection.objects.get_or_create(ref=ref, defaults={"name": ref})
    CollectionItem.objects.create(collection=collection, product=product, is_primary=True)
    return product


def _croque_menu(listing):
    """O cardápio do caso real, com os atributos que o `propose_product_attributes`
    deriva das coleções (salgados → comida/salgado/quente)."""
    madame = _in_collection(_product(
        "CQMA", "Croque Madame", price_q=2800, listing=listing,
        natureza="comida", sabor="salgado", temperatura="quente",
    ), "salgados")
    monsieur = _in_collection(_product(
        "CQMO", "Croque Monsieur", price_q=2400, listing=listing,
        natureza="comida", sabor="salgado", temperatura="quente",
    ), "salgados")
    complet = _in_collection(_product(
        "CQCOM", "Croque Complet", price_q=3000, listing=listing,
        natureza="comida", sabor="salgado", temperatura="quente",
    ), "salgados")
    suco = _in_collection(_product(
        "SUCO", "Suco de laranja", price_q=1200, listing=listing,
        natureza="bebida", temperatura="gelado",
    ), "bebidas-geladas")
    cafe = _in_collection(_product(
        "CAFE", "Café coado", price_q=700, listing=listing,
        natureza="bebida", temperatura="quente",
    ), "bebidas-quentes")
    return madame, monsieur, complet, suco, cafe


def test_a_croque_in_the_cart_gets_a_drink_and_never_another_croque(listing):
    """O caso do dono: 2 Croque Madame na sacola sugeriram Croque Monsieur.

    Com a regra REAL (a da migração) e o histórico do jeito que ele é: quem
    pede um croque para a mesa pede o outro, então o lift do par é alto — mais
    alto que o da bebida. Mesmo assim o croque não é adicional: é o mesmo
    prato, da mesma coleção. O que se oferece junto de um prato é a bebida.
    """
    _croque_menu(listing)
    _affinity("CQMA", "CQMO", 9.0, count=40)
    _affinity("CQMA", "CQCOM", 6.0, count=25)
    _affinity("CQMA", "SUCO", 1.4, count=30)

    found = suggest(COMPLEMENT, cart_skus={"CQMA"}, channel_ref=CHANNEL, limit=5)
    skus = [s.sku for s in found]

    assert skus, "a sacola com croque tem de receber alguma sugestão"
    assert skus[0] in {"SUCO", "CAFE"}, f"esperava uma bebida no topo, veio {skus}"
    assert not {"CQMO", "CQCOM"} & set(skus), f"croque sugerindo croque: {skus}"
    # A gelada ganha: comida → bebida (3) e quente → gelado (2), e o histórico
    # a confirma.
    assert skus[0] == "SUCO"
    assert "pairing:natureza=comida→natureza=bebida" in found[0].reasons


def test_a_bebida_without_any_history_still_reaches_the_croque(listing):
    """O pareamento acha a bebida mesmo quando a afinidade enche a fila.

    Antes o pareamento só avaliava a vaga que a afinidade deixasse, e em ordem
    alfabética de SKU — com 40 parceiros no histórico, a bebida nunca era vista.
    """
    _croque_menu(listing)
    for i in range(60):
        _product(f"A{i:02d}", f"Parceiro {i}", listing=listing)
        _affinity("CQMA", f"A{i:02d}", 1.5, count=5)

    found = suggest(COMPLEMENT, cart_skus={"CQMA"}, channel_ref=CHANNEL)
    assert [s.sku for s in found] == ["SUCO"]


def test_same_role_is_excluded_even_across_collections(listing):
    """Pão rústico e pão macio moram em coleções diferentes e são o mesmo papel."""
    _in_collection(_product("BAG", "Baguete", listing=listing,
                            natureza="comida", sabor="neutro"), "rusticos")
    _in_collection(_product("BRIOCHE", "Pão de forma", listing=listing,
                            natureza="comida", sabor="neutro"), "macios")
    _affinity("BAG", "BRIOCHE", 8.0)

    assert suggest(COMPLEMENT, cart_skus={"BAG"}, channel_ref=CHANNEL) == ()


def test_missing_attributes_never_exclude_by_themselves(listing):
    """Atributo em branco é ausência de dado, não igualdade."""
    _no_rule()
    _product("PAO", "Pão", listing=listing)
    _product("CAFE", "Café", listing=listing)
    _affinity("PAO", "CAFE", 4.0)
    _rule({"affinity_weight": 3, "distinct_from_cart": ["natureza", "sabor"]})

    assert [s.sku for s in suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)] == ["CAFE"]


def test_a_pairing_outranks_affinity_alone(listing):
    """O pareamento é a regra da casa; a afinidade ordena dentro dele."""
    _product("PAO", "Pão", listing=listing, natureza="comida", sabor="neutro")
    _product("DOCE", "Bolo", listing=listing, natureza="comida", sabor="doce")
    _product("CAFE", "Café", listing=listing, natureza="bebida", temperatura="quente")
    _affinity("PAO", "DOCE", 12.0)
    _affinity("PAO", "CAFE", 1.2)
    _rule({
        "pairings": [{
            "when": {"attr": "natureza", "value": "comida"},
            "suggest": {"attr": "natureza", "value": "bebida"}, "weight": 3,
        }],
        "affinity_weight": 3,
    })

    found = suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL, limit=2)
    assert [s.sku for s in found] == ["CAFE", "DOCE"]


def test_being_cheaper_is_not_a_reason_by_itself(listing):
    """Preço é preferência: sozinho, faria de todo item mais barato uma sugestão."""
    _product("CQMA", "Croque Madame", price_q=2800, listing=listing, sabor="salgado")
    _product("PAOZINHO", "Pãozinho", price_q=300, listing=listing)
    # Um pareamento que não casa com nada: antes, só por existir, ele abria a
    # fila para o catálogo inteiro, e o "mais barato" virava motivo sozinho.
    _rule({
        "pairings": [
            {"when": {"attr": "sabor", "value": "doce"}, "suggest": {"tag": "café"}, "weight": 2},
        ],
        "price": "below_cart_average",
    })

    assert suggest(COMPLEMENT, cart_skus={"CQMA"}, channel_ref=CHANNEL) == ()


def test_the_seeded_rule_offers_something_sweet_to_someone_carrying_coffee(listing):
    """O espelho de "doce pede café", com a regra REAL."""
    _in_collection(_product("CAFE", "Café", listing=listing,
                            natureza="bebida", temperatura="quente"), "bebidas-quentes")
    _in_collection(_product("CAPPU", "Cappuccino", listing=listing,
                            natureza="bebida", temperatura="quente"), "bebidas-quentes")
    _in_collection(_product("MAD", "Madeleine", listing=listing,
                            natureza="comida", sabor="doce"), "doces")
    _affinity("CAFE", "CAPPU", 5.0)

    found = suggest(COMPLEMENT, cart_skus={"CAFE"}, channel_ref=CHANNEL, limit=3)
    assert [s.sku for s in found] == ["MAD"]


def test_distinct_from_cart_refuses_an_attribute_that_does_not_exist():
    with pytest.raises(SuggestionRuleError, match="sabour"):
        ComplementRule.validate_params({"distinct_from_cart": ["sabour"]})


# --- o esquema de 23/09: sacola composta, ausência e um por sacola ---------


def test_when_absent_silences_a_pairing_once_the_cart_has_it(listing):
    _product("PAO", "Pão", listing=listing, natureza="comida")
    _product("CAFE", "Café", listing=listing, natureza="bebida")
    _rule({"pairings": [{
        "when": {"attr": "natureza", "value": "comida"},
        "when_absent": [{"attr": "natureza", "value": "bebida"}],
        "suggest": {"attr": "natureza", "value": "bebida"}, "weight": 3,
    }]})

    assert [s.sku for s in suggest(COMPLEMENT, cart_skus={"PAO"}, channel_ref=CHANNEL)] == ["CAFE"]
    _product("SUCO", "Suco", listing=listing, natureza="bebida")
    assert suggest(COMPLEMENT, cart_skus={"PAO", "CAFE"}, channel_ref=CHANNEL) == ()


def test_a_when_list_needs_every_condition_somewhere_in_the_cart(listing):
    _product("CROQUE", "Croque", listing=listing, natureza="comida", sabor="salgado")
    _product("SUCO", "Suco", listing=listing, natureza="bebida")
    _product("MAD", "Madeleine", listing=listing, natureza="comida", sabor="doce")
    _rule({"pairings": [{
        "when": [{"attr": "sabor", "value": "salgado"}, {"attr": "natureza", "value": "bebida"}],
        "suggest": {"attr": "sabor", "value": "doce"}, "weight": 3,
    }]})

    assert suggest(COMPLEMENT, cart_skus={"CROQUE"}, channel_ref=CHANNEL) == ()
    found = suggest(COMPLEMENT, cart_skus={"CROQUE", "SUCO"}, channel_ref=CHANNEL)
    assert [s.sku for s in found] == ["MAD"]
    assert found[0].reasons == ("pairing:sabor=salgado+natureza=bebida→sabor=doce",)


def test_one_per_cart_keeps_a_second_drink_out_even_with_history(listing):
    _product("CAFE", "Café", listing=listing, natureza="bebida")
    _product("CAPPU", "Cappuccino", listing=listing, natureza="bebida")
    _affinity("CAFE", "CAPPU", 9.0)
    _rule({"affinity_weight": 3, "one_per_cart": [{"attr": "natureza", "value": "bebida"}]})

    assert suggest(COMPLEMENT, cart_skus={"CAFE"}, channel_ref=CHANNEL) == ()


def test_history_breaks_ties_but_never_inverts_a_preference(listing):
    """Salgado pede gelada (+1); o café com lift 50 ainda perde para o suco."""
    _product("CROQUE", "Croque", listing=listing, natureza="comida", sabor="salgado")
    _product("CAFE", "Café", price_q=500, listing=listing,
             natureza="bebida", temperatura="quente")
    _product("SUCO", "Suco", price_q=1500, listing=listing,
             natureza="bebida", temperatura="gelado")
    _affinity("CROQUE", "CAFE", 50.0)
    _rule({"pairings": [
        {"when": {"attr": "natureza", "value": "comida"},
         "suggest": {"attr": "natureza", "value": "bebida"}, "weight": 3},
        {"when": {"attr": "sabor", "value": "salgado"},
         "suggest": [{"attr": "natureza", "value": "bebida"},
                     {"attr": "temperatura", "value": "gelado"}], "weight": 1},
    ], "affinity_weight": 3, "price": "below_cart_average"})

    found = suggest(COMPLEMENT, cart_skus={"CROQUE"}, channel_ref=CHANNEL, limit=2)
    assert [s.sku for s in found] == ["SUCO", "CAFE"]


def test_the_new_schema_is_validated():
    with pytest.raises(SuggestionRuleError, match="vazia"):
        ComplementRule.validate_params({"pairings": [
            {"when": [], "suggest": {"attr": "natureza", "value": "bebida"}},
        ]})
    with pytest.raises(SuggestionRuleError, match="sabour"):
        ComplementRule.validate_params({"pairings": [
            {"when": {"attr": "natureza", "value": "comida"},
             "when_absent": [{"attr": "sabour", "value": "doce"}],
             "suggest": {"attr": "natureza", "value": "bebida"}},
        ]})
    with pytest.raises(SuggestionRuleError, match="tag"):
        ComplementRule.validate_params({"one_per_cart": [{"tag": "cafe"}]})
