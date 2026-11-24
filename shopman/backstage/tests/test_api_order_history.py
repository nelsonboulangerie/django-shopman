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
    assert history["total_label"] == "4 pedidos hoje"
    assert history["period_label"] == "hoje"
    assert history["today"] == orders.isoformat()
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


def test_search_by_ifood_number_when_the_ref_was_drawn(client, manager, orders):
    """P2-29: sufixo ocupado, o ref é sorteado; o número do iFood continua achando."""
    _order("IFOOD-261013-D09", channel="ifood", method="external", ifood={"display_id": "4994"})
    assert _refs(_get(client, manager, q="4994")) == ["IFOOD-261013-D09"]


def test_row_contract(client, manager, orders):
    row = next(r for r in _get(client, manager, q="H-3").json()["history"]["items"])
    assert row["status"] == "cancelled"
    assert row["status_label"] == "Cancelado"
    assert row["status_tone"] == "danger"
    assert row["channel_label"] == "iFood"
    assert row["total_display"] == "R$ 25,00"
    assert row["closed_display"].endswith("12h")
    assert row["closed_label"] == "Cancelado hoje às 12h"
    # iFood: o dinheiro não passa pela casa, a linha não inventa destino.
    assert row["money_outcome"] == ""


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


def test_ordered_basis_counts_by_the_day_the_order_was_made(client, manager, shop):
    """ge:BI-03: o "Abrir os N pedidos" do B.I. conta pela hora da venda.

    A encomenda feita ontem e retirada hoje fecha hoje; pelo eixo do B.I.
    (``date_basis=ordered``) ela é de ontem, e é ontem que o link abre.
    """
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    order = _order("H-PRE", day=today)
    Order.objects.filter(pk=order.pk).update(created_at=_at(yesterday, 9))

    closed = _get(client, manager, date_from=yesterday.isoformat(), date_to=yesterday.isoformat())
    ordered = _get(
        client, manager, date_from=yesterday.isoformat(), date_to=yesterday.isoformat(), date_basis="ordered"
    )
    assert "H-PRE" not in _refs(closed)
    assert _refs(ordered) == ["H-PRE"]
    assert _get(client, manager, date_basis="sideways").json()["field"] == "date_basis"


