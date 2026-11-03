"""Venda "sem conexão" cobrada por um preço que o catálogo não explica (dono, 03/11/2026).

A regra D (dono, 10/10/2026) diz que na venda feita sem conexão vale o preço que foi
cobrado. O servidor não prova que o dispositivo estava mesmo sem conexão: o
``offline_captured_at`` vem do corpo. Um dispositivo com conexão que se declarasse
"sem conexão" selava o pedido no preço que escolhesse (R$ 0,01 por um pão de R$ 12),
e só sobrava o aviso ao gerente depois.

A decisão do dono, sem tolerância percentual (seria arbitrária):

- o preço de referência é o do CATÁLOGO, lido do histórico de preços, na hora da
  tabela da tela (``offline_prices_at``) e na hora da cobrança;
- o cobrado que bate com um desses é limpo (a venda sem conexão não tem desconto,
  taxa nem entrega: não há outra fonte legítima de diferença);
- o que não bate ENTRA (o dinheiro já está na gaveta), fica "a conferir", e o
  turno só fecha com o gerente (da lista, uma autorização, PIN no servidor);
- a hora da tabela é plausível ou não vale: no futuro, depois da cobrança ou de
  antes do turno, a venda segue a régua de sempre.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.doorman.models import PinCredential
from shopman.orderman.models import Order

from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db

BRT = ZoneInfo("America/Sao_Paulo")
DIA = datetime(2026, 10, 10, tzinfo=BRT)


def _at(hour: int, minute: int = 0, *, day: int = 0) -> datetime:
    return DIA.replace(hour=hour, minute=minute) + timedelta(days=day)


@pytest.fixture
def counter():
    return _Counter()


@pytest.fixture
def balcao():
    """O balcão com o turno aberto às 7h; o pão (R$ 12) entrou no catálogo às 6h."""
    with patch("django.utils.timezone.now", return_value=_at(6)):
        counter = _Counter()
    Shift.objects.filter(pk=counter.shift.pk).update(opened_at=_at(7))
    counter.shift.refresh_from_db()
    cache.clear()
    yield counter
    cache.clear()


def _send(counter, *, at: datetime, **overrides):
    with patch("django.utils.timezone.now", return_value=at):
        return counter.close(**overrides)


def _forged(counter, *, at=None, key="audit-offline-forged"):
    captured = (at or timezone.now()) - timedelta(minutes=1)
    return counter.close(
        client_request_id=key,
        items=[{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1}],
        offline_captured_at=captured.isoformat(),
        offline_prices_at=(captured - timedelta(minutes=1)).isoformat(),
        expected_total_q=1,
    )


def _manager(username="gerente-conf", pin="4321"):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username, password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="adjust_shift"))
    PinCredential.set_for(user, pin)
    return get_user_model().objects.get(pk=user.pk)


def _closer():
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user("fecha-dia", password="x", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="operate_pos"), Permission.objects.get(codename="perform_closing"),
    )
    return get_user_model().objects.get(pk=user.pk)


# ── Preço forjado: entra, a conferir, e o caixa só fecha com o gerente ────────


def test_preco_forjado_entra_e_fica_a_conferir(counter):
    from shopman.backstage.models import OperatorAlert

    result = _forged(counter)

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1, "a venda entra pelo cobrado: o dinheiro já está na gaveta"
    pricing = order.data["pos"]["offline"]["pricing"]
    assert pricing["review_required"] is True
    assert pricing["operator"] == "marina"
    (line,) = pricing["review_lines"]
    assert line["sku"] == "PAO"
    assert line["charged_line_total_q"] == 1
    assert line["catalog_line_total_q"] == 1200
    alert = OperatorAlert.objects.get(type="pos_offline_sale_adjusted", order_ref=order.ref)
    assert "A conferir" in alert.message


def test_caixa_com_venda_a_conferir_so_fecha_com_o_gerente(counter):
    from shopman.backstage.services import pos as pos_service

    result = _forged(counter)
    manager = _manager()
    closer = _closer()
    terminal = counter.shift.terminal.ref

    with pytest.raises(PosIntentError) as refused:
        pos_service.close_cash_shift(actor_user=closer, closing_amount_raw="100,01", terminal_ref=terminal)
    assert refused.value.code == "manager_approval_required"
    assert "1 venda sem conexão está a conferir" in refused.value.message
    counter.shift.refresh_from_db()
    assert counter.shift.status == Shift.Status.OPEN

    with pytest.raises(PosIntentError) as wrong:
        pos_service.close_cash_shift(
            actor_user=closer, closing_amount_raw="100,01", terminal_ref=terminal,
            manager_approval={"username": manager.username, "pin": "0000"},
        )
    assert wrong.value.code == "manager_approval_invalid"
    # O erro do PIN fica gravado: a recusa não desfaz a tentativa (trava do #2105).
    assert PinCredential.objects.get(user=manager).attempts == 1

    pos_service.close_cash_shift(
        actor_user=closer, closing_amount_raw="100,01", terminal_ref=terminal,
        manager_approval={"username": manager.username, "pin": "4321"},
    )

    counter.shift.refresh_from_db()
    assert counter.shift.status == Shift.Status.CLOSED
    pricing = Order.objects.get(ref=result.order_ref).data["pos"]["offline"]["pricing"]
    assert pricing["acknowledged_by"] == manager.username


def test_fechamento_lista_a_venda_a_conferir(counter):
    from shopman.backstage.projections.pos import _offline_review_sales

    result = _forged(counter)

    (row,) = _offline_review_sales(counter.shift)
    assert row.order_ref == result.order_ref
    assert row.sku == "PAO"
    assert row.catalog_price_display == "R$ 12,00"
    assert row.charged_price_display == "R$ 0,01"
    assert row.operator == "marina"


def test_api_do_fechamento_pede_o_gerente_com_codigo(client, counter):
    from shopman.backstage.tests.pos_test_runtime import bind_station

    _forged(counter)
    manager = _manager()
    client.force_login(_closer())
    bind_station(client, counter.shift.terminal.ref)

    def post(**extra):
        body = {"closing_amount": "100,01", "client_request_id": str(uuid.uuid4()), **extra}
        return client.post("/api/v1/backstage/pos/cash/close/", data=json.dumps(body), content_type="application/json")

    refused = post()
    assert refused.status_code == 422, refused.content
    assert refused.json()["error"]["code"] == "manager_approval_required"

    wrong = post(manager_approval={"username": manager.username, "pin": "0000"})
    assert wrong.json()["error"]["code"] == "manager_approval_invalid"
    assert PinCredential.objects.get(user=manager).attempts == 1

    ok = post(manager_approval={"username": manager.username, "pin": "4321"})
    assert ok.status_code == 200, ok.content
    counter.shift.refresh_from_db()
    assert counter.shift.status == Shift.Status.CLOSED


def test_caixa_sem_venda_a_conferir_fecha_sem_gerente(counter):
    from shopman.backstage.services import pos as pos_service

    counter.close(client_request_id="online-ok")

    pos_service.close_cash_shift(
        actor_user=_closer(), closing_amount_raw="112,00", terminal_ref=counter.shift.terminal.ref,
    )
    counter.shift.refresh_from_db()
    assert counter.shift.status == Shift.Status.CLOSED


def test_online_sale_forged_unit_price_is_refused(counter):
    """Controle: sem a marca de "sem conexão", o preço do navegador não vale."""
    with pytest.raises(PosIntentError):
        counter.close(
            client_request_id="audit-direct-forged",
            items=[{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1}],
            expected_total_q=1,
        )


# ── Catálogo mudado durante a queda: limpo ───────────────────────────────────


def test_preco_editado_durante_a_queda_explica_o_cobrado(balcao):
    from shopman.offerman.models import Product

    # A tela leu a tabela às 14h (R$ 12), a rede caiu, o gestor subiu o pão para
    # R$ 15 às 15h10, e a venda das 15h foi cobrada pelo preço da tela.
    with patch("django.utils.timezone.now", return_value=_at(15, 10)):
        product = Product.objects.get(sku="PAO")
        product.base_price_q = 1500
        product.save()

    result = _send(
        balcao, at=_at(16), client_request_id="pos:queda-catalogo",
        offline_captured_at=_at(15).isoformat(), offline_prices_at=_at(14).isoformat(), expected_total_q=1200,
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200
    pricing = order.data["pos"]["offline"]["pricing"]
    assert pricing["difference_q"] == -300  # a diferença para o catálogo de agora segue registrada
    assert "review_required" not in pricing


def test_preco_editado_entre_a_tabela_e_a_cobranca_explica_pela_hora_da_cobranca(balcao):
    from shopman.offerman.models import Listing, ListingItem, Product

    # Vitrine do canal: R$ 11 de manhã, R$ 10 às 14h30 (a tela, sem conexão desde
    # as 14h, ainda pode ter cobrado qualquer um dos dois), R$ 13 às 15h30.
    product = Product.objects.get(sku="PAO")
    with patch("django.utils.timezone.now", return_value=_at(6)):
        listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
        item = ListingItem.objects.create(listing=listing, product=product, price_q=1100)
    for hour, minute, price in ((14, 30, 1000), (15, 30, 1300)):
        with patch("django.utils.timezone.now", return_value=_at(hour, minute)):
            item.price_q = price
            item.save()

    line = {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1000}
    result = _send(
        balcao, at=_at(16), client_request_id="pos:entre", items=[line],
        offline_captured_at=_at(15).isoformat(), offline_prices_at=_at(14).isoformat(), expected_total_q=1000,
    )

    pricing = Order.objects.get(ref=result.order_ref).data["pos"]["offline"]["pricing"]
    assert "review_required" not in pricing


# ── A hora da tabela tem de ser plausível ────────────────────────────────────


def _table_cheaper_yesterday():
    """O pão custou R$ 9 das 6h10 às 6h50; voltou a R$ 12 antes de o turno abrir (7h)."""
    from shopman.offerman.models import Product

    product = Product.objects.get(sku="PAO")
    for at, price in ((_at(6, 10), 900), (_at(6, 50), 1200)):
        with patch("django.utils.timezone.now", return_value=at):
            product.base_price_q = price
            product.save()


@pytest.mark.parametrize(
    ("prices_at", "why"),
    [
        (_at(6, 20), "antes do turno"),
        (_at(17, 0), "no futuro e depois da cobrança"),
        (_at(15, 30), "depois da cobrança"),
    ],
)
def test_tabela_implausivel_segue_a_regra_de_sempre(balcao, prices_at, why):
    _table_cheaper_yesterday()
    line = {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 900}

    with pytest.raises(PosIntentError) as refused:
        _send(
            balcao, at=_at(16), client_request_id=f"pos:tabela-{len(why)}", items=[line],
            offline_captured_at=_at(15).isoformat(), offline_prices_at=prices_at.isoformat(), expected_total_q=900,
        )

    assert refused.value.code == "total_changed", why
    assert not Order.objects.filter(data__client_request_id=f"pos:tabela-{len(why)}").exists()


def test_tabela_de_ontem_sem_turno_segue_a_regra_de_sempre():
    from shopman.shop.services import pos_offline_sale

    payload = {
        "items": [{"sku": "PAO", "qty": 1, "unit_price_q": 900}],
        "payment_method": "cash",
        "offline_captured_at": _at(15).isoformat(),
        "offline_prices_at": _at(14, day=-2).isoformat(),
    }
    assert pos_offline_sale.pricing_instant(payload, now=_at(16)) is None
    payload["offline_prices_at"] = _at(14).isoformat()
    assert pos_offline_sale.pricing_instant(payload, now=_at(16)) == _at(15)

