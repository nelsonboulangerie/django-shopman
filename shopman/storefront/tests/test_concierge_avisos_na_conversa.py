# ruff: noqa: F401, F811
"""OC-10: a Nice sabe que avisos o cliente já recebeu (Etapa III omnicanal, DEV-2026-085).

O laudo da Etapa II (T4) mediu: o aviso de pedido com o código Pix saía pelo pipeline de
notificação, fora da transcrição, e a Nice, perguntada "cadê o Pix?", não sabia que o
cliente já o tinha recebido. Aqui, pela conversa inteira (pedido feito na conversa, aviso
entregue pela notificação de verdade, turno de consulta):

- X15: o aviso entregue vira nota na conversa, e o turno de consulta a enxerga;
- nada é reenviado: a leitura não cria aviso nem cobrança;
- código Pix regenerado não conta o aviso do código velho.
"""

from __future__ import annotations

from datetime import datetime, time
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent

from shopman.shop.models import ConversationMessage
from shopman.shop.services import notification
from shopman.storefront.concierge import tools
from shopman.storefront.tests import test_concierge_engine as fixtures
from shopman.storefront.tests import test_concierge_fechar_pedido as closing
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _listed,
    conversation,
    customer,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act

pytestmark = pytest.mark.django_db(transaction=True)

WHERE_IS_PIX = [_act("order_status", "cadê o Pix?")]
SENT_LINE = "Já te mandei o código Pix por aqui às 14h12."


@pytest.fixture
def shop(conversation, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr("shopman.storefront.concierge.intents._model", lambda: "modelo-de-teste")
    monkeypatch.setattr(
        "shopman.storefront.concierge.transport.send_for",
        lambda binding, text: fixtures.SendOutcome("accepted", "accepted", f"test:{binding.subject}:{text[:8]}"),
    )
    _listed("CROISSANT", "Croissant", description="Folhado amanteigado", stock="50")
    return conversation


@pytest.fixture
def whatsapp(monkeypatch):
    """O aviso sai pelo ManyChat em texto livre, aceito com comprovante; guarda o que saiu."""
    sent: list[str] = []

    def send(*, recipient, template, context, **kwargs):
        sent.append(template)
        return {"success": True, "message_id": f"wamid.{len(sent)}"}

    monkeypatch.setattr(notification, "_resolve_backend_chain", lambda order: ["manychat"])
    monkeypatch.setattr(notification, "_filter_backend_chain", lambda order, chain, **kwargs: chain)
    monkeypatch.setattr("shopman.shop.adapters.notification_manychat.sends_as_flow", lambda template: False)
    monkeypatch.setattr("shopman.shop.notifications.get_backend", lambda name: SimpleNamespace(send=send))
    return sent


def _pix_order(conversation) -> Order:
    closing._bag(conversation)
    closing._say(conversation, "pode fechar")
    closing._say(conversation, "amanhã")
    closing._say(conversation, "vou retirar")
    closing._say(conversation, "às 13h")
    summary = closing._say(conversation, "pix")
    closing._turn(conversation, f"confirmo {closing._code(summary)}")
    order = Order.objects.get()
    assert order.data["payment"]["copy_paste"]
    return order


def _reply_with_code_never_left(conversation, code: str) -> None:
    """A resposta da Nice com o código não chegou ao cliente: só o aviso pode provar o envio."""
    ConversationMessage.objects.filter(
        conversation=conversation, kind=ConversationMessage.Kind.REPLY, text__contains=code
    ).update(transport_state="not_applied")


def _notice_at_1412(conversation, order) -> ConversationMessage:
    """O último aviso de pagamento entregue nesta conversa, posto às 14h12."""
    note = ConversationMessage.objects.filter(
        conversation=conversation, kind=ConversationMessage.Kind.NOTE,
        envelope__order_ref=order.ref, envelope__template="payment_requested",
    ).latest("pk")
    at = timezone.make_aware(datetime.combine(timezone.localdate(), time(14, 12)))
    ConversationMessage.objects.filter(pk=note.pk).update(created_at=at)
    return note


def test_x15_cade_o_pix_enxerga_o_aviso_ja_enviado(shop, whatsapp):
    order = _pix_order(shop)
    code = order.data["payment"]["copy_paste"]
    _reply_with_code_never_left(shop, code)

    # O pedido feito na conversa já dispara avisos pela esteira de sempre (o "recebemos
    # seu pedido" vira nota aqui); o de pagamento, com o código, sai pela mesma entrega.
    assert ConversationMessage.objects.filter(
        conversation=shop, envelope__kind="order_notice", envelope__template="order_received"
    ).exists()
    assert notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref}) == (True, None)
    note = _notice_at_1412(shop, order)
    assert code in note.text and note.envelope["kind"] == "order_notice"
    sent_before = list(whatsapp)
    notices = Directive.objects.filter(topic=notification.TOPIC).count()
    charges = PaymentIntent.objects.filter(order_ref=order.ref).count()

    reply = closing._turn(shop, "cadê o Pix?", WHERE_IS_PIX)

    assert reply[0].startswith(f"Pedido {order.ref}"), reply
    # O código vai de novo na mensagem seguinte: as duas coisas numa linha só.
    assert tools.PIX_SENT_AGAIN.format(when="às 14h12") in reply[0].splitlines(), reply
    assert whatsapp == sent_before, "a consulta não reenvia o aviso"
    assert Directive.objects.filter(topic=notification.TOPIC).count() == notices, "nem agenda outro"
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == charges, "nem cria outra cobrança"


