"""Loja fechada promete só o que existe (OC-04, invariante X1 da Etapa II omnicanal).

Laudo da Etapa II, U1: às 22h, com a loja fechada, 0 de 31 itens podiam ir à
sacola, e o topo da home dizia "Você já pode finalizar o pedido" (constante no
Nuxt) e a sacola, "Você pode encomendar para o próximo dia". A frase não conferia
o cardápio.

Aqui fica provado que ``ordering`` (home e sacola) é o resumo das MESMAS
promessas que o card do cardápio diz (``presentation/promise.promise_for``):

- unidade (sem banco): o resumo de um conjunto de promessas;
- integração (com banco, relógio congelado): catálogo vazio, só fornada
  planejada, pronto agora, loja fechada, virada do dia e nada encomendável,
  lidos pela API como a loja lê.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from shopman.storefront.presentation.promise import (
    KIND_BATCH,
    KIND_PREORDER,
    KIND_READY,
    ORDERING_NONE,
    ORDERING_NOW,
    ORDERING_PREORDER,
    PromiseProjection,
    ordering_from_promises,
)

SP = ZoneInfo("America/Sao_Paulo")
TUESDAY = date(2026, 11, 17)


def _promise(kind: str, day: date) -> PromiseProjection:
    return PromiseProjection(kind, day.isoformat(), "09:00", "", "")


# ── unidade ────────────────────────────────────────────────────────────


class TestOrderingFromPromises:
    def test_sem_promessa_nenhuma_e_none(self):
        assert ordering_from_promises([], today=TUESDAY).state == ORDERING_NONE
        none = ordering_from_promises([None, None], today=TUESDAY)
        assert (none.state, none.next_date, none.day_label) == (ORDERING_NONE, None, "")

    def test_algo_para_hoje_e_now(self):
        ordering = ordering_from_promises(
            [None, _promise(KIND_BATCH, TUESDAY + timedelta(days=1)), _promise(KIND_READY, TUESDAY)],
            today=TUESDAY,
        )
        assert (ordering.state, ordering.next_date, ordering.day_label) == (
            ORDERING_NOW, "2026-11-17", "hoje",
        )

    def test_so_outro_dia_e_preorder_com_o_dia_mais_cedo(self):
        ordering = ordering_from_promises(
            [
                _promise(KIND_PREORDER, TUESDAY + timedelta(days=2)),
                _promise(KIND_BATCH, TUESDAY + timedelta(days=1)),
            ],
            today=TUESDAY,
        )
        assert (ordering.state, ordering.next_date, ordering.day_label) == (
            ORDERING_PREORDER, "2026-11-18", "amanhã, quarta",
        )

    def test_dia_mais_distante_leva_a_data(self):
        ordering = ordering_from_promises([_promise(KIND_PREORDER, date(2026, 11, 19))], today=TUESDAY)
        assert ordering.day_label == "quinta, 19/11"


# ── integração ─────────────────────────────────────────────────────────

CLOCKS = {
    # terça, 10h: casa aberta (segunda a sábado, das 7h às 18h)
    "aberta": datetime(2026, 11, 17, 10, 0, tzinfo=SP),
    # terça, 19h: casa fechada desde as 18h
    "fechada": datetime(2026, 11, 17, 19, 0, tzinfo=SP),
    # terça, 22h: a hora do laudo
    "noite": datetime(2026, 11, 17, 22, 0, tzinfo=SP),
    # a virada: terça 23h50 e quarta 0h10, casa fechada nas duas
    "antes_da_virada": datetime(2026, 11, 17, 23, 50, tzinfo=SP),
    "depois_da_virada": datetime(2026, 11, 18, 0, 10, tzinfo=SP),
}


def _frozen(at: datetime):
    return patch("django.utils.timezone.now", return_value=at.astimezone(ZoneInfo("UTC")))


def _world(*, stock: dict[str, Decimal | None], planned: dict[str, date] | None = None):
    """Um cardápio na loja online, na ordem de ``stock``.

    ``stock`` é o pronto na vitrine (``None``: SKU sem pronto, só fornada);
    ``planned`` é a fornada planejada (dia) de cada SKU que tiver.
    """
    from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
    from shopman.stockman import stock as stock_service
    from shopman.stockman.models import Position, PositionKind, Quant

    from shopman.shop.models import Channel, Shop

    shop = Shop.load() or Shop.objects.create(name="Casa")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "18:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
    }
    shop.save(update_fields=["opening_hours"])
    Channel.objects.filter(ref="web").update(config={"waitlist": {"enabled": True, "horizon_days": 3}})
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    listing, _ = Listing.objects.get_or_create(ref="web", defaults={"name": "Loja", "is_active": True})
    collection, _ = Collection.objects.get_or_create(
        ref="paes", defaults={"name": "Pães", "is_active": True},
    )
    for order, (sku, qty) in enumerate(stock.items()):
        product = Product.objects.create(
            sku=sku, name=sku.title(), base_price_q=600, is_published=True, is_sellable=True,
        )
        CollectionItem.objects.create(collection=collection, product=product, is_primary=True, sort_order=order)
        ListingItem.objects.create(listing=listing, product=product, price_q=600)
        if qty is not None:
            Quant.objects.create(sku=sku, position=vitrine, _quantity=qty)
    for sku, day in (planned or {}).items():
        # Como o estado ``planned`` do seed (``apply_storefront_state``): a fornada
        # entra na vitrine com o dia dela.
        stock_service.receive(Decimal("30"), sku=sku, position=vitrine, target_date=day, reason="fornada do teste")


def _read(client) -> tuple[dict, dict]:
    home = client.get("/api/v1/storefront/home/").json()["home"]
    cart = client.get("/api/v1/storefront/cart/").json()["cart"]
    return home, cart


def integration(fn):
    for mark in (pytest.mark.usefixtures("fresh_cache"), pytest.mark.channels("web"), pytest.mark.django_db):
        fn = mark(fn)
    return fn


@pytest.fixture
def fresh_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@integration
def test_catalogo_vazio_nao_tem_o_que_pedir():
    from django.test import Client

    with _frozen(CLOCKS["aberta"]):
        _world(stock={})
        home, cart = _read(Client())

    assert home["ordering"] == {"state": "none", "next_date": None, "day_label": ""}
    assert cart["ordering"] == home["ordering"]


@integration
def test_so_fornada_planejada_e_encomenda_para_o_dia_dela():
    from django.test import Client

    wednesday = TUESDAY + timedelta(days=1)
    with _frozen(CLOCKS["aberta"]):
        _world(stock={"SONHO": None}, planned={"SONHO": wednesday})
        home, cart = _read(Client())

    assert home["ordering"] == {
        "state": "preorder", "next_date": "2026-11-18", "day_label": "amanhã, quarta",
    }
    assert cart["ordering"] == home["ordering"]


@integration
def test_pronto_agora_com_a_casa_aberta_e_now():
    from django.test import Client

    with _frozen(CLOCKS["aberta"]):
        _world(stock={"PAO": Decimal("12")})
        home, cart = _read(Client())

    assert home["ordering"] == {"state": "now", "next_date": "2026-11-17", "day_label": "hoje"}
    assert cart["ordering"] == home["ordering"]


@integration
def test_loja_fechada_com_pronto_e_encomenda_para_amanha():
    """O regime da ADR-036: com a casa fechada, o pronto vira encomenda do próximo dia com horário."""
    from django.test import Client

    with _frozen(CLOCKS["fechada"]):
        _world(stock={"PAO": Decimal("12")})
        home, cart = _read(Client())

    assert home["shop_status"]["is_open"] is False
    assert home["ordering"] == {
        "state": "preorder", "next_date": "2026-11-18", "day_label": "amanhã, quarta",
    }
    assert cart["ordering"] == home["ordering"]


@integration
def test_virada_do_dia_amanha_vira_hoje():
    """23h50 de terça: encomenda para amanhã, quarta. 0h10 de quarta: a quarta já é hoje."""
    from django.test import Client

    with _frozen(CLOCKS["antes_da_virada"]):
        _world(stock={"PAO": Decimal("12")})
        before, _ = _read(Client())
    with _frozen(CLOCKS["depois_da_virada"]):
        after, _ = _read(Client())

    assert before["ordering"] == {
        "state": "preorder", "next_date": "2026-11-18", "day_label": "amanhã, quarta",
    }
    assert after["shop_status"]["is_open"] is False
    assert after["ordering"] == {"state": "now", "next_date": "2026-11-18", "day_label": "hoje"}


@integration
def test_x1_nada_encomendavel_a_home_e_a_sacola_nao_oferecem_finalizar():
    """X1: catálogo sem item encomendável ⇒ ``ordering.state == "none"`` ⇒ nenhuma frase de pedir.

    O cenário do laudo: 22h, casa fechada, todo item esgotado e nenhuma fornada
    planejada. O card de cada item não acende o botão, e a home e a sacola não
    podem dizer o contrário: nem a faceta "Escolha o dia ao finalizar o pedido.
    Encomendas com até 30 dias" de "Como funciona", que o laudo mediu na home.
    A frase do topo do hero mora no Nuxt e é provada no vitest
    (``homePresentation.test.ts``).
    """
    from django.test import Client

    with _frozen(CLOCKS["noite"]):
        _world(stock={"PAO": Decimal("0"), "AGUA": Decimal("0"), "BOLO": Decimal("0")})
        client = Client()
        home, cart = _read(client)
        menu = client.get("/api/v1/storefront/menu/").json()["catalog"]

    assert not any(item["can_add_to_cart"] for item in menu["items"])
    assert home["ordering"]["state"] == ORDERING_NONE
    assert cart["ordering"]["state"] == ORDERING_NONE

    assert "preorder" not in [facet["ref"] for facet in home["sections_copy"]["how_facets"]]
    # A FAQ fica de fora da varredura: ela RESPONDE a pergunta "Posso encomendar
    # para outro dia?" com a regra da casa ("Ao finalizar o pedido, você escolhe o
    # dia"), não convida a pedir agora. O resto da home e a sacola não podem.
    offers = {key: value for key, value in home.items() if key != "faq"}
    rendered = json.dumps(offers, ensure_ascii=False) + json.dumps(cart, ensure_ascii=False)
    assert "finalizar o pedido" not in rendered
    assert "Você pode encomendar" not in rendered
    # A sacola vazia diz o que há (nenhuma encomenda) e aponta o aviso.
    assert cart["empty_title"] == "Hoje não há encomenda aberta"
    assert "Me avise" in cart["empty_message"]
    [continue_action] = [a for a in cart["actions"] if a["ref"] == "continue_shopping"]
    assert continue_action["label"] == "Ver cardápio"


@integration
def test_sacola_vazia_com_encomenda_aberta_segue_a_copy_do_momento():
    from django.test import Client

    with _frozen(CLOCKS["fechada"]):
        _world(stock={"PAO": Decimal("12")})
        home, cart = _read(Client())

    assert "preorder" in [facet["ref"] for facet in home["sections_copy"]["how_facets"]]
    assert cart["empty_title"] == "Já fechamos por hoje"
    assert cart["empty_message"] == "Você pode encomendar para o próximo dia."
    [continue_action] = [a for a in cart["actions"] if a["ref"] == "continue_shopping"]
    assert continue_action["label"] == "Continuar comprando"


@integration
def test_sacola_com_itens_nao_rele_o_cardapio(monkeypatch):
    """Com itens, cada linha diz quando fica pronta; ``ordering`` fica ``None`` e o cardápio não é relido."""
    from django.test import Client

    from shopman.storefront.presentation import cart as cart_presentation

    with _frozen(CLOCKS["aberta"]):
        _world(stock={"PAO": Decimal("12")})
        client = Client()
        resp = client.put(
            "/api/v1/cart/skus/PAO/", data=json.dumps({"qty": 1}), content_type="application/json",
        )
        assert resp.status_code in (200, 201), resp.content[:400]

        def reread(**_kwargs):
            raise AssertionError("a sacola com itens releu o cardápio inteiro")

        monkeypatch.setattr(cart_presentation, "build_ordering", reread)
        cart = client.get("/api/v1/storefront/cart/").json()["cart"]

    assert cart["is_empty"] is False
    assert cart["ordering"] is None


@integration
def test_vitrine_da_home_abre_com_o_que_da_para_pedir():
    """Laudo U6: "Do nosso cardápio" abria com três "Indisponível" e o que dava para pedir ficava de fora."""
    from django.test import Client

    with _frozen(CLOCKS["aberta"]):
        _world(stock={
            "FENDU": Decimal("0"), "BOLO": Decimal("0"), "AGUA": Decimal("0"), "PAO": Decimal("12"),
        })
        home, _cart = _read(Client())

    rail = [item["sku"] for item in home["featured_items"]]
    assert rail[0] == "PAO", rail
    assert home["featured_items"][0]["can_add_to_cart"] is True
