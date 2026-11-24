"""OC-33 B1: o cardápio responde "para quando?" (servidor).

A cliente escolhe o dia antes da lista, e a disponibilidade e a promessa passam a
responder PARA aquele dia, pela régua da reserva: a encomenda de um dia mede só a
fornada da data e o que ainda vale nela, nunca a sobra de hoje (dono, 18/11/2026).
A data escolhida vai para a sacola no primeiro "Adicionar" e a reserva cai nela;
a sacola e o checkout leem a mesma data.

Relógio fixo: terça, 17/11/2026, 10h em São Paulo, casa de segunda a sábado das 7h
às 18h. O dia escolhido é a quinta, 19/11 (turnos da casa: 9h, 12h, 15h).

Invariantes provados aqui (plano da Etapa II, §6):

- **X1**: dia, item e horário só se oferecem quando a projeção diz que são
  possíveis (item sem horário no dia não acende o Adicionar; hoje encerrado não é
  oferecido como "hoje aberto").
- **X13**: para hoje, o cardápio com ``?date=`` é o MESMO do cardápio sem data
  (A = B): a variante muda a pergunta, nunca o preço, a disponibilidade ou a promessa.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

SP = ZoneInfo("America/Sao_Paulo")
TUESDAY = date(2026, 11, 17)
THURSDAY = date(2026, 11, 19)
SUNDAY = date(2026, 11, 22)
OPEN_AT_10 = datetime(2026, 11, 17, 10, 0, tzinfo=SP)
CLOSED_AT_19 = datetime(2026, 11, 17, 19, 0, tzinfo=SP)

CATALOG = "/api/v1/storefront/catalog/"


def _frozen(at: datetime):
    return patch("django.utils.timezone.now", return_value=at.astimezone(ZoneInfo("UTC")))


def _world():
    """Pão de um dia com vitrine HOJE e nada na quinta; fornadas da quinta; geleia de validade longa."""
    from shopman.offerman.models import Listing, ListingItem, Product
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind, Quant

    from shopman.shop.models import Shop

    cache.clear()
    shop = Shop.load() or Shop.objects.create(name="Casa")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "18:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
    }
    shop.save(update_fields=["opening_hours"])
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    listing, _ = Listing.objects.get_or_create(ref="web", defaults={"name": "Loja", "is_active": True})

    def product(sku, name, *, shelf_life_days, metadata=None):
        item = Product.objects.create(
            sku=sku, name=name, base_price_q=900, is_published=True, is_sellable=True,
            shelf_life_days=shelf_life_days, metadata=metadata or {},
        )
        ListingItem.objects.create(listing=listing, product=item, price_q=900)
        return item

    def planned(sku, day, qty):
        Quant.objects.create(sku=sku, position=None, target_date=day, _quantity=Decimal(qty))

    # Pão do dia com vitrine cheia HOJE e nenhuma fornada na quinta.
    product("PAO", "Pão do Dia", shelf_life_days=1)
    stock.receive(Decimal("20"), sku="PAO", position=vitrine, reason="vitrine de hoje")
    # Brioche: fornada da quinta, pronto desde a abertura.
    product("BRIOCHE", "Brioche", shelf_life_days=1)
    planned("BRIOCHE", THURSDAY, 10)
    # Tabatière: fornada da quinta, pronta às 11h (a casa declarou).
    product("TABAT", "Tabatière", shelf_life_days=1, metadata={"ready_from": "11:00"})
    planned("TABAT", THURSDAY, 10)
    # Fornada da quinta que só fica pronta às 19h: nenhum turno da quinta cabe.
    product("TARDIO", "Pão Tardio", shelf_life_days=1, metadata={"ready_from": "19:00"})
    planned("TARDIO", THURSDAY, 10)
    # Geleia: validade longa, o estoque de hoje lastreia qualquer dia.
    product("GELEIA", "Geleia", shelf_life_days=None)
    stock.receive(Decimal("5"), sku="GELEIA", position=vitrine, reason="prateleira")


def _items(payload) -> dict[str, dict]:
    return {item["sku"]: item for item in payload["catalog"]["items"]}


def _put(client, sku, **body):
    return client.put(f"/api/v1/cart/skus/{sku}/", data=json.dumps(body), content_type="application/json")


def _session():
    from shopman.orderman.models import Session

    return Session.objects.get(state="open", channel_ref="web")


# ── o cardápio do dia ──────────────────────────────────────────────────


def test_o_dia_escolhido_mede_so_a_fornada_do_dia_e_nunca_a_sobra_de_hoje():
    with _frozen(OPEN_AT_10):
        _world()
        resp = Client().get(CATALOG, {"date": THURSDAY.isoformat()})
        assert resp.status_code == 200, resp.content[:400]
        items = _items(resp.json())

    # A vitrine de hoje (20 pães de um dia) não vale na quinta: indisponível, sem motivo.
    pao = items["PAO"]
    assert (pao["can_add_to_cart"], pao["availability"], pao["availability_label"]) == (
        False, "unavailable", "Indisponível",
    )
    assert pao["promise"] is None
    assert pao["is_notifiable"] is False

    # A fornada da quinta é o que a quinta tem: disponível desde a abertura, sem frase.
    brioche = items["BRIOCHE"]
    assert brioche["can_add_to_cart"] is True
    assert brioche["availability"] == "available"
    assert brioche["promise"]["date"] == THURSDAY.isoformat()
    assert brioche["promise"]["ready_at"] == "09:00"
    assert brioche["promise"]["text"] == ""
    assert brioche["promise"]["day_label"] == "quinta, 19/11"

    # Pronta depois da abertura: diz a hora, no vocabulário aprovado.
    tabat = items["TABAT"]
    assert tabat["can_add_to_cart"] is True
    assert tabat["promise"]["ready_at"] == "12:00"  # o primeiro turno que começa depois das 11h
    assert tabat["promise"]["text"] == "A partir das 12h"

    # Validade longa: o estoque de hoje lastreia a quinta.
    assert items["GELEIA"]["can_add_to_cart"] is True
    assert items["GELEIA"]["promise"]["text"] == ""


def test_x1_item_sem_horario_no_dia_nao_oferece_o_adicionar():
    """X1: a fornada existe, mas nenhum turno da quinta começa depois das 19h."""
    with _frozen(OPEN_AT_10):
        _world()
        items = _items(Client().get(CATALOG, {"date": THURSDAY.isoformat()}).json())

    tardio = items["TARDIO"]
    assert tardio["can_add_to_cart"] is False
    assert tardio["availability"] == "unavailable"
    assert tardio["availability_label"] == "Indisponível"
    assert tardio["promise"] is None


def test_o_dia_escolhido_volta_na_projecao_com_o_rotulo_e_a_abertura():
    with _frozen(OPEN_AT_10):
        _world()
        days = Client().get(CATALOG, {"date": THURSDAY.isoformat()}).json()["catalog"]["days"]

    assert days["selected"] == {"date": "2026-11-19", "label": "quinta, 19/11", "opens_at": "09:00"}
    assert days["today"] == "2026-11-17"
    assert days["today_open"] is True
    # Domingo não tem expediente: nunca entra entre os dias oferecidos.
    assert days["next_days"] == ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21"]
    assert days["closed_weekdays"] == [6]


def test_x1_hoje_encerrado_nao_e_oferecido_como_aberto():
    with _frozen(CLOSED_AT_19):
        _world()
        days = Client().get(CATALOG).json()["catalog"]["days"]

    assert days["today_open"] is False
    assert days["next_days"][0] == "2026-11-18"
    assert days["selected"] is None


def test_x13_hoje_com_data_e_o_mesmo_cardapio_sem_data():
    """X13: para hoje, A (sem data) e B (``?date=hoje``) recebem o MESMO cardápio."""
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        without = client.get(CATALOG).json()
        with_today = client.get(CATALOG, {"date": TUESDAY.isoformat()}).json()

    assert with_today == without
    assert with_today["catalog"]["days"]["selected"] is None


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("2026-11-22", "A casa não abre em 22/11/2026. Escolha outra data."),
        ("2026-11-16", "Não é possível encomendar para uma data passada."),
        ("quinta", "Data inválida. Use AAAA-MM-DD."),
    ],
)
def test_dia_que_a_casa_nao_combina_e_recusado_com_a_frase(raw, message):
    with _frozen(OPEN_AT_10):
        _world()
        resp = Client().get(CATALOG, {"date": raw})

    assert resp.status_code == 400
    body = resp.json()
    assert (body["detail"], body["field"]) == (message, "date")
    assert body["errors"] == {"date": [message]}


def test_a_gemea_publica_nunca_responde_um_dia():
    """O dia nunca vai para o cache de borda: a gêmea pública recusa parâmetro."""
    with _frozen(OPEN_AT_10):
        _world()
        resp = Client().get("/api/v1/storefront/public/catalog/", {"date": THURSDAY.isoformat()})

    assert resp.status_code == 400
    assert "public" not in resp.get("Cache-Control", "")


def test_ler_o_cardapio_do_dia_nao_escreve_nada():
    from shopman.orderman.models import Session
    from shopman.stockman.models import Hold

    with _frozen(OPEN_AT_10):
        _world()
        before = (Session.objects.count(), Hold.objects.count())
        resp = Client().get(CATALOG, {"date": THURSDAY.isoformat()})
        assert resp.status_code == 200
        assert (Session.objects.count(), Hold.objects.count()) == before
        # X14: a leitura do dia é a rota canônica, nunca cacheável na borda.
        assert "public" not in resp.get("Cache-Control", "")


# ── a data vai para a sacola ───────────────────────────────────────────


def test_o_primeiro_adicionar_grava_o_dia_e_a_reserva_cai_nele():
    from shopman.stockman.models import Hold

    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        resp = _put(client, "BRIOCHE", qty=1, date=THURSDAY.isoformat())
        assert resp.status_code == 200, resp.content[:400]

        session = _session()
        assert session.data["delivery_date"] == "2026-11-19"
        holds = Hold.objects.filter(metadata__reference=session.session_key)
        assert {hold.target_date for hold in holds} == {THURSDAY}

        # A sacola e o checkout leem a mesma data.
        expected_day = {"date": "2026-11-19", "label": "quinta, 19/11"}
        assert resp.json()["cart"]["day"] == expected_day
        assert client.get("/api/v1/storefront/cart/").json()["cart"]["day"] == expected_day
        checkout = client.get("/api/v1/storefront/checkout/").json()
        assert checkout["checkout"]["cart"]["day"] == expected_day

        # O cardápio do dia mostra o que já está na sacola dela, com a reserva dela.
        items = _items(client.get(CATALOG, {"date": THURSDAY.isoformat()}).json())
        assert items["BRIOCHE"]["qty_in_cart"] == 1
        assert items["BRIOCHE"]["can_add_to_cart"] is True

        # Outro item do mesmo dia entra na mesma sacola.
        assert _put(client, "TABAT", qty=1, date=THURSDAY.isoformat()).status_code == 200
        assert {hold.target_date for hold in Hold.objects.filter(metadata__reference=session.session_key)} == {
            THURSDAY,
        }


def test_outro_dia_com_a_sacola_ja_datada_e_outro_pedido():
    """Um pedido, uma data: a sacola da quinta não aceita o item de hoje, nem reserva nada."""
    from shopman.stockman.models import Hold

    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        assert _put(client, "BRIOCHE", qty=1, date=THURSDAY.isoformat()).status_code == 200
        holds_before = Hold.objects.count()

        resp = _put(client, "GELEIA", qty=1, date=TUESDAY.isoformat())

        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "cart_date_mismatch"
        assert (body["cart_date"], body["item_date"]) == ("2026-11-19", "2026-11-17")
        assert Hold.objects.count() == holds_before


def test_dia_recusado_no_adicionar_nao_abre_sacola():
    from shopman.orderman.models import Session

    with _frozen(OPEN_AT_10):
        _world()
        resp = _put(Client(), "BRIOCHE", qty=1, date=SUNDAY.isoformat())

        assert resp.status_code == 400
        body = resp.json()
        assert (body["field"], body["error_code"]) == ("date", "date_refused")
        assert body["detail"] == "A casa não abre em 22/11/2026. Escolha outra data."
        assert Session.objects.count() == 0


def test_hoje_escolhido_com_a_sacola_vazia_tira_o_dia_e_segue_a_regra_de_sempre():
    from shopman.stockman.models import Hold

    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        assert _put(client, "BRIOCHE", qty=1, date=THURSDAY.isoformat()).status_code == 200
        assert _put(client, "BRIOCHE", qty=0).status_code == 200  # esvaziou a sacola

        resp = _put(client, "GELEIA", qty=1, date=TUESDAY.isoformat())

        assert resp.status_code == 200, resp.content[:400]
        session = _session()
        assert "delivery_date" not in session.data
        assert resp.json()["cart"]["day"] is None
        live = Hold.objects.filter(metadata__reference=session.session_key, status__in=["pending", "confirmed"])
        assert {hold.target_date for hold in live if hold.quant_id} <= {TUESDAY}


def test_sem_data_o_adicionar_e_o_de_sempre():
    """A (sem experimento): nenhum campo novo no pedido, nenhuma data gravada."""
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        resp = _put(client, "GELEIA", qty=1)

        assert resp.status_code == 200
        assert "delivery_date" not in _session().data
        assert resp.json()["cart"]["day"] is None


def test_tirar_da_sacola_nao_depende_do_dia():
    """Com a sacola da quinta, o "-" no cardápio de outro dia tira o item, sem recusa."""
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        assert _put(client, "BRIOCHE", qty=2, date=THURSDAY.isoformat()).status_code == 200

        resp = _put(client, "BRIOCHE", qty=1, date=(THURSDAY + timedelta(days=1)).isoformat())

        assert resp.status_code == 200, resp.content[:400]
        [line] = resp.json()["cart"]["items"]
        assert line["qty"] == 1


# ── o "Trocar": a sacola inteira muda de dia, ou nada muda (X3, X4) ─────

FRIDAY = THURSDAY + timedelta(days=1)


def _day(client, day, without=None):
    body = {"date": day.isoformat()}
    if without is not None:
        body["without"] = without
    return client.put("/api/v1/cart/day/", data=json.dumps(body), content_type="application/json")


def _bag_on_thursday(client):
    """Brioche e Tabatière na sacola da quinta; na sexta só há fornada de brioche."""
    from shopman.stockman.models import Quant

    Quant.objects.create(sku="BRIOCHE", position=None, target_date=FRIDAY, _quantity=Decimal(10))
    assert _put(client, "BRIOCHE", qty=2, date=THURSDAY.isoformat()).status_code == 200
    assert _put(client, "TABAT", qty=1, date=THURSDAY.isoformat()).status_code == 200


def _live_hold_dates(session_key):
    from shopman.stockman.models import Hold

    return {
        hold.target_date
        for hold in Hold.objects.filter(metadata__reference=session_key, status__in=["pending", "confirmed"])
        if hold.quant_id
    }


def _lines(session):
    return {item["sku"]: int(float(item["qty"])) for item in session.items}


def test_trocar_para_um_dia_em_que_um_item_nao_da_nomeia_o_item_e_nao_muda_nada():
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        _bag_on_thursday(client)
        before = _session()

        resp = _day(client, FRIDAY)

        assert resp.status_code == 409, resp.content[:400]
        body = resp.json()
        assert body["error_code"] == "cart_day_change_refused"
        assert [item["name"] for item in body["items"]] == ["Tabatière"]
        assert body["title"] == "Tabatière não está disponível para sexta, 20/11"
        assert body["detail"] == "Você pode seguir para sexta, 20/11 sem ele, ou manter o dia que tinha."
        # Nada mudou: o dia, as reservas e as linhas são os de antes.
        after = _session()
        assert after.data["delivery_date"] == "2026-11-19"
        assert _live_hold_dates(after.session_key) == {THURSDAY}
        assert _lines(after) == _lines(before) == {"BRIOCHE": 2, "TABAT": 1}


def test_seguir_sem_ele_tira_so_aquele_item_e_leva_o_resto_para_o_dia_novo():
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        _bag_on_thursday(client)

        resp = _day(client, FRIDAY, without=["TABAT"])

        assert resp.status_code == 200, resp.content[:400]
        session = _session()
        assert _lines(session) == {"BRIOCHE": 2}
        assert session.data["delivery_date"] == "2026-11-20"
        assert _live_hold_dates(session.session_key) == {FRIDAY}
        assert resp.json()["cart"]["day"] == {"date": "2026-11-20", "label": "sexta, 20/11"}


def test_adicionar_depois_da_troca_nao_da_409():
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        _bag_on_thursday(client)
        assert _day(client, FRIDAY, without=["TABAT"]).status_code == 200

        resp = _put(client, "GELEIA", qty=1, date=FRIDAY.isoformat())

        assert resp.status_code == 200, resp.content[:400]
        assert _live_hold_dates(_session().session_key) == {FRIDAY}


def test_trocar_quando_tudo_da_move_a_sacola_inteira_com_efeito_unico():
    from shopman.stockman.models import Quant

    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        _bag_on_thursday(client)
        Quant.objects.create(sku="TABAT", position=None, target_date=FRIDAY, _quantity=Decimal(10))

        resp = _day(client, FRIDAY)

        assert resp.status_code == 200, resp.content[:400]
        session = _session()
        assert _lines(session) == {"BRIOCHE": 2, "TABAT": 1}
        assert _live_hold_dates(session.session_key) == {FRIDAY}
        # X4: a mesma troca de novo deixa a sacola igual.
        assert _day(client, FRIDAY).status_code == 200
        again = _session()
        assert _lines(again) == {"BRIOCHE": 2, "TABAT": 1}
        assert _live_hold_dates(again.session_key) == {FRIDAY}


def test_trocar_para_um_dia_que_a_casa_nao_atende_recusa_e_a_sacola_fica_intacta():
    with _frozen(OPEN_AT_10):
        _world()
        client = Client()
        _bag_on_thursday(client)

        resp = _day(client, SUNDAY)

        assert resp.status_code == 400
        body = resp.json()
        assert (body["field"], body["error_code"]) == ("date", "date_refused")
        assert body["detail"] == "A casa não abre em 22/11/2026. Escolha outra data."
        after = _session()
        assert after.data["delivery_date"] == "2026-11-19"
        assert _live_hold_dates(after.session_key) == {THURSDAY}
        assert _lines(after) == {"BRIOCHE": 2, "TABAT": 1}