def test_sem_aviso_e_sem_resposta_enviada_a_nice_nao_diz_que_mandou(shop):
    """Sem o WhatsApp de mentira, os avisos não saem (adapter inerte em teste): nada a lembrar."""
    order = _pix_order(shop)
    _reply_with_code_never_left(shop, order.data["payment"]["copy_paste"])
    assert not ConversationMessage.objects.filter(kind=ConversationMessage.Kind.NOTE, envelope__kind="order_notice").exists()

    reply = closing._turn(shop, "cadê o Pix?", WHERE_IS_PIX)

    assert reply[0].startswith(f"Pedido {order.ref}"), reply
    assert "Já te mandei" not in reply[0], reply


def test_codigo_regenerado_nao_conta_o_aviso_do_codigo_velho(shop, whatsapp):
    order = _pix_order(shop)
    _reply_with_code_never_left(shop, order.data["payment"]["copy_paste"])
    notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref})
    _notice_at_1412(shop, order)
    order.data["payment"]["copy_paste"] = "00020101PIXNOVO"
    order.save(update_fields=["data"])

    ctx = tools.ToolContext(conversation=shop, channel_ref=shop.channel_ref)
    fixtures._create_inbound(shop, "cadê o Pix?", "oc10-regenerado")
    fixtures._reclaim(ctx)
    result = tools.order_status(ctx, order.ref)

    assert result["orders"][0]["pix_sent_at"] == ""
    assert "Já te mandei" not in tools.render_result("order_status", result)


def test_a_resposta_da_nice_que_saiu_tambem_conta(shop, whatsapp):
    """O código que a própria Nice mandou no pedido (bloco separado, aceito) também é "já mandei"."""
    order = _pix_order(shop)

    reply = closing._turn(shop, "cadê o Pix?", WHERE_IS_PIX)

    assert reply[0].startswith(f"Pedido {order.ref}"), reply
    assert any(line.startswith("Já te mandei o código Pix por aqui ") for line in reply[0].splitlines()), reply


def test_render_sem_o_campo_nao_muda_a_consulta():
    text = tools.render_result("order_status", {"ok": True, "orders": [{
        "order_ref": "W29", "title": "Aguardando pagamento", "message": "", "total": "R$ 18,00",
        "created_at": "23/11 14:10", "tracking_url": "https://loja/pedido/W29", "actions": [],
    }]})
    assert "Já te mandei" not in text
    text = tools.render_result("order_status", {"ok": True, "orders": [{
        "order_ref": "W29", "title": "Aguardando pagamento", "message": "", "total": "R$ 18,00",
        "created_at": "23/11 14:10", "tracking_url": "https://loja/pedido/W29", "actions": [],
        "pix_sent_at": "às 14h12",
    }]})
    assert text.splitlines()[:2] == [
        "Pedido W29, de 23/11 14:10: Aguardando pagamento. Total: R$ 18,00.",
        SENT_LINE,
    ]
