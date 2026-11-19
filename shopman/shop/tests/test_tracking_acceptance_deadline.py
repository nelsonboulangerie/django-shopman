"""Até quando a loja responde: o acompanhamento lê o que o lifecycle agendou (#2749).

O prazo de aceite já existia, mas a projeção do acompanhamento só o entregava no
``auto_confirm`` (filtrava a Directive por ``action="confirm"``), e a loja online
opera em ``auto_cancel``. Quem pagou e esperava a loja não lia até quando.

A régua é uma só por construção: a projeção não calcula prazo, ela lê o instante
em que o ``confirmation.timeout`` do pedido está agendado. Estes testes agendam
pelo próprio lifecycle e comparam o que a tela recebe com o que ficou na fila.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.projections import order_tracking
from shopman.shop.projections.order_tracking import build_tracking

pytestmark = pytest.mark.django_db


def _web_channel(mode: str) -> None:
    Channel.objects.update_or_create(
        ref="web",
        defaults={
            "name": "Loja online",
            "is_active": True,
            "config": {
                "confirmation": {"mode": mode, "timeout_minutes": 5, "preorder_timeout_minutes": 60},
                "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
            },
        },
    )


def _order(ref: str, *, status: str = "new", method: str = "pix", delivery_date=None) -> Order:
    data: dict = {"payment": {"method": method}}
    if delivery_date is not None:
        data["delivery_date"] = delivery_date.isoformat()
    return Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=1500, data=data)


def _schedule(order: Order, *, action: str) -> Directive:
    from shopman.shop.lifecycle import _schedule_confirmation_timeout

    timer = _schedule_confirmation_timeout(
        order, ChannelConfig.for_channel("web"), action=action, source="payment_confirmed",
    )
    assert timer is not None
    return timer


@pytest.fixture
def paid(monkeypatch):
    """O pedido está pago: a bola é da loja (estado ``payment_confirmed``)."""
    status = order_tracking.payment_status
    monkeypatch.setattr(status, "has_sufficient_captured_payment", lambda order: True)
    monkeypatch.setattr(status, "payment_deadline_passed", lambda order: False)
    monkeypatch.setattr(status, "get_payment_status", lambda order: "captured")
    monkeypatch.setattr(order_tracking, "store_review_deferred_state", lambda order, state=None: None)


@pytest.fixture
def card_authorized(monkeypatch):
    """Cartão autorizado e ainda não cobrado (estado ``payment_authorized``)."""
    status = order_tracking.payment_status
    monkeypatch.setattr(status, "has_sufficient_captured_payment", lambda order: False)
    monkeypatch.setattr(status, "payment_deadline_passed", lambda order: False)
    monkeypatch.setattr(status, "get_payment_status", lambda order: "authorized")
    monkeypatch.setattr(order_tracking, "store_review_deferred_state", lambda order, state=None: None)


def _published(order: Order) -> datetime | None:
    value = build_tracking(order).promise.acceptance_deadline_at
    return datetime.fromisoformat(value) if value else None


# ── A mesma régua: o que a tela recebe é o que ficou agendado ────────────────


def test_auto_cancel_publica_o_instante_em_que_o_cancelamento_esta_agendado(paid):
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-1")
    timer = _schedule(order, action="cancel")

    promise = build_tracking(order).promise

    assert promise.state == "payment_confirmed"
    assert datetime.fromisoformat(promise.acceptance_deadline_at) == timer.available_at
    assert timer.payload["action"] == "cancel"
    # E é o mesmo instante que o lifecycle gravou no payload do timer.
    assert datetime.fromisoformat(timer.payload["expires_at"]) == timer.available_at


def test_auto_confirm_publica_o_instante_do_aceite_automatico(paid):
    _web_channel("auto_confirm")
    order = _order("WEB-PRAZO-2")
    timer = _schedule(order, action="confirm")

    assert _published(order) == timer.available_at


def test_encomenda_publica_o_prazo_longo_que_o_lifecycle_agendou(paid):
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-3", delivery_date=timezone.localdate() + timedelta(days=1))
    before = timezone.now()
    timer = _schedule(order, action="cancel")

    published = _published(order)

    assert published == timer.available_at
    # 60 minutos da encomenda, não os 5 do pedido do dia: quem decide é quem agenda.
    assert published >= before + timedelta(minutes=60)


def test_cartao_autorizado_publica_o_mesmo_prazo(card_authorized):
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-4", method="card")
    timer = _schedule(order, action="cancel")

    promise = build_tracking(order).promise

    assert promise.state == "payment_authorized"
    assert datetime.fromisoformat(promise.acceptance_deadline_at) == timer.available_at


def test_prazo_rebaseado_pelo_lifecycle_e_o_que_a_tela_passa_a_ler(paid):
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-5")
    _schedule(order, action="cancel")
    # O lifecycle rebaseia o mesmo timer (outra origem): a tela segue a fila.
    later = timezone.now() + timedelta(minutes=42)
    Directive.objects.filter(topic="confirmation.timeout", payload__order_ref=order.ref).update(available_at=later)

    assert _published(order) == later
    assert Directive.objects.filter(topic="confirmation.timeout", payload__order_ref=order.ref).count() == 1


# ── Quando não há prazo a publicar ───────────────────────────────────────────


@pytest.mark.parametrize("status", ["accepted", "preparing", "ready", "cancelled", "completed"])
def test_pedido_que_a_loja_ja_decidiu_nao_publica_prazo(paid, status):
    _web_channel("auto_cancel")
    order = _order(f"WEB-PRAZO-D-{status}")
    _schedule(order, action="cancel")
    Order.objects.filter(pk=order.pk).update(status=status)
    order.refresh_from_db()

    assert _published(order) is None


def test_pedido_sem_timer_na_fila_nao_publica_prazo(paid):
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-6")

    promise = build_tracking(order).promise

    assert promise.state == "payment_confirmed"
    assert promise.acceptance_deadline_at is None


def test_timer_que_ja_rodou_nao_publica_prazo(paid):
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-7")
    timer = _schedule(order, action="cancel")
    Directive.objects.filter(pk=timer.pk).update(status="done")

    assert _published(order) is None


def test_prazo_vencido_e_ainda_na_fila_nao_e_prometido(paid):
    # O worker ainda não passou: dizer "até 8h40" às 8h45 seria promessa errada.
    _web_channel("auto_cancel")
    order = _order("WEB-PRAZO-8")
    timer = _schedule(order, action="cancel")
    Directive.objects.filter(pk=timer.pk).update(available_at=timezone.now() - timedelta(minutes=1))

    assert _published(order) is None


def test_enquanto_a_bola_e_do_cliente_o_prazo_da_loja_nao_aparece(monkeypatch):
    # Pix ainda não pago: quem age é o cliente; o prazo publicado é o do Pix.
    _web_channel("auto_cancel")
    status = order_tracking.payment_status
    monkeypatch.setattr(status, "has_sufficient_captured_payment", lambda order: False)
    monkeypatch.setattr(status, "payment_deadline_passed", lambda order: False)
    monkeypatch.setattr(status, "get_payment_status", lambda order: "pending")
    monkeypatch.setattr(order_tracking, "store_review_deferred_state", lambda order, state=None: None)
    order = _order("WEB-PRAZO-9")
    order.data["payment"].update({"qr_code": "00020126...", "copy_paste": "00020126..."})
    order.save(update_fields=["data"])
    _schedule(order, action="cancel")

    promise = build_tracking(order).promise

    assert promise.state not in order_tracking._STORE_DECISION_STATES
    assert promise.acceptance_deadline_at is None


def test_o_modo_auto_confirm_continua_com_a_contagem_que_ja_tinha(paid):
    # A contagem do aceite automático (``store_checking``) segue lendo só o timer
    # de ``action="confirm"``: o prazo novo não mudou a regra antiga.
    _web_channel("auto_confirm")
    order = _order("WEB-PRAZO-10")
    timer = _schedule(order, action="confirm")

    assert order_tracking._confirmation_deadline(order) == timer.available_at
    Directive.objects.filter(pk=timer.pk).update(payload={**timer.payload, "action": "cancel"})
    assert order_tracking._confirmation_deadline(order) is None
    assert order_tracking._confirmation_deadline(order, action=None) == timer.available_at
