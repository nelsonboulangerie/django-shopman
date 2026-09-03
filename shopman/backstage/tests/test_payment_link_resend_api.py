"""As duas portas do reenvio do link de pagamento (PDV e gestor).

O gesto é do operador, e ele está em dois lugares quando o cliente diz "não
chegou": na tela de resultado do PDV (``cashman.operate_pos``) e no detalhe do
pedido no gestor (``shop.manage_orders``). As duas portas chamam o MESMO
service; aqui se prova o contrato HTTP — 200 com a prova de envio, recusa no
dialeto ``{detail, error: {code, message}}``, permissão e 404.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.orderman.models import Directive, Order

from shopman.shop.models import Channel, Shop
from shopman.shop.services import notification as notification_svc

POS_URL = "/api/v1/backstage/pos/orders/{ref}/resend-payment-link/"
GESTOR_URL = "/api/v1/backstage/orders/{ref}/resend-payment-link/"
CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_api"


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"
    )


def _operate_pos_perm() -> Permission:
    return Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos")


def _link_order(ref: str, **payment_extra) -> Order:
    payment = {"method": "link", "amount_q": 1500, "checkout_url": CHECKOUT_URL}
    payment.update(payment_extra)
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        session_key=f"s-{ref}",
        status=Order.Status.ACCEPTED,
        total_q=1500,
        data={"customer": {"name": "Ana", "phone": "+5543999990002"}, "fulfillment_type": "pickup", "payment": payment},
    )


def _directives(ref: str):
    return Directive.objects.filter(topic=notification_svc.TOPIC, payload__template="payment_link_sent", payload__order_ref=ref)


def _delivered_long_ago(order: Order) -> None:
    """Envio original entregue há mais de um minuto: o reenvio passa pela cadência."""
    notification_svc.send(order, "payment_link_sent")
    (original,) = _directives(order.ref)
    original.status = "done"
    original.save(update_fields=["status", "updated_at"])
    Directive.objects.filter(pk=original.pk).update(created_at=timezone.now() - timedelta(minutes=2))


class _ResendContract:
    """O contrato comum às duas portas — mixin, para o unittest não o coletar sozinho."""

    url: str
    client: object

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
        User = get_user_model()
        self.operator = User.objects.create_user("op-resend", password="x", is_staff=True)
        self.operator.user_permissions.add(self.perm_object())
        self.plain_staff = User.objects.create_user("plain-resend", password="x", is_staff=True)
        self.client.force_login(self.operator)

    def perm_object(self) -> Permission:  # pragma: no cover — subclasses
        raise NotImplementedError

    def post(self, ref: str):
        return self.client.post(self.url.format(ref=ref), data="{}", content_type="application/json")

    # ── contrato ──

    def test_reenvia_e_devolve_a_prova_de_envio(self) -> None:
        order = _link_order("LNK-1")
        _delivered_long_ago(order)

        response = self.post("LNK-1")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["detail"], "Link reenviado ao cliente.")
        self.assertEqual(body["payment_link_notice"], "Enviando o link ao cliente…")
        self.assertEqual(_directives("LNK-1").count(), 2)

    def test_recusa_fala_o_dialeto_da_casa(self) -> None:
        order = _link_order("LNK-2")
        notification_svc.send(order, "payment_link_sent")  # ainda na fila

        response = self.post("LNK-2")

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertIn("detail", body)
        self.assertEqual(body["error"]["code"], "payment_link_send_pending")
        self.assertEqual(body["error"]["message"], body["detail"])
        self.assertEqual(_directives("LNK-2").count(), 1)

    def test_link_vencido_recusa_com_o_codigo(self) -> None:
        _link_order("LNK-3", expires_at=(timezone.now() - timedelta(minutes=1)).isoformat())

        response = self.post("LNK-3")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "payment_link_expired")

    def test_pedido_sem_link_recusa(self) -> None:
        _link_order("LNK-4", method="cash", checkout_url="")

        response = self.post("LNK-4")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "payment_link_unavailable")

    def test_pedido_inexistente_e_404(self) -> None:
        response = self.post("LNK-NOPE")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(set(response.json()), {"detail"})

    def test_staff_sem_a_permissao_e_barrado(self) -> None:
        order = _link_order("LNK-5")
        _delivered_long_ago(order)
        self.client.force_login(self.plain_staff)

        response = self.post("LNK-5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(_directives("LNK-5").count(), 1)


class POSResendPaymentLinkTests(_ResendContract, TestCase):
    url = POS_URL

    def perm_object(self) -> Permission:
        return _operate_pos_perm()


class GestorResendPaymentLinkTests(_ResendContract, TestCase):
    url = GESTOR_URL

    def perm_object(self) -> Permission:
        return _manage_orders_perm()

    def test_o_detalhe_do_pedido_expoe_o_botao_e_a_prova(self) -> None:
        order = _link_order("LNK-6")
        _delivered_long_ago(order)

        response = self.client.get(f"/api/v1/backstage/orders/{order.ref}/")

        self.assertEqual(response.status_code, 200)
        detail = response.json()["order"]
        self.assertTrue(detail["can_resend_payment_link"])
        self.assertTrue(detail["payment_link_notice"].startswith("Link enviado às "))

    def test_o_detalhe_esconde_o_botao_de_quem_nao_e_link(self) -> None:
        _link_order("LNK-7", method="cash", checkout_url="")

        detail = self.client.get("/api/v1/backstage/orders/LNK-7/").json()["order"]

        self.assertFalse(detail["can_resend_payment_link"])
        self.assertEqual(detail["payment_link_notice"], "")
