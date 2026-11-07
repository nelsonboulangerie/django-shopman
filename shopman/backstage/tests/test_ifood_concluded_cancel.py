"""Pedido que o iFood já CONCLUIU não se cancela nem se recusa daqui.

Alpha, 07/11/2026, IFOOD-261107-3761: o CON chegou às 16:00:18 com o pedido
aceito aqui; às 16:02 o gerente tentou cancelar. A view foi ler os motivos de
cancelamento no iFood, que não os dá para pedido concluído, e respondeu 503
três vezes; a tela terminou em "Resultado ainda desconhecido". O fato
``data.ifood.remote_concluded`` já dizia a resposta: a recusa sai de antemão,
com a hora, e a ação nem é oferecida.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop
from shopman.shop.services.operator_orders import operational_revision

pytestmark = [pytest.mark.django_db, pytest.mark.channels("ifood")]

REGUA = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "completed", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["dispatched", "completed", "cancelled"],
    "cancelled": [],
}

CONCLUDED_AT = timezone.make_aware(timezone.datetime(2026, 11, 7, 13, 0, 18))


@pytest.fixture
def gerente(db):
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("gerente", password="pw", is_staff=True)
    ct = ContentType.objects.get(app_label="shop", model="shop")
    user.user_permissions.add(
        Permission.objects.get(content_type=ct, codename="manage_orders"),
        Permission.objects.get(content_type=ct, codename="cancel_advanced_order"),
    )
    return user


def _order(ref: str, status: str, *, concluded: bool = True) -> Order:
    ifood = {"order_code": "5695f008-test", "display_id": "3761"}
    if concluded:
        ifood["remote_concluded"] = {"event_id": "con-1", "observed_at": CONCLUDED_AT.isoformat()}
    order = Order.objects.create(
        ref=ref,
        channel_ref="ifood",
        external_ref=f"5695f008-{ref}",
        status=status,
        total_q=1500,
        data={"customer": {"name": "Ana"}, "payment": {"method": "external"}, "ifood": ifood},
        snapshot={"lifecycle": {"transitions": REGUA}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _post(client, user, order, operation: str):
    return client.post(
        reverse(f"api-backstage-order-{operation}", args=[order.ref]),
        data={
            "reason_key": "other",
            "expected_actor_id": user.pk,
            "base_revision": operational_revision(order),
            "idempotency_key": f"{operation}-{order.ref}",
        },
        content_type="application/json",
    )


def test_cancelar_concluido_no_ifood_recusa_com_a_hora_sem_consultar_o_ifood(client, gerente):
    order = _order("IFOOD-CON-CANCEL", "accepted")
    client.force_login(gerente)

    with patch("shopman.shop.services.ifood_callbacks.fetch_cancellation_reasons") as fetch:
        resp = _post(client, gerente, order, "cancel")

    assert resp.status_code == 409, resp.content
    body = resp.json()
    hora = f"{timezone.localtime(CONCLUDED_AT):%H:%M}"
    assert body["detail"] == f"O iFood já concluiu este pedido às {hora}. Não dá mais para cancelar."
    assert body["outcome"] == "not_applied"
    fetch.assert_not_called()
    order.refresh_from_db()
    assert order.status == "accepted"


def test_recusar_concluido_no_ifood_recusa_de_antemao(client, gerente):
    order = _order("IFOOD-CON-REJECT", "new")
    client.force_login(gerente)

    with patch("shopman.shop.services.ifood_callbacks.fetch_cancellation_reasons") as fetch:
        resp = _post(client, gerente, order, "reject")

    assert resp.status_code == 409, resp.content
    body = resp.json()
    assert "Não dá mais para recusar." in body["detail"]
    assert body["outcome"] == "not_applied"
    fetch.assert_not_called()


def test_a_acao_nem_e_oferecida_e_diz_por_que(gerente):
    from shopman.backstage.projections.order_queue import build_operator_order

    projecao = build_operator_order(_order("IFOOD-CON-CAP", "preparing"), user=gerente)

    assert projecao.can_cancel is False
    assert projecao.cancel_block_label.startswith("O iFood já concluiu este pedido às ")
    cancel = next(a for a in projecao.actions if a.ref == "cancel")
    assert cancel.enabled is False
    assert cancel.reason == projecao.cancel_block_label

    nova = build_operator_order(_order("IFOOD-CON-NEW", "new"), user=gerente)
    reject = next(a for a in nova.actions if a.ref == "reject")
    assert reject.enabled is False
    assert "recusar" in reject.reason


def test_sem_o_fato_o_cancelar_segue_oferecido(gerente):
    from shopman.backstage.projections.order_queue import build_operator_order

    projecao = build_operator_order(_order("IFOOD-SEM-CON", "preparing", concluded=False), user=gerente)

    assert projecao.can_cancel is True