def test_ordered_basis_is_the_agreed_day_of_a_preorder(client, manager, shop):
    """#3427: a encomenda feita ontem para hoje é venda de hoje no B.I., e é hoje
    que o "Abrir os N pedidos" (``date_basis=ordered``) a abre."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    order = _order("H-AGREED", day=today)
    Order.objects.filter(pk=order.pk).update(
        created_at=_at(yesterday, 9), data={**order.data, "delivery_date": today.isoformat()},
    )

    on_today = _get(client, manager, date_from=today.isoformat(), date_to=today.isoformat(), date_basis="ordered")
    on_yesterday = _get(
        client, manager, date_from=yesterday.isoformat(), date_to=yesterday.isoformat(), date_basis="ordered"
    )
    assert "H-AGREED" in _refs(on_today)
    assert "H-AGREED" not in _refs(on_yesterday)


def test_history_and_detail_show_the_edited_total(client, manager, orders):
    """G20: o histórico fechado não volta ao total selado antes da edição."""
    from shopman.shop.projections.order_tracking import build_tracking
    from shopman.shop.services import order_composition

    order = Order.objects.create(
        ref="H-EDITED", channel_ref="web", status="completed", total_q=800,
        completed_at=timezone.now(), data={"fulfillment_type": "pickup"},
    )
    adjustment = order_composition.record(
        order, items=[{"line_id": "bread", "sku": "PAO", "name": "Pão",
                       "qty": 1, "unit_price_q": 1700, "line_total_q": 1700}],
        total_q=1700, source="pos", event_id="edit-history-regression",
    )
    order.data = {**order.data, order_composition.KEY: adjustment}
    order.save(update_fields=["data"])

    response = _get(client, manager, q=order.ref)

    assert response.status_code == 200
    [row] = response.json()["history"]["items"]
    assert row["total_q"] == build_tracking(order).total_q == 1700
    assert row["total_display"] == "R$ 17,00"
    order.refresh_from_db()
    assert order.total_q == 800


# ── WP-G04: Histórico honesto (P1-21, P2-23) ─────────────────────────────────


def test_search_that_finds_nothing_says_where_it_looked(client, manager, orders):
    """P1-21: a busca presa a hoje diz que procurou só em hoje."""
    _order("H-ONTEM", name="Carla Souza", day=orders - timedelta(days=1))

    today_only = _get(client, manager, q="carla").json()["history"]
    assert today_only["total"] == 0
    assert today_only["total_label"] == "Nenhum pedido com “carla” hoje"

    wider = _get(
        client, manager, q="carla", date_from=(orders - timedelta(days=27)).isoformat(), date_to=orders.isoformat()
    ).json()["history"]
    assert [row["ref"] for row in wider["items"]] == ["H-ONTEM"]
    assert wider["total_label"] == f"1 pedido de {(orders - timedelta(days=27)):%d/%m} até hoje"
    assert wider["items"][0]["closed_label"] == "Concluído ontem às 12h"


def test_period_words():
    from datetime import date

    today = date(2026, 11, 16)
    words = order_history.period_words
    assert words(today, today, today) == "hoje"
    assert words(date(2026, 11, 15), date(2026, 11, 15), today) == "ontem"
    assert words(date(2026, 11, 12), date(2026, 11, 12), today) == "em 12/11"
    assert words(date(2026, 10, 20), today, today) == "de 20/10 até hoje"
    assert words(date(2026, 11, 9), date(2026, 11, 15), today) == "de 09/11 até ontem"
    assert words(date(2026, 11, 1), date(2026, 11, 7), today) == "de 01/11 a 07/11"
    assert words(date(2025, 12, 1), date(2025, 12, 1), today) == "em 01/12/2025"


def test_day_is_the_stamp_of_the_current_status(client, manager, orders):
    """P2-23: o devolvido depois de concluído conta no dia da devolução."""
    order = _order("H-RET", status="returned", day=orders)
    Order.objects.filter(pk=order.pk).update(completed_at=_at(orders - timedelta(days=5)))
    late_cancel = _order("H-LATE", status="cancelled", day=orders)
    Order.objects.filter(pk=late_cancel.pk).update(completed_at=_at(orders - timedelta(days=2)))

    today_refs = _refs(_get(client, manager))
    assert "H-RET" in today_refs and "H-LATE" in today_refs
    five_days_ago = (orders - timedelta(days=5)).isoformat()
    assert "H-RET" not in _refs(_get(client, manager, date_from=five_days_ago, date_to=five_days_ago))
    row = next(r for r in _get(client, manager, q="H-RET").json()["history"]["items"])
    assert row["closed_label"] == "Devolvido hoje às 12h"


def _paid(order, method, amount_q=2500, refund_q=0):
    from shopman.payman import PaymentService

    intent = PaymentService.create_intent(order.ref, amount_q, method, ref=f"INT-{order.ref}")
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    if refund_q:
        PaymentService.refund(intent.ref, amount_q=refund_q)
    return intent


def test_cancelled_row_says_where_the_money_went(client, manager, orders):
    """P2-23: o cancelado não lê "Pix · R$ 25,00" igual a um concluído."""
    _paid(_order("H-REFUNDED", status="cancelled", method="pix"), "pix", refund_q=2500)
    _paid(_order("H-PENDING", status="cancelled", method="pix"), "pix")
    _paid(_order("H-PARTIAL", status="returned", method="card"), "card", refund_q=1000)
    _paid(_order("H-CASH", status="cancelled", method="cash"), "cash")
    _order("H-NEVER", status="cancelled", method="pix")
    _paid(_order("H-DONE", status="completed", method="pix"), "pix")

    rows = {row["ref"]: row for row in _get(client, manager, q="H-").json()["history"]["items"]}
    outcome = {ref: (row["money_outcome"], row["money_outcome_pending"]) for ref, row in rows.items()}
    assert outcome["H-REFUNDED"] == ("R$ 25,00 estornado", False)
    assert outcome["H-PENDING"] == ("R$ 25,00 a estornar", True)
    assert outcome["H-PARTIAL"] == ("R$ 10,00 de R$ 25,00 estornado, R$ 15,00 a estornar", True)
    assert outcome["H-CASH"] == ("R$ 25,00 a devolver", True)
    assert outcome["H-NEVER"] == ("Nada foi cobrado", False)
    assert outcome["H-DONE"] == ("", False)


def test_journey_j7_find_yesterdays_order(client, manager, orders):
    """J7: o Gerente busca pelo nome, amplia para 28 dias e abre o pedido."""
    _order("H-J7", name="Marta Lima", day=orders - timedelta(days=1))

    first = _get(client, manager, q="Marta").json()["history"]
    assert first["items"] == []
    assert first["period_label"] == "hoje"

    wider = _get(
        client, manager, q="Marta", date_from=(orders - timedelta(days=27)).isoformat(), date_to=orders.isoformat()
    ).json()["history"]
    [row] = wider["items"]
    assert row["ref"] == "H-J7"
    assert row["customer_label"].startswith("Marta")

    detail = client.get(f"/api/v1/backstage/orders/{row['ref']}/")
    assert detail.status_code == 200, detail.content
