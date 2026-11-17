"""A promessa de quando: um fato só, no card, no produto e na linha da sacola (WP-L01).

Plano EXCELENCIA-STOREFRONT, seção 4.1 e achados P1-01, P1-02, P2-12: cinco telas
calculavam cada uma o seu "quando". Aqui fica provado que as três projeções leem
a MESMA função (``presentation/promise.promise_for``) e que ela diz o que o
checkout oferece: o dia da fornada, a hora de pronto e a grade de horários.

Duas camadas:

- **unidade** (sem banco): a frase e o tipo para cada combinação de fatos, com a
  grade preenchida à mão;
- **integração** (com banco, relógio congelado): os quatro estados de vitrine do
  perfil ``qa`` do seed (``STOREFRONT_STATES``: FENDU esgotado, MELON últimas
  unidades, TABAT fornada só amanhã, MDLN pausado), lidos pela API como a loja
  lê, com a casa aberta, fechada e num dia sem expediente.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from shopman.storefront.presentation.promise import (
    KIND_BATCH,
    KIND_PREORDER,
    KIND_READY,
    promise_for,
)
from shopman.storefront.services.promise_facts import PromiseFacts

SP = ZoneInfo("America/Sao_Paulo")
# Terça, 17/11/2026. A casa abre de segunda a sábado, das 7h às 18h.
TUESDAY = date(2026, 11, 17)
CANONICAL = (time(9), time(12), time(15))


def _facts(
    *,
    at: datetime,
    grids: dict[date, tuple[time, ...]],
    today_orderable: dict[str, bool] | None = None,
    next_batch: dict[str, date] | None = None,
    ready_at: dict[str, time] | None = None,
    readiness_unavailable: bool = False,
) -> PromiseFacts:
    facts = PromiseFacts(
        now=at,
        today=at.astimezone(SP).date(),
        next_batch=next_batch or {},
        today_orderable=today_orderable or {},
        ready_at=ready_at or {},
        readiness_unavailable=readiness_unavailable,
    )
    # Dia que o teste não declara é dia sem horário (fechado).
    for offset in range(20):
        day = facts.today + timedelta(days=offset)
        facts._grids[day] = grids.get(day, ())
    return facts


def _half_hours(start: time, end: time) -> tuple[time, ...]:
    out, cursor = [], datetime.combine(TUESDAY, start)
    while cursor.time() < end:
        out.append(cursor.time())
        cursor += timedelta(minutes=30)
    return tuple(out)


# ── unidade ────────────────────────────────────────────────────────────


class TestPromiseSentence:
    def test_pronto_hoje_com_a_casa_aberta(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        facts = _facts(at=at, grids={TUESDAY: _half_hours(time(10, 30), time(18))})

        promise = promise_for("MELON", facts, orderable=True)

        assert promise.kind == KIND_READY
        assert promise.text == "Pronto agora"
        assert promise.date == "2026-11-17"
        assert promise.ready_at == "10:30"
        assert promise.day_label == "hoje"

    def test_preparado_na_hora_nao_diz_pronto(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        facts = _facts(at=at, grids={TUESDAY: _half_hours(time(10, 30), time(18))})

        promise = promise_for("CROQUE", facts, orderable=True, made_to_order=True)

        assert (promise.kind, promise.text) == (KIND_READY, "Preparado na hora")

    def test_fica_pronto_hoje_mais_tarde_pela_hora_de_pronto(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        facts = _facts(
            at=at,
            grids={TUESDAY: _half_hours(time(10, 30), time(18))},
            ready_at={"BAGUETE": time(15)},
        )

        promise = promise_for("BAGUETE", facts, orderable=True)

        assert promise.kind == KIND_BATCH
        assert promise.text == "Fica pronto hoje às 15h"
        assert promise.ready_at == "15:00"

    def test_fornada_de_amanha_diz_o_dia_e_a_hora(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        wednesday = TUESDAY + timedelta(days=1)
        facts = _facts(
            at=at,
            grids={TUESDAY: _half_hours(time(10, 30), time(18)), wednesday: CANONICAL},
            today_orderable={"TABAT": False},
            next_batch={"TABAT": wednesday},
            ready_at={"TABAT": time(15)},
        )

        promise = promise_for("TABAT", facts, orderable=True)

        assert promise.kind == KIND_BATCH
        assert promise.text == "Fica pronto amanhã, quarta, a partir das 15h"
        assert promise.date == "2026-11-18"
        assert promise.day_label == "amanhã, quarta"

    def test_casa_fechada_nunca_diz_hoje(self):
        """P1-02: às 18:38, com a casa fechada, a loja dizia "Disponível hoje"."""
        at = datetime(2026, 11, 17, 18, 38, tzinfo=SP)
        wednesday = TUESDAY + timedelta(days=1)
        facts = _facts(at=at, grids={TUESDAY: (), wednesday: CANONICAL})

        promise = promise_for("CROISSANT", facts, orderable=True)

        assert promise.kind == KIND_PREORDER
        assert promise.text == "Fica pronto amanhã, quarta, a partir das 9h"

    def test_corte_do_dia_passa_para_o_proximo_dia(self):
        """Casa ainda aberta às 17h45, mas a antecedência já não deixa horário hoje."""
        at = datetime(2026, 11, 17, 17, 45, tzinfo=SP)
        wednesday = TUESDAY + timedelta(days=1)
        facts = _facts(at=at, grids={TUESDAY: (), wednesday: CANONICAL})

        promise = promise_for("MELON", facts, orderable=True)

        assert promise.kind == KIND_PREORDER
        assert promise.text == "Fica pronto amanhã, quarta, a partir das 9h"

    def test_hora_de_pronto_corta_os_horarios_de_hoje_e_dos_proximos_dias(self):
        """Hoje o último horário começa às 16h30; os turnos de amanhã, às 9h, 12h e 15h."""
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        wednesday = TUESDAY + timedelta(days=1)
        facts = _facts(
            at=at,
            grids={TUESDAY: _half_hours(time(10, 30), time(17)), wednesday: CANONICAL},
            ready_at={"BAGUETE": time(13)},
        )
        # hoje, 13h cabe
        assert promise_for("BAGUETE", facts, orderable=True).text == "Fica pronto hoje às 13h"
        facts.ready_at["BAGUETE"] = time(17)
        promise = promise_for("BAGUETE", facts, orderable=True)
        assert promise is None  # nenhum turno de amanhã começa depois das 17h

    def test_pronto_depois_do_ultimo_horario_sem_turno_que_caiba_nao_promete(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        facts = _facts(
            at=at,
            grids={TUESDAY: _half_hours(time(10, 30), time(18)), TUESDAY + timedelta(days=1): CANONICAL},
            ready_at={"BAGUETE": time(18, 30)},
        )
        assert promise_for("BAGUETE", facts, orderable=True) is None

    def test_dia_sem_expediente_pula_para_o_proximo_dia_aberto(self):
        sunday = date(2026, 11, 22)
        monday = sunday + timedelta(days=1)
        at = datetime(2026, 11, 22, 10, 0, tzinfo=SP)
        facts = _facts(at=at, grids={sunday: (), monday: CANONICAL})

        promise = promise_for("MELON", facts, orderable=True)

        assert promise.kind == KIND_PREORDER
        assert promise.text == "Fica pronto amanhã, segunda, a partir das 9h"

    def test_fornada_num_dia_fechado_fica_para_o_proximo_dia_aberto(self):
        at = datetime(2026, 11, 20, 10, 0, tzinfo=SP)  # sexta
        saturday, sunday, monday = (date(2026, 11, 21), date(2026, 11, 22), date(2026, 11, 23))
        facts = _facts(
            at=at,
            grids={saturday: (), sunday: (), monday: CANONICAL},
            today_orderable={"TABAT": False},
            next_batch={"TABAT": sunday},
        )

        promise = promise_for("TABAT", facts, orderable=True)

        assert promise.kind == KIND_PREORDER
        assert promise.text == "Fica pronto segunda, 23/11, a partir das 9h"

    def test_sem_promessa_quando_nao_ha_o_que_afirmar(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        grids = {TUESDAY: _half_hours(time(10, 30), time(18))}

        # indisponível ou pausado: o selo "Indisponível" já fala
        assert promise_for("FENDU", _facts(at=at, grids=grids), orderable=False) is None
        # prontidão que não pôde ser apurada: o checkout recusa todo horário
        assert promise_for("X", _facts(at=at, grids=grids, readiness_unavailable=True), orderable=True) is None
        # espera fornada, e a fornada não se achou
        facts = _facts(at=at, grids=grids, today_orderable={"X": False})
        assert promise_for("X", facts, orderable=True) is None
        # nenhum dia com horário na busca
        assert promise_for("X", _facts(at=at, grids={}), orderable=True) is None

    def test_linha_da_sacola_usa_o_dia_da_reserva(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        thursday = TUESDAY + timedelta(days=2)
        facts = _facts(at=at, grids={TUESDAY: _half_hours(time(10, 30), time(18)), thursday: CANONICAL})

        promise = promise_for("TABAT", facts, orderable=True, planned_for=thursday)

        assert promise.kind == KIND_BATCH
        assert promise.text == "Fica pronto quinta, 19/11, a partir das 9h"

    def test_meia_hora_aparece_na_frase(self):
        at = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
        facts = _facts(
            at=at,
            grids={TUESDAY: _half_hours(time(10, 30), time(18))},
            ready_at={"BAGUETE": time(11, 30)},
        )

        assert promise_for("BAGUETE", facts, orderable=True).text == "Fica pronto hoje às 11h30"

    def test_verbo_e_fica_pronto_nunca_sai(self):
        at = datetime(2026, 11, 17, 19, 0, tzinfo=SP)
        wednesday = TUESDAY + timedelta(days=1)
        facts = _facts(at=at, grids={wednesday: CANONICAL})
        text = promise_for("CROISSANT", facts, orderable=True).text
        assert "sai" not in text.split()
        assert "—" not in text


# ── totais da linha (decisão 1) ────────────────────────────────────────


def _cart_line(**overrides):
    from shopman.shop.projections.cart import CartLineProjection

    fields = {
        "line_id": "L1", "sku": "MELON", "name": "Melonpan", "qty": 2,
        "unit_price_q": 510, "line_total_q": 1020,
        "is_available": True, "available_qty": None,
        "is_awaiting_confirmation": False, "is_ready_for_confirmation": False,
        "confirmation_deadline_iso": None, "planned_for_date": None, "earlier_available_date": None,
        "list_price_q": 600, "list_total_q": 1200,
        "discount_name": "Happy Hour", "discount_is_coupon": False,
    }
    fields.update(overrides)
    return CartLineProjection(**fields)


class TestCartLineTotals:
    def test_com_promocao_a_linha_fala_o_total_com_desconto_e_risca_o_cheio(self):
        from shopman.storefront.presentation.cart import _present_line

        item = _present_line(_cart_line(), {})

        assert item.promo_price_display == "R$ 5,10"
        assert item.line_total_display == "R$ 10,20"
        assert item.line_total_struck_display == "R$ 12,00"

    def test_sem_promocao_o_total_e_o_cheio_e_nada_se_risca(self):
        from shopman.storefront.presentation.cart import _present_line

        item = _present_line(
            _cart_line(unit_price_q=600, line_total_q=1200, discount_name=None), {},
        )

        assert item.line_total_display == "R$ 12,00"
        assert item.line_total_struck_display is None

    def test_cupom_nao_abate_na_linha(self):
        from shopman.storefront.presentation.cart import _present_line

        item = _present_line(_cart_line(discount_name="BEMVINDO", discount_is_coupon=True), {})

        assert item.line_total_display == "R$ 12,00"
        assert item.line_total_struck_display is None


# ── integração: os quatro estados do perfil qa, pela API ───────────────

QA_SKUS = ("FENDU", "MELON", "TABAT", "MDLN")


def _frozen(at: datetime):
    return patch("django.utils.timezone.now", return_value=at.astimezone(ZoneInfo("UTC")))


def _qa_world():
    """Os quatro produtos, cada um no estado de vitrine do perfil ``qa``.

    O estado sai da MESMA função do seed (``apply_storefront_state``), sob o
    relógio congelado do teste: a fornada da Tabatière é para o dia seguinte ao
    "hoje" do cenário, como no seed.
    """
    from shopman.offerman.models import Listing, ListingItem, Product
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    from config.management.commands.seed import STOREFRONT_STATES, apply_storefront_state
    from shopman.shop.models import Channel, Shop

    shop = Shop.load() or Shop.objects.create(name="Casa")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "18:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
    }
    shop.save(update_fields=["opening_hours"])
    Channel.objects.filter(ref="web").update(
        config={"waitlist": {"enabled": True, "horizon_days": 3}},
    )
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    listing, _ = Listing.objects.get_or_create(ref="web", defaults={"name": "Loja", "is_active": True})
    names = {"FENDU": "Fendu", "MELON": "Melonpan", "TABAT": "Tabatière", "MDLN": "Madeleine"}
    for sku, name in names.items():
        product = Product.objects.create(
            sku=sku, name=name, base_price_q=600, is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=600)
        stock.receive(Decimal("20"), sku=sku, position=vitrine, reason="mundo do teste")
    # A Tabatière fica pronta às 15h (declarado), como a fornada da tarde.
    Product.objects.filter(sku="TABAT").update(metadata={"ready_from": "15:00"})
    for state, sku in STOREFRONT_STATES.items():
        apply_storefront_state(state, sku, vitrine=vitrine)


def _promises_from_api(client) -> dict[str, dict | None]:
    menu = client.get("/api/v1/storefront/menu/").json()["catalog"]
    by_sku = {item["sku"]: item.get("promise") for item in menu["items"]}
    for sku in QA_SKUS:
        detail = client.get(f"/api/v1/storefront/products/{sku}/").json()["product"]
        # O produto e o card dizem a mesma coisa, sempre.
        assert detail.get("promise") == by_sku[sku], sku
    return by_sku


def _cart_promise(client, sku: str) -> dict | None:
    import json

    resp = client.put(
        f"/api/v1/cart/skus/{sku}/", data=json.dumps({"qty": 1}), content_type="application/json",
    )
    assert resp.status_code in (200, 201), resp.content[:400]
    cart = client.get("/api/v1/storefront/cart/").json()["cart"]
    [line] = [item for item in cart["items"] if item["sku"] == sku]
    return line["promise"]


CLOCKS = {
    # terça, 10h: casa aberta
    "aberta": datetime(2026, 11, 17, 10, 0, tzinfo=SP),
    # terça, 19h: casa fechada desde as 18h
    "fechada": datetime(2026, 11, 17, 19, 0, tzinfo=SP),
    # domingo, 10h: dia sem expediente
    "domingo": datetime(2026, 11, 22, 10, 0, tzinfo=SP),
}

EXPECTED = {
    "aberta": {
        "MELON": ("ready", "Pronto agora"),
        "TABAT": ("batch", "Fica pronto amanhã, quarta, a partir das 15h"),
    },
    "fechada": {
        "MELON": ("preorder", "Fica pronto amanhã, quarta, a partir das 9h"),
        "TABAT": ("batch", "Fica pronto amanhã, quarta, a partir das 15h"),
    },
    "domingo": {
        "MELON": ("preorder", "Fica pronto amanhã, segunda, a partir das 9h"),
        "TABAT": ("batch", "Fica pronto amanhã, segunda, a partir das 15h"),
    },
}


@pytest.mark.django_db
@pytest.mark.channels("web")
@pytest.mark.parametrize("moment", list(CLOCKS))
def test_os_quatro_estados_da_vitrine_qa_dizem_a_mesma_promessa_no_card_no_produto_e_na_sacola(moment):
    from django.core.cache import cache
    from django.test import Client

    cache.clear()
    with _frozen(CLOCKS[moment]):
        _qa_world()
        client = Client()
        promises = _promises_from_api(client)

        # Indisponível (esgotado) e pausado: nada a prometer.
        assert promises["FENDU"] is None
        assert promises["MDLN"] is None
        for sku, (kind, text) in EXPECTED[moment].items():
            assert promises[sku] is not None, sku
            assert (promises[sku]["kind"], promises[sku]["text"]) == (kind, text), sku

        # A linha da sacola repete a promessa do card.
        for sku in ("MELON", "TABAT"):
            assert _cart_promise(client, sku) == promises[sku], sku


@pytest.mark.django_db
@pytest.mark.channels("web")
def test_a_promessa_e_o_horario_mais_cedo_que_o_checkout_oferece():
    """O que a tela promete é o que o checkout oferece: mesma grade, mesmo corte."""
    from django.core.cache import cache
    from django.test import Client

    from shopman.storefront.services.pickup_slots import annotate_slots_for_checkout

    cache.clear()
    with _frozen(CLOCKS["aberta"]):
        _qa_world()
        promises = _promises_from_api(Client())
        for sku in ("MELON", "TABAT"):
            promise = promises[sku]
            checkout = annotate_slots_for_checkout([sku], delivery_date=promise["date"])
            [earliest] = [s for s in checkout["pickup_slots"] if s["is_earliest"]]
            assert earliest["starts_at"] == promise["ready_at"], sku
