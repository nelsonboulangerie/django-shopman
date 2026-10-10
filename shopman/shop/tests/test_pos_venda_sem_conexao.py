"""A venda que o PDV fez SEM CONEXÃO e enviou depois (WP-PDV-SEM-CONEXAO).

A fila do PDV reenvia o mesmo ``close_sale`` com o mesmo ``client_request_id``.
O servidor já é idempotente por essa chave, e o pedido diz que nasceu de uma
venda sem conexão, quando o balcão cobrou e de quando eram os preços da tela
(``order.data.pos.offline``).

Decisões do dono de 10/10/2026 (§3.3 do WP):

- **D.** A venda é precificada NA HORA DA COBRANÇA; se a conta ainda assim
  divergir do cobrado, vale o cobrado e a diferença fica registrada. Sem recusa.
- **C.** Comanda mudada em outro dispositivo: fecha só o que este cobrou; o resto
  segue aberto. Comanda já paga: não cobra de novo as mesmas linhas.

O relógio dos testes é fixo (``timezone.now`` em ``patch``): a janela de
plausibilidade da hora da cobrança (24 h, turno aberto) depende dele.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from shopman.orderman.models import Order

from shopman.shop.models import Channel
from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db

BRT = ZoneInfo("America/Sao_Paulo")
DIA = datetime(2026, 10, 10, tzinfo=BRT)


def _at(hour: int, minute: int = 0, *, day: int = 0) -> datetime:
    return DIA.replace(hour=hour, minute=minute) + timedelta(days=day)


@pytest.fixture
def balcao():
    """O balcão com o turno aberto às 7h do dia da venda."""
    from shopman.cashman.models import Shift

    with patch("django.utils.timezone.now", return_value=_at(7)):
        counter = _Counter()
    Shift.objects.filter(pk=counter.shift.pk).update(opened_at=_at(7))
    counter.shift.refresh_from_db()
    cache.clear()
    yield counter
    cache.clear()


def _send(counter, *, at: datetime, **overrides):
    with patch("django.utils.timezone.now", return_value=at):
        return counter.close(**overrides)


def _offline(captured: datetime, **extra) -> dict:
    return {"offline_captured_at": captured.isoformat(), "expected_total_q": 1200, **extra}


def _happy_hour(percent=40, start="17:00", end="18:00"):
    from shopman.shop.models import RuleConfig

    RuleConfig.objects.create(
        ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Happy Hour", params={"discount_percent": percent, "start": start, "end": end}, enabled=True,
    )
    cache.clear()


# ── O registro ───────────────────────────────────────────────────────────────


def test_venda_sem_conexao_grava_a_hora_da_cobranca_no_pedido(balcao):
    result = _send(
        balcao, at=_at(15),
        client_request_id="pos:offline-1",
        offline_captured_at="2026-10-10T14:32:05-03:00",
        offline_prices_at="2026-10-10T14:05:00-03:00",
    )

    offline = Order.objects.get(ref=result.order_ref).data["pos"]["offline"]
    assert offline["captured_at"] == "2026-10-10T14:32:05-03:00"
    assert offline["prices_at"] == "2026-10-10T14:05:00-03:00"
    assert offline["priced_at"] == "2026-10-10T14:32:05-03:00"


def test_reenvio_da_fila_devolve_a_mesma_venda(balcao):
    first = _send(balcao, at=_at(15), client_request_id="pos:offline-2", offline_captured_at="2026-10-10T17:32:05Z")
    again = _send(balcao, at=_at(15, 5), client_request_id="pos:offline-2", offline_captured_at="2026-10-10T17:32:05Z")

    assert again.order_ref == first.order_ref
    assert Order.objects.filter(data__client_request_id="pos:offline-2").count() == 1


def test_venda_com_conexao_nao_ganha_marca_de_offline(counter):
    result = counter.close(client_request_id="pos:online-1")

    assert "offline" not in (Order.objects.get(ref=result.order_ref).data.get("pos") or {})


def test_hora_sem_fuso_e_recusada():
    with pytest.raises(PosIntentError) as refused:
        parse_pos_sale_intent(
            {"items": [{"sku": "PAO", "qty": 1}], "offline_captured_at": "2026-10-10T14:32:05"},
        )

    assert refused.value.field == "offline_captured_at"


@pytest.fixture
def counter():
    return _Counter()


# ── D: o preço da hora da venda; vale o cobrado ─────────────────────────────


def test_xepa_venda_das_15h_enviada_no_happy_hour_nao_ganha_o_desconto(balcao):
    _happy_hour()

    result = _send(balcao, at=_at(17, 30), client_request_id="pos:xepa", **_offline(_at(15)))

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200
    assert order.data["pos"]["offline"]["priced_at"] == _at(15).isoformat()
    assert "pricing" not in order.data["pos"]["offline"]
    assert order.data["payment"]["amount_q"] == 1200


def test_venda_com_conexao_no_happy_hour_segue_com_o_desconto(balcao):
    # Controle: o relógio da precificação só muda para a venda sem conexão.
    _happy_hour()

    result = _send(balcao, at=_at(17, 30), client_request_id="pos:hh-online")

    assert Order.objects.get(ref=result.order_ref).total_q == 720


def test_venda_no_happy_hour_enviada_depois_dele_vale_o_cobrado_e_registra(balcao):
    # Cobrada às 17h40 pelo preço cheio (a tela sem conexão não sabe do Happy
    # Hour): pela hora da venda o servidor daria 40%, mas o que entrou foi o cheio.
    from shopman.backstage.models import OperatorAlert

    _happy_hour()

    result = _send(balcao, at=_at(18, 30), client_request_id="pos:hh-cobrado", **_offline(_at(17, 40)))

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200
    assert order.data["pos"]["offline"]["pricing"] == {
        "priced_at": _at(17, 40).isoformat(),
        "charged_total_q": 1200,
        "server_total_q": 720,
        "difference_q": 480,
    }
    assert "happy_hour" not in ((order.snapshot or {}).get("pricing") or {})
    alert = OperatorAlert.objects.get(type="pos_offline_sale_adjusted", order_ref=order.ref)
    assert "Valeu o cobrado: R$ 4,80 acima do preço." in alert.message
    assert alert.audience == "orders"


def test_preco_de_catalogo_mudado_na_queda_vale_o_cobrado_sem_recusa(balcao):
    from shopman.offerman.models import Product

    Product.objects.filter(sku="PAO").update(base_price_q=1500)

    result = _send(balcao, at=_at(16), client_request_id="pos:catalogo", **_offline(_at(15)))

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200
    assert order.data["pos"]["offline"]["pricing"]["difference_q"] == -300
    sale = balcao.sale_lines()[-1]
    assert sale.order_ref == order.ref and sale.amount_q == 1200


def test_promocao_que_venceu_durante_a_queda_vale_para_a_venda_feita_antes(balcao):
    from shopman.shop.models import Promotion

    Promotion.objects.create(
        ref="manha", name="Manhã", type=Promotion.PERCENT, value=20, is_active=True,
        valid_from=_at(6), valid_until=_at(16),
    )
    cache.clear()
    item = {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 960}

    result = _send(
        balcao, at=_at(17), client_request_id="pos:promo",
        items=[item], **_offline(_at(15, 30), expected_total_q=960),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 960
    assert "pricing" not in order.data["pos"]["offline"]


def test_aniversario_e_o_do_dia_da_venda_nao_o_do_envio():
    from shopman.guestman.models import Customer
    from shopman.offerman.models import Product
    from shopman.orderman.ids import generate_session_key
    from shopman.orderman.models import Session
    from shopman.orderman.services.modify import ModifyService

    from shopman.shop.models import Promotion

    Channel.objects.create(ref="pdv", name="PDV", is_active=True)
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=1000, is_published=True, is_sellable=True)
    Customer.objects.create(ref="ANA", first_name="Ana", birthday=DIA.date().replace(year=1990))
    Promotion.objects.create(
        ref="aniver", name="Aniversário", type=Promotion.PERCENT, value=10, is_active=True,
        birthday_only=True, valid_from=_at(0, day=-30), valid_until=_at(0, day=30),
    )
    cache.clear()

    def priced(ctx):
        key = generate_session_key()
        Session.objects.create(session_key=key, channel_ref="pdv", state="open", data={"customer": {"ref": "ANA"}})
        with patch("django.utils.timezone.now", return_value=_at(0, 10, day=1)):
            session = ModifyService.modify_session(
                session_key=key, channel_ref="pdv", ctx=ctx,
                ops=[{"op": "add_line", "sku": "BOLO", "qty": 1, "unit_price_q": 1000}],
            )
        return session.items[0]["unit_price_q"]

    # A venda das 23h50 do aniversário, enviada à 0h10 do dia seguinte.
    assert priced({"priced_at": _at(23, 50)}) == 900
    # Precificada no envio, o aniversário já teria passado.
    assert priced({}) == 1000


def test_hora_fora_da_janela_segue_a_regra_de_sempre(balcao):
    _happy_hour()

    # Velha demais (antes do turno e de 24 h): precificada no envio, como sempre.
    result = _send(balcao, at=_at(17, 30), client_request_id="pos:velha", **_offline(_at(15, day=-2)))

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 720
    assert "priced_at" not in order.data["pos"]["offline"]


def test_travas_da_venda_sem_conexao_decidem_quem_ganha_o_relogio_da_cobranca():
    from shopman.shop.services import pos_offline_sale

    payload = {
        "items": [{"sku": "PAO", "qty": 1, "unit_price_q": 1200, "discount": {"type": "percent", "value": 10}}],
        "payment_method": "cash",
        "offline_captured_at": _at(15).isoformat(),
    }
    assert pos_offline_sale.pricing_instant(payload, now=_at(16)) is None
    payload["items"][0].pop("discount")
    assert pos_offline_sale.pricing_instant(payload, now=_at(16)) == _at(15)
    assert pos_offline_sale.pricing_instant(payload, now=_at(14)) is None  # no futuro
    payload["payment_method"] = "pix"
    assert pos_offline_sale.pricing_instant(payload, now=_at(16)) is None


# ── C: comanda mudada em outro dispositivo ───────────────────────────────────

PAO = {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200, "line_id": "L-pao00001"}
OUTRO = {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200, "line_id": "L-outro001"}


def _open_tab(ref="12"):
    from shopman.shop.services import pos as pos_service

    with patch("django.utils.timezone.now", return_value=_at(14)):
        return pos_service.open_pos_tab(channel_ref="pdv", tab_ref=ref, actor="pos:marina", operator_username="marina")


def _save_tab(session, items):
    from shopman.shop.services import pos as pos_service

    with patch("django.utils.timezone.now", return_value=_at(14, 30)):
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={"tab_session_key": session.session_key, "items": items},
            actor="pos:marina",
            operator_username="marina",
        )
    session.refresh_from_db()


def _revision(session):
    from shopman.shop.services.pos_intent import pos_session_revision

    session.refresh_from_db()
    return pos_session_revision(session)


def _pay_tab_elsewhere(counter, tab, items):
    return _send(
        counter, at=_at(14, 45), client_request_id="pos:outro-pagou", items=items,
        tab_session_key=tab.session_key, expected_revision=_revision(tab),
    )


def test_comanda_mudada_em_outro_dispositivo_fecha_so_o_cobrado(balcao):
    from shopman.orderman.models import Session

    from shopman.backstage.models import OperatorAlert

    tab = _open_tab()
    _save_tab(tab, [PAO])
    seen = _revision(tab)
    # Durante a queda, o outro dispositivo lança mais um item na mesma comanda.
    _save_tab(tab, [PAO, OUTRO])

    result = _send(
        balcao, at=_at(15, 30), client_request_id="pos:comanda",
        items=[PAO], tab_session_key=tab.session_key, expected_revision=seen, **_offline(_at(15)),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert [item.line_id for item in order.items.all()] == ["L-pao00001"]
    assert order.total_q == 1200
    record = order.data["pos"]["offline"]["tab"]
    assert record["outcome"] == "lines_left_open"
    assert [line["line_id"] for line in record["left_open"]] == ["L-outro001"]
    # A comanda segue viva, com o mesmo número e só o que não foi cobrado.
    still_open = Session.objects.get(handle_type="pos_tab", handle_ref=tab.handle_ref, state="open")
    assert [item["line_id"] for item in still_open.items] == ["L-outro001"]
    alert = OperatorAlert.objects.get(type="pos_offline_sale_adjusted", order_ref=order.ref)
    assert "1 item lançado em outro dispositivo segue aberto na comanda." in alert.message


def test_linha_que_ja_esta_na_cozinha_nao_volta_ao_kds_na_comanda_nova(balcao):
    from shopman.orderman.models import Session

    from shopman.shop.adapters import kds as kds_adapter

    tab = _open_tab()
    _save_tab(tab, [PAO])
    seen = _revision(tab)
    _save_tab(tab, [PAO, OUTRO])

    # O outro dispositivo já mandou a linha dele à cozinha (ticket da comanda antiga).
    with patch("shopman.shop.services.kds.fired_line_ids", return_value={"L-outro001"}):
        _send(
            balcao, at=_at(15, 30), client_request_id="pos:cozinha",
            items=[PAO], tab_session_key=tab.session_key, expected_revision=seen, **_offline(_at(15)),
        )

    still_open = Session.objects.get(handle_type="pos_tab", handle_ref=tab.handle_ref, state="open")
    assert still_open.data["kds_inherited_lines"] == ["L-outro001"]
    assert still_open.data["fired_lines"] == ["L-outro001"]
    assert "L-outro001" in kds_adapter.fired_line_ids_for_session(still_open.session_key)


def test_comanda_mudada_fora_da_fila_sem_conexao_segue_recusada(balcao):
    tab = _open_tab()
    _save_tab(tab, [PAO])
    seen = _revision(tab)
    _save_tab(tab, [PAO, OUTRO])

    with pytest.raises(PosIntentError) as refused:
        _send(
            balcao, at=_at(15, 30), client_request_id="pos:online-tab",
            items=[PAO], tab_session_key=tab.session_key, expected_revision=seen, expected_total_q=1200,
        )

    assert refused.value.code == "tab_revision_conflict"


def test_quantidade_mudada_no_outro_dispositivo_vale_o_cobrado_e_so_registra(balcao):
    tab = _open_tab()
    _save_tab(tab, [PAO])
    seen = _revision(tab)
    _save_tab(tab, [{**PAO, "qty": 3}])

    result = _send(
        balcao, at=_at(15, 30), client_request_id="pos:qty",
        items=[PAO], tab_session_key=tab.session_key, expected_revision=seen, **_offline(_at(15)),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200
    adjusted = order.data["pos"]["offline"]["tab"]["adjusted"]
    assert adjusted == [{
        "line_id": "L-pao00001", "sku": "PAO", "name": "Pão", "qty": 1,
        "kind": "qty_changed_elsewhere", "charged_qty": 1, "tab_qty": 3,
    }]


def test_linha_que_o_outro_dispositivo_tirou_vale_o_cobrado(balcao):
    tab = _open_tab()
    _save_tab(tab, [PAO, OUTRO])
    seen = _revision(tab)
    _save_tab(tab, [PAO])

    result = _send(
        balcao, at=_at(15, 30), client_request_id="pos:tirou",
        items=[PAO, OUTRO], tab_session_key=tab.session_key, expected_revision=seen,
        **_offline(_at(15), expected_total_q=2400),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 2400
    assert [row["kind"] for row in order.data["pos"]["offline"]["tab"]["adjusted"]] == ["removed_elsewhere"]


def test_comanda_ja_paga_inteira_nao_cobra_de_novo(balcao):
    from shopman.backstage.models import OperatorAlert

    tab = _open_tab()
    _save_tab(tab, [PAO])
    seen = _revision(tab)
    paid = _pay_tab_elsewhere(balcao, tab, [PAO])
    orders_before = Order.objects.count()
    body = {"items": [PAO], "tab_session_key": tab.session_key, "expected_revision": seen, **_offline(_at(15))}

    result = _send(balcao, at=_at(15, 30), client_request_id="pos:dobro", **body)
    again = _send(balcao, at=_at(15, 31), client_request_id="pos:dobro", **body)

    assert result.order_ref == paid.order_ref == again.order_ref
    assert Order.objects.count() == orders_before
    order = Order.objects.get(ref=paid.order_ref)
    duplicates = order.data["pos"]["offline_duplicates"]
    assert len(duplicates) == 1 and duplicates[0]["charged_total_q"] == 1200
    alert = OperatorAlert.objects.get(type="pos_offline_sale_adjusted", order_ref=order.ref)
    assert "cobrou de novo R$ 12,00" in alert.message
    assert "Devolva ao cliente." in alert.message


def test_comanda_paga_em_parte_sobe_so_o_que_nao_estava_pago(balcao):
    tab = _open_tab()
    _save_tab(tab, [PAO])
    seen = _revision(tab)
    paid = _pay_tab_elsewhere(balcao, tab, [PAO])

    result = _send(
        balcao, at=_at(15, 30), client_request_id="pos:parte",
        items=[PAO, OUTRO], tab_session_key=tab.session_key, expected_revision=seen,
        **_offline(_at(15), expected_total_q=2400),
    )

    assert result.order_ref != paid.order_ref
    order = Order.objects.get(ref=result.order_ref)
    assert [item.line_id for item in order.items.all()] == ["L-outro001"]
    assert order.total_q == 1200
    record = order.data["pos"]["offline"]["tab"]
    assert record["outcome"] == "already_paid"
    assert record["already_paid_q"] == 1200 and record["paid_order_ref"] == paid.order_ref
    # O livro do turno recebe só a venda nova: o dobro não é venda.
    assert balcao.sale_lines()[-1].amount_q == 1200


def test_relatorio_do_caixa_mostra_o_ajuste(balcao):
    from shopman.offerman.models import Product

    from shopman.backstage.projections.cash_session import _shift_reading

    Product.objects.filter(sku="PAO").update(base_price_q=1500)
    _send(balcao, at=_at(16), client_request_id="pos:relatorio", **_offline(_at(15)))

    reading = _shift_reading(balcao.shift)

    assert len(reading.offline_notes) == 1
    assert "Valeu o cobrado: R$ 3,00 abaixo do preço." in reading.offline_notes[0]
