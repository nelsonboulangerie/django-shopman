"""Os links que o aviso de pedido leva: os COMUNS do pedido, sem credencial (OC-01).

Decisão D5 do dono (23/11/2026): o aviso leva ``/pedido/<ref>``, nunca um link de
entrada (``/a?t=<token>``). Mensagem se encaminha, e um link que entrasse na conta
entregaria a conta a quem recebesse o encaminhamento. Quem é o dono abre direto no
próprio celular (sessão ou dispositivo confiável); em outro dispositivo, a loja pede
a entrada e volta para o mesmo pedido.

A prova de ponta a ponta (texto renderizado de todo aviso, encaminhado, dono,
outro dispositivo) mora em
``shopman/storefront/tests/security/test_aviso_de_pedido_sem_credencial.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

CUSTOMER_UUID = UUID("12345678-1234-5678-1234-567812345678")


def _order(*, ref: str = "ORD-001", customer: dict | None = None, payment: dict | None = None):
    order = MagicMock()
    order.ref = ref
    order.total_q = 3000
    order.status = "accepted"
    order.data = {"fulfillment_type": "pickup"}
    if customer is not None:
        order.data["customer"] = customer
    if payment is not None:
        order.data["payment"] = payment
    order.snapshot = {"items": []}
    return order


class TestNotificationContextLinks:
    def test_cliente_identificado_recebe_o_link_comum_e_nada_e_cunhado(self, settings):
        """O pedido com ``customer.uuid`` era o que cunhava link de entrada. Não cunha mais."""
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _order(customer={"uuid": str(CUSTOMER_UUID), "name": "Ana", "phone": "+5511999990001"})
        with patch("shopman.doorman.services.access_link.AccessLinkService.create_token") as create:
            ctx = _build_context(order, {"order_ref": "ORD-001"}, "order_accepted")

        assert not create.called, "aviso de pedido não cunha link de entrada"
        assert ctx["tracking_url"] == "https://shop.test/pedido/ORD-001"
        assert ctx["payment_url"] == "https://shop.test/pedido/ORD-001"
        assert ctx["reorder_url"] == "https://shop.test/conta/pedidos"

    def test_pedido_sem_cliente_identificado_recebe_os_mesmos_links(self, settings):
        """O pedido da loja não grava ``customer.uuid``: o link é o mesmo, nunca some."""
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _order(ref="ORD-002", customer={"name": "Bob"})
        ctx = _build_context(order, {"order_ref": "ORD-002"}, "order_accepted")
        assert ctx["tracking_url"] == "https://shop.test/pedido/ORD-002"
        assert ctx["payment_url"] == "https://shop.test/pedido/ORD-002"
        assert ctx["reorder_url"] == "https://shop.test/conta/pedidos"

        ctx = _build_context(_order(ref="ORD-003"), {}, "order_accepted")
        assert ctx["tracking_url"] == "https://shop.test/pedido/ORD-003"

    def test_pagar_e_a_tela_do_pedido_e_o_pix_vai_no_texto(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _order(
            ref="ORD-PIX",
            customer={"uuid": str(CUSTOMER_UUID), "name": "Ana"},
            payment={"method": "pix", "copy_paste": "000201PIX", "checkout_url": ""},
        )
        ctx = _build_context(order, {"order_ref": "ORD-PIX"}, "payment_requested")
        assert ctx["payment_url"] == "https://shop.test/pedido/ORD-PIX"
        assert ctx["pix_suffix"] == " Código PIX: 000201PIX"

    def test_uuid_torto_no_pedido_ainda_entrega_o_link_comum(self, settings):
        """Garantia herdada do antigo bloco de link de entrada: dado torto no pedido nunca
        vira ``{tracking_url}`` cru na tela do cliente. Agora o uuid nem é lido."""
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _order(ref="ORD-TORTO", customer={"uuid": "nao-e-um-uuid", "name": "Ana"})
        ctx = _build_context(order, {"order_ref": "ORD-TORTO"}, "order_received")
        assert ctx["tracking_url"] == "https://shop.test/pedido/ORD-TORTO"
        assert ctx["payment_url"] == "https://shop.test/pedido/ORD-TORTO"
        assert ctx["reorder_url"] == "https://shop.test/conta/pedidos"

    def test_cofre_de_token_fora_do_ar_nao_afeta_o_aviso(self, settings):
        """Garantia herdada: cunhagem de token fora do ar não pode sumir com o link do
        aviso. Agora o aviso nem passa por ela."""
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _order(ref="ORD-COFRE", customer={"uuid": str(CUSTOMER_UUID), "name": "Ana"})
        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            side_effect=RuntimeError("token store fora do ar"),
        ) as create:
            ctx = _build_context(order, {"order_ref": "ORD-COFRE"}, "order_received")

        assert not create.called
        assert ctx["tracking_url"] == "https://shop.test/pedido/ORD-COFRE"
        assert ctx["payment_url"] == "https://shop.test/pedido/ORD-COFRE"

    def test_nao_ha_gemea_publica_dos_links_do_pedido(self, settings):
        """O link do aviso JÁ é o comum: não existe chave ``<nome>_public`` para ele."""
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _order(customer={"uuid": str(CUSTOMER_UUID)})
        ctx = _build_context(order, {"order_ref": "ORD-001"}, "order_accepted")
        assert not [key for key in ctx if key.endswith("_public")]


class TestManychatMessageLinks:
    def _build(self, template: str, **extra_ctx):
        from shopman.shop.adapters.notification_manychat import _build_message

        ctx = {"order_ref": "ORD-042", "customer_name": "Ana", "order_total_display": "R$ 30,00"}
        ctx.update(extra_ctx)
        with patch("shopman.shop.adapters._notification_templates.db_template", return_value=(None, None)):
            return _build_message(template, ctx)

    def test_tracking_url_goes_in_the_message(self):
        msg = self._build("order_accepted", tracking_url="https://shop.test/pedido/ORD-042")
        assert "Acompanhe por aqui: https://shop.test/pedido/ORD-042" in msg

    def test_tracking_url_none_renders_cleanly(self):
        msg = self._build("order_accepted", tracking_url=None)
        assert "None" not in msg
        assert "{tracking_url}" not in msg
