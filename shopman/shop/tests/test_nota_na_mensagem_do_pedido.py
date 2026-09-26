"""A nota da loja online vai DENTRO da mensagem que o cliente já recebe.

Decisão do dono (25/09/2026): menos mensagens. O link da NFC-e vai na mensagem
de status que sai quando a nota já existe (pronto para retirada, saiu para
entrega, entregue); o aviso avulso ``fiscal_note_ready`` só sai quando a nota
autoriza DEPOIS da última mensagem que a levaria. Uma nota, no máximo uma
menção por pedido.

A matriz: nota antes/depois de cada mensagem, em retirada e entrega, e nunca
duas vezes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters import notification_sms
from shopman.shop.services import notification

pytestmark = pytest.mark.django_db

DANFE = "https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe1.html"
NOTE = {
    "nfce_access_key": "4" * 44,
    "nfce_danfe_url": DANFE,
}


@pytest.fixture(autouse=True)
def _web_channel(settings):
    from shopman.shop.models import Channel

    settings.SHOPMAN_FOCUS_NFE = {"environment": "producao"}
    settings.SHOPMAN_STOREFRONT_CHANNEL_REF = "web"
    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja", "config": {}})
    Channel.objects.update_or_create(ref="pdv", defaults={"name": "Balcão", "config": {}})


def _order(*, fulfillment: str, status: str, channel: str = "web", ref: str = "NF-1") -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref=channel,
        status=status,
        total_q=1600,
        handle_type="phone",
        handle_ref="5543999990001",
        data={
            "fulfillment_type": fulfillment,
            "customer": {"name": "Ana", "phone": "+5543999990001"},
        },
    )


def _authorize(order: Order) -> None:
    """A nota autorizada, gravada como o handler grava, e o aviso decidido."""
    Order.objects.filter(pk=order.pk).update(data={**order.data, **NOTE})
    order.refresh_from_db()
    notification.send_fiscal_note_unless_carried(order)


def _status(order: Order, status: str) -> None:
    Order.objects.filter(pk=order.pk).update(status=status)
    order.refresh_from_db()


def _deliver(order: Order, template: str, *, chain=("sms",)) -> str:
    """Monta e "envia" a mensagem de status; devolve o texto que o cliente leria."""
    order.refresh_from_db()
    sent = {}

    def _notify(*, event, recipient, context, backend):
        sent["text"] = notification_sms._build_message(event, context)
        return SimpleNamespace(success=True, message_id="m1", error=None)

    backend = MagicMock()
    backend.is_available.return_value = True
    with (
        patch.object(notification, "_resolve_backend_chain", return_value=list(chain)),
        patch.object(notification, "notify", side_effect=_notify),
        patch("shopman.shop.notifications.get_backend", return_value=backend),
    ):
        ok, error = notification.deliver_order_notification(order, template, {"order_ref": order.ref})
    assert ok, error
    return sent["text"]


def _fallbacks(order: Order) -> int:
    return Directive.objects.filter(
        topic=notification.TOPIC, payload__order_ref=order.ref, payload__template="fiscal_note_ready"
    ).count()


def _mentions(*texts: str) -> int:
    return sum(text.count(DANFE) for text in texts)


# ── Retirada: a nota nasce na conclusão, depois do "pronto" ──────────────


def test_retirada_nota_depois_do_pronto_sai_no_aviso_avulso_uma_vez():
    order = _order(fulfillment="pickup", status="ready")
    ready = _deliver(order, "order_ready")
    assert DANFE not in ready

    _status(order, "completed")
    _authorize(order)
    _authorize(order)  # retry da directive de emissão
    assert _fallbacks(order) == 1


def test_retirada_nota_antes_do_pronto_vai_no_pronto_e_nao_no_avulso():
    order = _order(fulfillment="pickup", status="preparing")
    _authorize(order)
    assert _fallbacks(order) == 0  # o "pronto" ainda vai sair e a leva

    _status(order, "ready")
    ready = _deliver(order, "order_ready")
    assert ready.endswith(f"\n\nNota fiscal do pedido: {DANFE}")
    assert _fallbacks(order) == 0


# ── Entrega: a nota que autoriza depois da mensagem de "saiu" ────────────


def test_entrega_nota_depois_do_saiu_vai_no_entregue():
    order = _order(fulfillment="delivery", status="dispatched")
    dispatched = _deliver(order, "order_dispatched")  # a mensagem ganhou a corrida
    _authorize(order)
    assert _fallbacks(order) == 0

    _status(order, "delivered")
    delivered = _deliver(order, "order_delivered")
    assert DANFE in delivered
    _status(order, "completed")
    _authorize(order)
    assert _fallbacks(order) == 0
    assert _mentions(dispatched, delivered) == 1


def test_entrega_nota_antes_do_saiu_vai_no_saiu_e_nao_repete_no_entregue():
    order = _order(fulfillment="delivery", status="dispatched")
    _authorize(order)
    dispatched = _deliver(order, "order_dispatched")
    _status(order, "delivered")
    delivered = _deliver(order, "order_delivered")
    assert DANFE in dispatched
    assert DANFE not in delivered
    assert _fallbacks(order) == 0
    assert _mentions(dispatched, delivered) == 1


# ── Entrega paga antes: a nota nasce na conclusão, logo depois do "entregue" ──


def test_entrega_paga_nota_depois_do_entregue_sai_no_avulso():
    order = _order(fulfillment="delivery", status="delivered")
    delivered = _deliver(order, "order_delivered")
    assert DANFE not in delivered
    _status(order, "completed")
    _authorize(order)
    assert _fallbacks(order) == 1


def test_entregue_ainda_na_fila_quando_a_nota_autoriza_leva_a_nota():
    order = _order(fulfillment="delivery", status="delivered")
    notification.send(order, "order_delivered")  # na fila, ainda não montada
    _status(order, "completed")
    _authorize(order)
    assert _fallbacks(order) == 0

    delivered = _deliver(order, "order_delivered")
    assert DANFE in delivered
    assert _fallbacks(order) == 0


def test_retry_da_mesma_mensagem_leva_a_nota_de_novo_e_nenhuma_outra_leva():
    order = _order(fulfillment="delivery", status="dispatched")
    _authorize(order)
    first = _deliver(order, "order_dispatched")
    retry = _deliver(order, "order_dispatched")  # a primeira tentativa falhou
    _status(order, "delivered")
    delivered = _deliver(order, "order_delivered")
    assert DANFE in first and DANFE in retry
    assert DANFE not in delivered


# ── Quando a mensagem não pode levar o link ──────────────────────────────


def test_ultima_mensagem_por_flow_nao_leva_o_link_e_o_avulso_sai(settings):
    settings.SHOPMAN_MANYCHAT = {"flow_map": {"order_delivered": "content2025_pedido_entregue"}}
    order = _order(fulfillment="delivery", status="dispatched")
    _authorize(order)  # entregue ainda por vir: espera
    assert _fallbacks(order) == 0

    _status(order, "delivered")
    delivered = _deliver(order, "order_delivered", chain=("manychat", "sms"))
    assert DANFE not in delivered  # o texto do flow é fixo no ManyChat
    assert _fallbacks(order) == 1
    _authorize(order)
    assert _fallbacks(order) == 1


def test_balcao_nunca_leva_a_nota_na_mensagem_nem_recebe_o_avulso():
    order = _order(fulfillment="delivery", status="dispatched", channel="pdv")
    _authorize(order)
    dispatched = _deliver(order, "order_dispatched")
    assert DANFE not in dispatched
    assert _fallbacks(order) == 0


def test_nota_cancelada_nao_vai_na_mensagem():
    order = _order(fulfillment="delivery", status="dispatched")
    Order.objects.filter(pk=order.pk).update(data={**order.data, **NOTE, "nfce_cancelled": True})
    dispatched = _deliver(order, "order_dispatched")
    assert DANFE not in dispatched


# ── O texto ──────────────────────────────────────────────────────────────


def test_texto_do_admin_sem_marcador_ainda_leva_a_nota():
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_delivered", subject="Pedido {order_ref} entregue",
        body="Seu pedido *{order_ref}* foi entregue.", is_active=True,
    )
    order = _order(fulfillment="delivery", status="dispatched")
    _authorize(order)
    _status(order, "delivered")
    delivered = _deliver(order, "order_delivered")
    assert delivered == f"Seu pedido NF-1 foi entregue.\n\nNota fiscal do pedido: {DANFE}"


def test_nota_de_homologacao_avisa_que_nao_vale(settings):
    settings.SHOPMAN_FOCUS_NFE = {"environment": "homologacao"}
    order = _order(fulfillment="delivery", status="dispatched")
    _authorize(order)
    dispatched = _deliver(order, "order_dispatched")
    assert f"Nota fiscal do pedido: {DANFE}\n(Nota de teste, sem valor fiscal.)" in dispatched


def test_mensagem_sem_nota_nao_ganha_rotulo_solto():
    order = _order(fulfillment="pickup", status="ready")
    ready = _deliver(order, "order_ready")
    assert "Nota fiscal" not in ready
    assert "{fiscal_note_suffix}" not in ready
