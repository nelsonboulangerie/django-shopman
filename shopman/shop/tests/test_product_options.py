"""``shopman.shop.product_options``: formato, validação, escolha, preço, cozinha e nota.

Fase 1 das escolhas no produto (dono, 02/10/2026): sabor obrigatório e
adicionais com preço. O adicional sai SOMADO ao item na NFC-e (uma linha); o
insumo que a opção gasta é gravado e mostrado, sem baixa na venda.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop import product_options as po

GROUPS = [
    {
        "ref": "adicionais", "label": "Adicionais", "min": 0, "max": 2,
        "options": [
            {"ref": "ovo-frito", "label": "Ovo frito", "price_q": 400, "available": True,
             "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]},
            {"ref": "salada", "label": "Salada", "price_q": 300, "available": True, "consumes": []},
            {"ref": "bacon", "label": "Bacon", "price_q": 500, "available": False},
        ],
    },
    {
        "ref": "pao", "label": "Pão", "min": 1, "max": 1,
        "options": [
            {"ref": "brioche", "label": "Brioche", "price_q": 0},
            {"ref": "campagne", "label": "Campagne", "price_q": 0},
        ],
    },
]


def _product(groups=GROUPS, name="Croque Monsieur"):
    return SimpleNamespace(sku="CQMO", name=name, metadata={"option_groups": groups})


# ── formato ──────────────────────────────────────────────────────────────────


def test_parse_is_tolerant_and_drops_what_is_malformed():
    groups = po.parse(_product([
        "lixo",
        {"ref": "sem-opcao", "label": "Vazio", "options": []},
        {"ref": "g", "label": "Grupo", "min": 5, "max": 9, "options": [
            {"ref": "a", "label": "A", "price_q": -1},
            {"ref": "b", "label": "B", "price_q": "200"},
            {"ref": "b", "label": "B de novo", "price_q": 0},
        ]},
    ]))
    assert len(groups) == 1
    group = groups[0]
    assert [option.ref for option in group.options] == ["b"]
    assert group.options[0].price_q == 200
    # min/max cabem no que existe: um grupo obrigatório impossível travaria o produto.
    assert (group.min, group.max) == (1, 1)


def test_public_groups_never_carry_the_ingredient():
    public = po.public_groups(_product())
    assert public[0]["options"][0] == {"ref": "ovo-frito", "label": "Ovo frito", "price_q": 400, "available": True}
    assert "consumes" not in str(public)
    assert po.public_groups(SimpleNamespace(metadata={})) == []


# ── escolha → linha ──────────────────────────────────────────────────────────


def test_resolve_reads_everything_from_the_catalog_and_freezes_consumes():
    product = _product()
    resolved = po.resolve_selection(product, [
        {"group": "pao", "ref": "brioche"},
        {"group": "adicionais", "ref": "ovo-frito"},
    ])
    assert resolved == [
        {"group": "adicionais", "group_label": "Adicionais", "ref": "ovo-frito", "name": "Ovo frito",
         "qty": 1, "unit_price_q": 400, "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]},
        {"group": "pao", "group_label": "Pão", "ref": "brioche", "name": "Brioche",
         "qty": 1, "unit_price_q": 0, "consumes": []},
    ]
    # Congelado: mudar o cadastro depois não muda o que a linha gravou.
    product.metadata["option_groups"][0]["options"][0]["consumes"][0]["qty"] = "999"
    assert resolved[0]["consumes"][0]["qty"] == "50"
    product.metadata["option_groups"][0]["options"][0]["consumes"][0]["qty"] = "50"


@pytest.mark.parametrize(
    ("selection", "code"),
    [
        ([], "option_required"),
        ([{"group": "pao", "ref": "brioche"}, {"group": "pao", "ref": "campagne"}], "option_unknown"),
        ([{"group": "pao", "ref": "focaccia"}], "option_unknown"),
        ([{"group": "molho", "ref": "x"}], "option_unknown"),
        ([{"group": "pao", "ref": "brioche"}, {"group": "adicionais", "ref": "bacon"}], "option_unavailable"),
        ([{"group": "pao", "ref": "brioche"}, {"group": "pao", "ref": "brioche"}], "option_unknown"),
        ("lixo", "option_unknown"),
    ],
)
def test_resolve_refuses_with_a_stable_code(selection, code):
    with pytest.raises(po.OptionSelectionError) as caught:
        po.resolve_selection(_product(), selection)
    assert caught.value.code == code
    assert "—" not in caught.value.message


def test_required_message_names_the_group_and_the_product():
    with pytest.raises(po.OptionSelectionError) as caught:
        po.resolve_selection(_product(), [])
    assert caught.value.message == "Falta escolher Pão de Croque Monsieur."


def test_signature_summary_and_name_are_stable():
    first = po.resolve_selection(_product(), [
        {"group": "adicionais", "ref": "salada"}, {"group": "pao", "ref": "brioche"},
        {"group": "adicionais", "ref": "ovo-frito"},
    ])
    second = po.resolve_selection(_product(), [
        {"group": "pao", "ref": "brioche"}, {"group": "adicionais", "ref": "ovo-frito"},
        {"group": "adicionais", "ref": "salada"},
    ])
    assert po.signature(first) == po.signature(second) == "adicionais:ovo-frito|adicionais:salada|pao:brioche"
    assert po.summary(first) == "+ Ovo frito · + Salada · Brioche"
    name = po.line_name("Croque Monsieur", first)
    assert name == "Croque Monsieur (+ Ovo frito · + Salada · Brioche)"
    assert po.base_name(name, first) == "Croque Monsieur"
    assert po.line_name("Croque Monsieur", []) == "Croque Monsieur"
    assert po.signature([]) == ""


def test_ifood_options_without_ref_are_not_ours():
    ifood = [{"name": "Bacon extra", "group": "Adicionais", "qty": 1, "unit_price_q": 500, "customizations": []}]
    assert po.signature(ifood) == ""
    assert po.summary(ifood) == ""
    assert po.options_unit_price_q(_product(), ifood) == 0
    assert po.kitchen_note({"options": ifood, "notes": "Adicionais: 1× Bacon extra"}) == "Adicionais: 1× Bacon extra"


def test_kitchen_note_is_summary_then_note_and_is_derived():
    meta = {"options": [{"group": "adicionais", "ref": "ovo-frito", "name": "Ovo frito", "unit_price_q": 400}],
            "notes": "gema mole"}
    assert po.kitchen_note(meta) == "+ Ovo frito\ngema mole"
    assert meta["notes"] == "gema mole"
    assert po.kitchen_note({}) == ""


def test_option_price_is_reread_by_ref_and_vanished_option_counts_zero():
    line = [{"group": "adicionais", "ref": "ovo-frito", "unit_price_q": 1}, {"group": "adicionais", "ref": "x"}]
    assert po.options_unit_price_q(_product(), line) == 400


# ── cadastro (Admin) ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_validate_definition_checks_the_ingredient_and_its_unit():
    from shopman.buyman.models import Material

    Material.objects.create(sku="OVOS", name="Ovos", unit="g")

    ok = po.validate_definition([{
        "ref": "adicionais", "label": "  Adicionais ", "min": 0, "max": 1,
        "options": [{"ref": "ovo-frito", "label": "Ovo frito", "price_q": 400,
                     "consumes": [{"sku": "OVOS", "qty": "50,0", "unit": "G"}]}],
    }])
    assert ok[0]["label"] == "Adicionais"
    assert ok[0]["options"][0]["consumes"] == [{"sku": "OVOS", "qty": "50", "unit": "g"}]
    assert ok[0]["options"][0]["available"] is True

    with pytest.raises(po.OptionDefinitionError) as caught:
        po.validate_definition([{
            "ref": "Adicionais!", "label": "", "min": 2, "max": 1,
            "options": [
                {"ref": "ovo", "label": "Ovo", "price_q": -5,
                 "consumes": [{"sku": "OVOS", "qty": "1", "unit": "un"},
                              {"sku": "NAO-EXISTE", "qty": "0", "unit": "xícara"}]},
            ],
        }])
    text = " | ".join(caught.value.messages)
    assert "minúsculas" in text
    assert "falta o nome do grupo" in text
    assert "passa do máximo" in text
    assert "preço em centavos" in text
    assert "OVOS conta em g" in text
    assert "NAO-EXISTE não existe" in text
    assert "maior que zero" in text
    assert "unidades das fichas" in text
    assert "—" not in text


def test_validate_definition_empty_means_no_choice():
    assert po.validate_definition("") == []
    assert po.validate_definition([]) == []


# ── preço ────────────────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, items, policy):
        self.items = items
        self.pricing_policy = policy
        self.pricing_trace = []

    def update_items(self, items):
        self.items = items


class _Backend:
    def get_price(self, sku, channel, **kwargs):
        return 2400


@pytest.mark.django_db
def test_internal_pricing_adds_options_and_list_price_includes_them():
    from shopman.offerman.models import Product

    from shopman.shop.handlers.pricing import ItemPricingModifier

    Product.objects.create(sku="CQMO", name="Croque Monsieur", base_price_q=2400, metadata={"option_groups": GROUPS})
    items = [
        {"line_id": "L1", "sku": "CQMO", "qty": 2, "unit_price_q": 1,
         "meta": {"options": [{"group": "adicionais", "ref": "ovo-frito", "unit_price_q": 1}]}},
        {"line_id": "L2", "sku": "CQMO", "qty": 1, "unit_price_q": 1, "meta": {}},
    ]
    session = _FakeSession(items, "internal")

    ItemPricingModifier(_Backend()).apply(channel=None, session=session, ctx={})

    with_egg, plain = session.items
    assert (with_egg["unit_price_q"], with_egg["line_total_q"], with_egg["meta"]["_list_q"]) == (2800, 5600, 2800)
    assert (plain["unit_price_q"], plain["line_total_q"]) == (2400, 2400)


def test_external_pricing_ifood_keeps_the_price_it_brought():
    from shopman.shop.handlers.pricing import ItemPricingModifier

    items = [{"line_id": "i1", "sku": "CQMO", "qty": 1, "unit_price_q": 3100, "line_total_q": 3100,
              "meta": {"options": [{"name": "Ovo", "group": "Adicionais", "qty": 1, "unit_price_q": 700}]}}]
    session = _FakeSession(items, "external")

    ItemPricingModifier(_Backend()).apply(channel=None, session=session, ctx={})

    assert session.items[0]["unit_price_q"] == 3100
    assert session.items[0]["line_total_q"] == 3100


# ── cozinha ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_kds_card_shows_the_product_name_and_the_choice_in_the_note():
    from shopman.shop.services import kds

    options = [{"group": "adicionais", "ref": "ovo-frito", "name": "Ovo frito", "unit_price_q": 400}]
    routed = kds._build_routable_items([
        {"line_id": "L1", "sku": "CQMO", "name": "Croque Monsieur (+ Ovo frito)", "qty": 1,
         "notes": "gema mole", "meta": {"options": options, "notes": "gema mole"}},
        {"line_id": "i1", "sku": "CQMO", "name": "Croque Monsieur", "qty": 1,
         "notes": "Adicionais: 1× Bacon", "meta": {"options": [{"name": "Bacon", "group": "Adicionais"}]}},
    ])
    assert (routed[0]["name"], routed[0]["notes"]) == ("Croque Monsieur", "+ Ovo frito\ngema mole")
    # iFood: intocado (a nota dele já traz a opção).
    assert (routed[1]["name"], routed[1]["notes"]) == ("Croque Monsieur", "Adicionais: 1× Bacon")


# ── nota fiscal ──────────────────────────────────────────────────────────────


def test_nfce_line_is_one_line_with_the_summary_and_exact_values():
    from decimal import Decimal

    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    mapped = _map_item(1, {
        "sku": "CQMO", "name": "Croque Monsieur (+ Ovo frito)", "qty": "2", "unit": "UN",
        "unit_price_q": 2800, "total_q": 5600,
        "fiscal": {"ncm": "16024900", "icms_origem": "0", "csosn": "102",
                   "pis_situacao_tributaria": "49", "cofins_situacao_tributaria": "49"},
    }, {})

    assert mapped["descricao"] == "Croque Monsieur (+ Ovo frito)"
    assert Decimal(str(mapped["valor_bruto"])) == Decimal("56.00")
    assert Decimal(str(mapped["valor_unitario_comercial"])) == Decimal("28.00")
    assert (
        Decimal(str(mapped["valor_unitario_comercial"])) * Decimal(str(mapped["quantidade_comercial"]))
        == Decimal(str(mapped["valor_bruto"]))
    )
