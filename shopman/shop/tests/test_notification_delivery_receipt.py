"""Comprovante de entrega (D3): aceite não é entrega, e aviso crítico segue a cadeia.

Ver ``docs/reference/comprovante-de-entrega.md``. Os dois defeitos medidos em
30/09 (O3b, ``PDV-260930-R62``):

1. "sucesso" sem identificador do provedor encerrava a cadeia como entregue;
2. resposta ambígua parava a cadeia, e o e-mail (que funcionaria) nunca saía.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.notification import NotificationSendHandler
from shopman.shop.models import Shop
from shopman.shop.services import notification


@pytest.fixture
def order(db, monkeypatch):
    Shop.objects.create(name="Synthetic receipt lab")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    order = Order.objects.create(
        ref="RECEIPT-1", status="confirmed", total_q=1500,
        data={"fulfillment_type": "pickup", "payment": {"method": "cash"}},
    )
    monkeypatch.setattr(notification, "_resolve_backend_chain", lambda order: ["manychat", "email", "sms"])
    monkeypatch.setattr(notification, "_filter_backend_chain", lambda order, chain, **kwargs: chain)
    monkeypatch.setattr(notification, "_resolve_recipient", lambda order, backend: f"synthetic-{backend}")
    monkeypatch.setattr(notification, "_build_context", lambda *args: {})
    return order


def _backends(monkeypatch, behaviour: dict):
    """``behaviour[backend]`` = retorno do ``send`` ou exceção a levantar."""
    calls: list[str] = []

    def make(name):
        def send(**kwargs):
            calls.append(name)
            outcome = behaviour[name]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return SimpleNamespace(send=send)

    adapters = {name: make(name) for name in behaviour}
    monkeypatch.setattr("shopman.shop.notifications.get_backend", lambda name: adapters.get(name))
    return calls


def test_os_eventos_criticos_sao_o_link_e_a_confirmacao():
    assert notification.CRITICAL_NOTIFICATION_TEMPLATES == frozenset({"payment_link_sent", "order_accepted"})


# ── Defeito 1: aceite sem identificador não é entrega ──────────────────────


def test_critico_sem_identificador_segue_para_o_proximo_canal(order, monkeypatch):
    calls = _backends(monkeypatch, {
        "manychat": True,  # ManyChat: status success, sem message_id
        "email": {"success": True, "message_id": "<abc@boulangerie.com.br>"},
        "sms": True,
    })
    payload = {"order_ref": order.ref}

    success, error = notification.deliver_order_notification(order, "payment_link_sent", payload)

    assert (success, error) == (True, None)
    assert calls == ["manychat", "email"]
    record = payload["notification_delivery"]
    assert record["status"] == "accepted"
    assert record["proof"] == notification.PROOF_RECEIPT
    assert record["backend"] == "email"
    assert record["message_id"] == "<abc@boulangerie.com.br>"
    assert record["critical"] is True
    assert [(a["backend"], a["outcome"]) for a in record["attempts"]] == [
        ("manychat", "no_receipt"),
        ("email", "receipt"),
    ]
    # O comprovante não leva o contato em claro.
    assert "synthetic-" not in str(record)
    assert all(len(a["recipient_fingerprint"]) == 16 for a in record["attempts"])


def test_nao_critico_sem_identificador_para_no_primeiro_aceite(order, monkeypatch):
    calls = _backends(monkeypatch, {"manychat": True, "email": True, "sms": True})
    payload = {"order_ref": order.ref}

    success, _ = notification.deliver_order_notification(order, "order_ready", payload)

    assert success is True
    assert calls == ["manychat"]
    record = payload["notification_delivery"]
    assert record["status"] == "accepted"
    assert record["proof"] == notification.PROOF_NO_RECEIPT
    assert "critical" not in record


def test_critico_com_identificador_no_primeiro_canal_nao_manda_mais_nada(order, monkeypatch):
    calls = _backends(monkeypatch, {
        "manychat": {"success": True, "message_id": "wamid.1"}, "email": True, "sms": True,
    })
    payload = {"order_ref": order.ref}

    notification.deliver_order_notification(order, "order_accepted", payload)

    assert calls == ["manychat"]
    assert payload["notification_delivery"]["proof"] == notification.PROOF_RECEIPT


def test_critico_sem_comprovante_em_canal_nenhum_fica_aceito_sem_comprovante(order, monkeypatch):
    calls = _backends(monkeypatch, {"manychat": True, "email": False, "sms": True})
    payload = {"order_ref": order.ref}

    success, _ = notification.deliver_order_notification(order, "payment_link_sent", payload)

    assert success is True  # saiu: retry automático seria mais uma mensagem
    assert calls == ["manychat", "email", "sms"]
    record = payload["notification_delivery"]
    assert record["status"] == "accepted"
    assert record["proof"] == notification.PROOF_NO_RECEIPT
    assert record["backend"] == "sms"
    assert [a["outcome"] for a in record["attempts"]] == ["no_receipt", "failed", "no_receipt"]


# ── Defeito 2: ambíguo em crítico tenta o próximo ──────────────────────────


def test_critico_ambiguo_tenta_o_proximo_canal(order, monkeypatch):
    calls = _backends(monkeypatch, {
        "manychat": TimeoutError("synthetic lost response"),
        "email": {"success": True, "message_id": "<m@boulangerie.com.br>"},
        "sms": True,
    })
    payload = {"order_ref": order.ref}

    success, _ = notification.deliver_order_notification(order, "payment_link_sent", payload)

    assert success is True
    assert calls == ["manychat", "email"]
    assert [a["outcome"] for a in payload["notification_delivery"]["attempts"]] == ["unknown", "receipt"]


def test_critico_ambiguo_sem_outro_canal_aceito_continua_desconhecido(order, monkeypatch):
    _backends(monkeypatch, {"manychat": TimeoutError("x"), "email": False, "sms": False})
    payload = {"order_ref": order.ref}

    success, error = notification.deliver_order_notification(order, "order_accepted", payload)

    assert (success, error) == (False, "acceptance_unconfirmed")
    assert payload["notification_delivery"]["status"] == "unknown"
    assert payload["notification_delivery"]["backend"] == "manychat"


def test_nao_critico_ambiguo_continua_parando_a_cadeia(order, monkeypatch):
    calls = _backends(monkeypatch, {"manychat": TimeoutError("x"), "email": True, "sms": True})
    payload = {"order_ref": order.ref}

    success, _ = notification.deliver_order_notification(order, "order_ready", payload)

    assert success is False
    assert calls == ["manychat"]
    assert payload["notification_delivery"]["status"] == "unknown"


# ── Alerta ao operador ─────────────────────────────────────────────────────


def _run_handler(order, template):
    task = Directive.objects.create(topic=notification.TOPIC, attempts=1,
        payload={"order_ref": order.ref, "template": template})
    NotificationSendHandler().handle(message=task, ctx={})
    task.refresh_from_db()
    return task


def test_critico_sem_comprovante_alerta_o_operador(order, monkeypatch):
    from shopman.backstage.models import OperatorAlert

    _backends(monkeypatch, {"manychat": True, "email": False, "sms": True})

    task = _run_handler(order, "order_accepted")

    assert task.payload["notification_delivery"]["proof"] == notification.PROOF_NO_RECEIPT
    alert = OperatorAlert.objects.get(order_ref=order.ref)
    assert alert.type == "notification_failed"
    assert "nenhum canal devolveu comprovante" in alert.message
    assert "—" not in alert.message


def test_critico_com_comprovante_nao_alerta(order, monkeypatch):
    from shopman.backstage.models import OperatorAlert

    _backends(monkeypatch, {"manychat": True, "email": {"success": True, "message_id": "<x@y>"}, "sms": True})

    _run_handler(order, "order_accepted")

    assert not OperatorAlert.objects.filter(order_ref=order.ref).exists()


def test_nao_critico_sem_comprovante_nao_alerta(order, monkeypatch):
    from shopman.backstage.models import OperatorAlert

    _backends(monkeypatch, {"manychat": True, "email": True, "sms": True})

    _run_handler(order, "order_ready")

    assert not OperatorAlert.objects.filter(order_ref=order.ref).exists()


# ── O comprovante na tela do operador ──────────────────────────────────────


def test_projecao_mostra_entregue_so_com_comprovante(order, monkeypatch):
    from shopman.backstage.projections.notification_receipts import build_notification_receipts

    _backends(monkeypatch, {"manychat": True, "email": {"success": True, "message_id": "<m@b>"}, "sms": True})
    _run_handler(order, "order_accepted")
    _backends(monkeypatch, {"manychat": True, "email": True, "sms": True})
    _run_handler(order, "order_ready")

    confirmed, ready = build_notification_receipts(order)

    assert confirmed.state == "delivered"
    assert confirmed.state_label == "Entregue com comprovante"
    assert confirmed.channel_label == "E-mail"
    assert confirmed.provider_id == "<m@b>"
    assert confirmed.critical is True
    assert [a.outcome_label for a in confirmed.attempts] == ["aceito, sem comprovante", "aceito, com comprovante"]
    assert ready.state == "accepted_no_receipt"
    assert ready.state_label == "Aceito pelo provedor, sem comprovante"
    assert ready.provider_id == ""
    assert ready.critical is False


def test_projecao_registro_sem_marca_de_comprovante_nunca_e_entregue(order):
    from shopman.backstage.projections.notification_receipts import build_receipt

    directive = Directive.objects.create(topic=notification.TOPIC, status="done", payload={
        "order_ref": order.ref, "template": "payment_link_sent",
        "notification_delivery": {"status": "accepted", "backend": "manychat", "message_id": "solto"},
    })

    receipt = build_receipt(directive)

    assert receipt.state == "accepted_no_receipt"
    assert receipt.provider_id == ""


def test_detalhe_do_pedido_expoe_os_comprovantes(order, monkeypatch):
    from shopman.backstage.projections.order_queue import build_operator_order

    _backends(monkeypatch, {"manychat": True, "email": False, "sms": True})
    _run_handler(order, "order_accepted")

    detail = build_operator_order(order)

    (receipt,) = detail.notification_receipts
    assert receipt.state_label == "Aceito pelo provedor, sem comprovante"
    assert receipt.channel_label == "SMS"
    assert "Confirme com o cliente" in receipt.detail
