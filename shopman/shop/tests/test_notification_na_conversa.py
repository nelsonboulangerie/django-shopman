"""OC-10: o aviso de pedido entra na conversa da Concierge (Etapa III omnicanal, DEV-2026-085).

O laudo da Etapa II (T4) mediu: os avisos de pedido (pago, aceito, pronto, saiu) saem por
um pipeline à parte e não entravam na transcrição, e a Concierge não sabia o que o cliente
já tinha recebido. Aqui, pela entrega de verdade (``deliver_order_notification``):

- X15: aviso entregue pelo WhatsApp a contato com conversa grava a nota com o texto;
- contato sem conversa, ou aviso por e-mail, não grava nada;
- nada é reenviado, e falhar ao gravar não falha o aviso (a directive não tenta de novo).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from shopman.orderman.models import Order

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage, Shop
from shopman.shop.services import notification

pytestmark = pytest.mark.django_db

PHONE = "+5543981234567"
SUBSCRIBER = "1962036908"
PIX = "00020101021226870014br.gov.bcb.pix2565pix.example.com/qr/v2/OC10"


@pytest.fixture
def order(monkeypatch):
    Shop.objects.create(name="Synthetic notice lab")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    order = Order.objects.create(
        ref="OC10-1", status="new", total_q=1800,
        data={"fulfillment_type": "pickup", "customer": {"name": "Ana", "phone": PHONE},
              "payment": {"method": "pix", "copy_paste": PIX}},
    )
    monkeypatch.setattr(notification, "_filter_backend_chain", lambda order, chain, **kwargs: chain)
    monkeypatch.setattr(notification, "_build_context", lambda order, payload, template: {
        "order_ref": order.ref,
        "customer_name": "Ana",
        "copy_paste": PIX,
        "pix_suffix": f" Código PIX: {PIX}",
        "tracking_url": f"https://loja.test/pedido/{order.ref}",
        "payment_url": f"https://loja.test/pedido/{order.ref}",
    })
    monkeypatch.setattr("shopman.shop.adapters.notification_manychat.sends_as_flow", lambda template: False)
    return order


def _chain(monkeypatch, chain: list[str], recipient: str = PHONE):
    monkeypatch.setattr(notification, "_resolve_backend_chain", lambda order: list(chain))
    monkeypatch.setattr(notification, "_resolve_recipient", lambda order, backend: recipient)


def _backends(monkeypatch, outcome=None):
    """Cada ``send`` aceito com comprovante; devolve a lista do que saiu."""
    sent: list[tuple[str, str]] = []

    def make(name):
        def send(*, recipient, template, context, **kwargs):
            sent.append((name, template))
            return outcome if outcome is not None else {"success": True, "message_id": f"{name}.{len(sent)}"}
        return SimpleNamespace(send=send)

    monkeypatch.setattr("shopman.shop.notifications.get_backend", lambda name: make(name))
    return sent


def _conversation(*, phone: str = PHONE, subject: str = SUBSCRIBER, state=Conversation.State.ACTIVE):
    conversation = Conversation.objects.create(phone=phone, customer_name="Ana", channel_ref="whatsapp", state=state)
    ConversationBinding.objects.create(
        conversation=conversation, provider="manychat", account="conta", transport_channel="whatsapp",
        subject=subject, connection_key="manychat-whatsapp", status=ConversationBinding.Status.ACTIVE,
    )
    return conversation


def _notes(conversation=None):
    notes = ConversationMessage.objects.filter(kind=ConversationMessage.Kind.NOTE)
    return notes.filter(conversation=conversation) if conversation is not None else notes


def test_x15_aviso_entregue_pelo_whatsapp_grava_a_nota_na_conversa(order, monkeypatch):
    conversation = _conversation()
    _chain(monkeypatch, ["manychat"])
    sent = _backends(monkeypatch)

    assert notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref}) == (True, None)

    assert sent == [("manychat", "payment_requested")], "um envio só: gravar não reenvia"
    note = _notes(conversation).get()
    assert note.role == ConversationMessage.Role.ASSISTANT
    assert note.binding_id is None and note.transport_state == "not_applicable", "nota não é mensagem a enviar"
    assert note.envelope == {
        "version": 3, "kind": "order_notice", "order_ref": order.ref, "template": "payment_requested",
        "backend": "manychat", "approved_template": False,
    }
    assert note.text.startswith("Oi, Ana! Seu pedido"), note.text
    assert PIX in note.text, "o texto enviado, com o código Pix que ele levou"


def test_x15_pelo_assinante_do_manychat_acha_a_conversa_do_vinculo(order, monkeypatch):
    conversation = _conversation(phone="")
    _chain(monkeypatch, ["manychat"], recipient=SUBSCRIBER)
    _backends(monkeypatch)

    notification.deliver_order_notification(order, "order_ready_pickup", {"order_ref": order.ref})

    assert _notes(conversation).get().envelope["template"] == "order_ready_pickup"


def test_cliente_sem_conversa_nao_grava_nada(order, monkeypatch):
    other = _conversation(phone="+5543999990000", subject="555")
    _chain(monkeypatch, ["manychat"])
    sent = _backends(monkeypatch)

    assert notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref}) == (True, None)

    assert sent == [("manychat", "payment_requested")]
    assert not ConversationMessage.objects.exists(), "nem na conversa de outro número"
    assert not _notes(other).exists()


def test_aviso_por_email_nao_e_desta_conversa(order, monkeypatch):
    _conversation()
    _chain(monkeypatch, ["email"], recipient="ana@example.com")
    _backends(monkeypatch)

    notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref})

    assert not _notes().exists()


def test_aviso_que_falhou_nao_grava(order, monkeypatch):
    _conversation()
    _chain(monkeypatch, ["manychat"])
    _backends(monkeypatch, outcome={"success": False, "error": "provider_rejected"})

    assert notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref})[0] is False

    assert not _notes().exists()


def test_conversa_encerrada_nao_recebe_a_nota(order, monkeypatch):
    _conversation(state=Conversation.State.CLOSED)
    _chain(monkeypatch, ["manychat"])
    _backends(monkeypatch)

    notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref})

    assert not _notes().exists()


def test_template_aprovado_nao_leva_o_codigo_pix_e_a_nota_nao_diz_que_levou(order, monkeypatch):
    conversation = _conversation()
    _chain(monkeypatch, ["manychat"])
    _backends(monkeypatch)
    monkeypatch.setattr("shopman.shop.adapters.notification_manychat.sends_as_flow", lambda template: True)

    notification.deliver_order_notification(order, "payment_requested", {"order_ref": order.ref})

    note = _notes(conversation).get()
    assert note.envelope["approved_template"] is True
    assert PIX not in note.text and "Código PIX" not in note.text, note.text


def test_falhar_ao_gravar_nao_falha_o_aviso_nem_o_reenvia(order, monkeypatch):
    _conversation()
    _chain(monkeypatch, ["manychat"])
    sent = _backends(monkeypatch)

    def broken(*args, **kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(ConversationMessage.objects, "create", broken)

    payload = {"order_ref": order.ref}
    assert notification.deliver_order_notification(order, "payment_requested", payload) == (True, None)

    assert sent == [("manychat", "payment_requested")]
    assert payload["notification_delivery"]["status"] == "accepted"
