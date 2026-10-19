"""O GET do acompanhamento só lê; conferir o pagamento é o POST ``payment/check/``.

Antes (A8-1) o GET criava a cobrança, perguntava ao gateway, resolvia prazo
vencido e consumia a marca do confete. Leitura com efeito cobra até de quem só
abriu o link: a prévia do WhatsApp, um robô, a aba esquecida. Cada efeito foi
para o seu dono, e este arquivo prova as duas metades: o GET não mexe em nada,
e o POST faz o que o GET fazia pela tela que abre.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from shopman.shop.services import customer_orders
from shopman.shop.services import payment as payment_service

pytestmark = pytest.mark.django_db


def _set(order, *, status: str, payment: dict):
    from shopman.orderman.models import Order

    Order.objects.filter(pk=order.pk).update(status=status, data={"payment": payment})
    order.refresh_from_db()
    return order


def test_get_nao_cria_cobranca_e_o_post_cria(client, order):
    _set(order, status="accepted", payment={"method": "pix"})

    with patch.object(customer_orders.payment_service, "initiate") as initiate:
        assert client.get(f"/api/v1/tracking/{order.ref}/").status_code == 200
        initiate.assert_not_called()

        resposta = client.post(f"/api/v1/orders/{order.ref}/payment/check/")

    assert resposta.status_code == 200
    initiate.assert_called_once()
    assert resposta.json()["ref"] == order.ref


def test_get_nao_pergunta_ao_gateway_e_o_post_pergunta(client, order):
    _set(order, status="accepted", payment={"method": "card", "intent_ref": "pi_1", "checkout_url": "https://pay"})

    with patch.object(payment_service, "reconcile_with_gateway_if_due", return_value=False) as reconcile:
        client.get(f"/api/v1/tracking/{order.ref}/")
        reconcile.assert_not_called()

        client.post(f"/api/v1/orders/{order.ref}/payment/check/")

    reconcile.assert_called_once()


def test_get_nao_resolve_prazo_vencido(client, order):
    """O prazo vencido é a directive do worker; a leitura só mostra."""
    from shopman.orderman.models import Directive

    from shopman.shop.directives import PAYMENT_TIMEOUT

    _set(order, status="accepted", payment={"method": "pix", "intent_ref": "pix_1", "copy_paste": "000201"})
    directive = Directive.objects.create(
        topic=PAYMENT_TIMEOUT,
        payload={"order_ref": order.ref},
        available_at=timezone.now() - timedelta(minutes=1),
    )

    assert client.get(f"/api/v1/tracking/{order.ref}/").status_code == 200

    directive.refresh_from_db()
    assert directive.status == Directive.Status.QUEUED
    assert directive.attempts == 0


def test_get_nao_grava_no_pedido(client, order):
    _set(order, status="accepted", payment={"method": "pix"})
    antes = (order.data, order.updated_at)

    client.get(f"/api/v1/tracking/{order.ref}/")

    order.refresh_from_db()
    assert (order.data, order.updated_at) == antes


def test_post_de_pedido_alheio_e_404(client):
    assert client.post("/api/v1/orders/NAO-EXISTE/payment/check/").status_code == 404


def test_tentar_novamente_e_comando_e_nao_recarga(order):
    """O botão do erro de cobrança pede a conferência (POST), não recarrega a tela."""
    from shopman.shop.projections.order_tracking import _payment_retry_promise

    (action,) = _payment_retry_promise(order, method="pix").actions

    assert (action.ref, action.kind, action.method) == ("retry_payment", "mutation", "POST")
    assert action.href == f"/api/v1/orders/{order.ref}/payment/check/"
