"""Histórico do Gestor — GET /api/v1/backstage/orders/history/.

O pedido do dono (03/10/2026): "acesso a um histórico dos pedidos
concluídos/cancelados, com filtro por data, status, forma de pagamento". Estes
testes guardam que os recortes são aplicados NO SERVIDOR, que a contagem de cada
opção solta o próprio recorte, que a página corta, que o balcão do PDV fica de
fora e que só quem opera o Gestor lê.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections import order_history
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/orders/history/"


def _perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def manager(shop):
    user = User.objects.create_user("gestor", password="pw", is_staff=True)
    user.user_permissions.add(_perm())
    return user


@pytest.fixture
def plain_staff(shop):
    return User.objects.create_user("caixa", password="pw", is_staff=True)


def _at(day, hour=12):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)), timezone.get_current_timezone())


def _order(ref, *, status="completed", channel="web", method="pix", fulfillment="pickup", day=None, name="Ana", **data):
    day = day or timezone.localdate()
    payload = {"customer": {"name": name, "phone": "+5543999990000"}, "fulfillment_type": fulfillment}
    if method is not None:
        payload["payment"] = {"method": method}
    payload.update(data)
    order = Order.objects.create(ref=ref, channel_ref=channel, status=status, total_q=2500, data=payload)
    closed = {"completed": "completed_at", "cancelled": "cancelled_at", "returned": "returned_at"}.get(status)
    if closed:
        Order.objects.filter(pk=order.pk).update(**{closed: _at(day)})
    return order


@pytest.fixture
def orders(shop):
    Channel.objects.create(ref="web", name="Loja online")
    Channel.objects.create(ref="ifood", name="iFood")
    today = timezone.localdate()
    _order("H-1", method="pix")
    _order("H-2", method="card", fulfillment="delivery", name="Bruno")
    _order("H-3", status="cancelled", channel="ifood", method="external")
    _order("H-4", method="cash", day=today - timedelta(days=3))
    _order("H-5", method=None)  # pagamento não informado
    # Fora do histórico: ainda no quadro, e venda de balcão do PDV.
    _order("H-ACTIVE", status="preparing")
    _order("H-COUNTER", origin_channel="pos", pos={"sales_mode": "counter"})
    return today


def _get(client, user, **params):
    client.force_login(user)
    return client.get(URL, params)


def _refs(response):
    return [row["ref"] for row in response.json()["history"]["items"]]


def _facet(response, facet_id):
    facet = next(f for f in response.json()["history"]["facets"] if f["id"] == facet_id)
    return {option["value"]: option["count"] for option in facet["options"]}


def test_requires_manage_orders(client, plain_staff, manager, orders):
    assert _get(client, plain_staff).status_code == 403
    assert _get(client, manager).status_code == 200


def test_default_is_today_closed_orders_without_counter_sales(client, manager, orders):
    response = _get(client, manager)
    assert response.status_code == 200
    assert sorted(_refs(response)) == ["H-1", "H-2", "H-3", "H-5"]
    history = response.json()["history"]
    assert history["total"] == 4
    assert history["total_label"] == "4 pedidos"
    assert history["date_from"] == history["date_to"] == orders.isoformat()


def test_period_reaches_older_orders(client, manager, orders):
    response = _get(client, manager, date_from=(orders - timedelta(days=7)).isoformat(), date_to=orders.isoformat())
    assert "H-4" in _refs(response)


def test_multi_value_and_multi_field_filters(client, manager, orders):
    response = _get(client, manager, payment="pix,card")
    assert sorted(_refs(response)) == ["H-1", "H-2"]

    response = _get(client, manager, payment="pix,card", fulfillment="delivery")
    assert _refs(response) == ["H-2"]

    response = _get(client, manager, status="cancelled", channel="ifood")
    assert _refs(response) == ["H-3"]

    response = _get(client, manager, payment="none")
    assert _refs(response) == ["H-5"]


def test_facet_counts_release_their_own_filter(client, manager, orders):
    response = _get(client, manager, payment="pix")
    # O recorte de pagamento conta sem ele mesmo: marcar Pix não zera Cartão.
    payment = _facet(response, "payment")
    assert payment["pix"] == 1 and payment["card"] == 1 and payment["none"] == 1
    # Os outros recortes contam COM o Pix aplicado.
    assert _facet(response, "status") == {"completed": 1, "cancelled": 0}
    channel_labels = {
        o["value"]: o["label"] for o in next(f for f in response.json()["history"]["facets"] if f["id"] == "channel")["options"]
    }
    assert channel_labels["web"] == "Loja online"


def test_search_by_ref_and_customer(client, manager, orders):
    assert _refs(_get(client, manager, q="H-2")) == ["H-2"]
    assert _refs(_get(client, manager, q="brun")) == ["H-2"]


def test_row_contract(client, manager, orders):
    row = next(r for r in _get(client, manager, q="H-3").json()["history"]["items"])
    assert row["status"] == "cancelled"
    assert row["status_label"] == "Cancelado"
    assert row["status_tone"] == "danger"
    assert row["channel_label"] == "iFood"
    assert row["total_display"] == "R$ 25,00"
    assert row["closed_display"].endswith("12:00")


def test_pagination(client, manager, orders, monkeypatch):
    monkeypatch.setattr(order_history, "PAGE_SIZE", 2)
    first = _get(client, manager).json()["history"]
    second = _get(client, manager, page=2).json()["history"]
    assert first["has_next"] is True and len(first["items"]) == 2
    assert second["has_next"] is False and len(second["items"]) == 2
    assert not {row["ref"] for row in first["items"]} & {row["ref"] for row in second["items"]}


def test_invalid_input_speaks_the_error_dialect(client, manager, orders):
    response = _get(client, manager, status="preparing")
    assert response.status_code == 400
    assert response.json()["field"] == "status"
    assert "detail" in response.json()

    response = _get(client, manager, date_from="2026-10-03", date_to="2026-10-01")
    assert response.status_code == 400
    assert response.json()["field"] == "date_to"

    response = _get(client, manager, colour="blue")
    assert response.status_code == 400
    assert response.json()["field"] == "colour"
