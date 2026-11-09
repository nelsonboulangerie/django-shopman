"""Prazo de aceite da loja online: 5 min no dia, 60 na encomenda (dono, 09/11/2026).

Emenda da ADR-036. Os 30 min de antes eram "tempo demais" para quem pagou e espera
a resposta. O pedido do dia tem 5 minutos de loja aberta; a encomenda para outro dia
(data combinada posterior a hoje), 60. O aviso de pedido parado sai a 1/3 do prazo do
próprio pedido, e a janela do aviso conta até a mesma hora que o corpo diz.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

WEB = {
    "confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "preorder_timeout_minutes": 60},
    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
}


def _web_channel(config=WEB):
    Channel.objects.update_or_create(
        ref="web", defaults={"name": "Loja online", "is_active": True, "config": config},
    )


def _order(ref: str, *, delivery_date=None) -> Order:
    data = {"payment": {"method": "pix"}}
    if delivery_date is not None:
        data["delivery_date"] = delivery_date.isoformat()
    return Order.objects.create(ref=ref, channel_ref="web", status=Order.Status.NEW, total_q=1500, data=data)


def _schedule(order: Order):
    from shopman.shop.lifecycle import _schedule_confirmation_timeout

    return _schedule_confirmation_timeout(
        order, ChannelConfig.for_channel("web"), action="cancel", source="payment_confirmed",
    )


def _run_timer_at(order: Order, when):
    from shopman.shop.handlers.confirmation import ConfirmationTimeoutHandler

    directive = Directive.objects.get(topic="confirmation.timeout", payload__order_ref=order.ref)
    with (
        patch("django.utils.timezone.now", return_value=when),
        patch("shopman.shop.lifecycle.payment"),
        patch("shopman.shop.lifecycle.notification"),
    ):
        ConfirmationTimeoutHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    return order


def _tomorrow():
    return timezone.localdate() + timedelta(days=1)


# ── O prazo do pedido ───────────────────────────────────────────────────────


def test_pedido_do_dia_tem_5_minutos():
    _web_channel()
    order = _order("WEB-DIA-1")
    before = timezone.now()

    timer = _schedule(order)

    expires_at = datetime.fromisoformat(timer.payload["expires_at"])
    assert before + timedelta(minutes=5) <= expires_at <= timezone.now() + timedelta(minutes=5)


def test_pedido_com_data_de_hoje_e_do_dia():
    _web_channel()
    order = _order("WEB-DIA-2", delivery_date=timezone.localdate())
    before = timezone.now()

    timer = _schedule(order)

    expires_at = datetime.fromisoformat(timer.payload["expires_at"])
    assert expires_at <= before + timedelta(minutes=5, seconds=5)


def test_encomenda_para_outro_dia_tem_60_minutos():
    _web_channel()
    order = _order("WEB-ENC-1", delivery_date=_tomorrow())
    before = timezone.now()

    timer = _schedule(order)

    expires_at = datetime.fromisoformat(timer.payload["expires_at"])
    assert before + timedelta(minutes=60) <= expires_at <= timezone.now() + timedelta(minutes=60)


def test_canal_sem_prazo_de_encomenda_usa_o_do_dia_na_encomenda():
    _web_channel({**WEB, "confirmation": {"mode": "auto_cancel", "timeout_minutes": 5}})
    order = _order("WEB-ENC-2", delivery_date=_tomorrow())
    before = timezone.now()

    timer = _schedule(order)

    expires_at = datetime.fromisoformat(timer.payload["expires_at"])
    assert expires_at <= before + timedelta(minutes=5, seconds=5)


def test_pedido_do_dia_cancela_sozinho_depois_de_5_minutos_e_nao_antes():
    _web_channel()
    order = _order("WEB-DIA-3")
    timer = _schedule(order)
    expires_at = datetime.fromisoformat(timer.payload["expires_at"])

    assert _run_timer_at(order, expires_at - timedelta(seconds=30)).status == Order.Status.NEW
    assert _run_timer_at(order, expires_at + timedelta(seconds=1)).status == Order.Status.CANCELLED
    assert order.data["cancellation_reason"] == "confirmation_timeout"


def test_encomenda_nao_cancela_aos_5_minutos_so_depois_de_60():
    _web_channel()
    order = _order("WEB-ENC-3", delivery_date=_tomorrow())
    start = timezone.now()
    timer = _schedule(order)
    expires_at = datetime.fromisoformat(timer.payload["expires_at"])

    assert _run_timer_at(order, start + timedelta(minutes=6)).status == Order.Status.NEW
    assert _run_timer_at(order, expires_at - timedelta(seconds=30)).status == Order.Status.NEW
    assert _run_timer_at(order, expires_at + timedelta(seconds=1)).status == Order.Status.CANCELLED


def test_encomenda_feita_com_a_loja_fechada_conta_60_minutos_desde_a_abertura():
    """Minutos de LOJA ABERTA: a encomenda da noite começa a contar na abertura."""
    tz = ZoneInfo("America/Sao_Paulo")
    hours = {"open": "07:00", "close": "19:00"}
    Shop.objects.create(
        name="Loja",
        timezone="America/Sao_Paulo",
        opening_hours=dict.fromkeys(
            ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"), hours,
        ),
    )
    _web_channel()
    night = datetime(2026, 11, 9, 22, 0, tzinfo=tz)
    order = _order("WEB-ENC-4", delivery_date=night.date() + timedelta(days=2))

    with patch("django.utils.timezone.now", return_value=night):
        timer = _schedule(order)

    assert datetime.fromisoformat(timer.payload["expires_at"]) == datetime(2026, 11, 10, 8, 0, tzinfo=tz)
    alert = Directive.objects.get(topic="order.stale_new_alert", payload__order_ref=order.ref)
    assert alert.available_at == datetime(2026, 11, 10, 7, 20, tzinfo=tz)


# ── O aviso antes do prazo ──────────────────────────────────────────────────


def test_aviso_do_pedido_do_dia_sai_a_um_terco_do_prazo():
    _web_channel()
    order = _order("WEB-DIA-4")

    timer = _schedule(order)

    alert = Directive.objects.get(topic="order.stale_new_alert", payload__order_ref=order.ref)
    assert alert.payload["deadline_at"] == timer.payload["expires_at"]
    # 5 min de prazo: o aviso sai com 1min40s corridos, faltando 3min20s.
    assert timer.available_at - alert.available_at == timedelta(minutes=3, seconds=20)


def test_aviso_da_encomenda_sai_aos_20_minutos():
    _web_channel()
    order = _order("WEB-ENC-5", delivery_date=_tomorrow())

    timer = _schedule(order)

    alert = Directive.objects.get(topic="order.stale_new_alert", payload__order_ref=order.ref)
    assert alert.payload["deadline_at"] == timer.payload["expires_at"]
    assert timer.available_at - alert.available_at == timedelta(minutes=40)


def test_titulo_e_corpo_do_aviso_dizem_a_mesma_hora():
    """O título da janela ("Responda em…") conta até o prazo do pedido, não a régua de 5 min."""
    from shopman.backstage.alert_specs import deadline_for, deadline_kind
    from shopman.backstage.models import OperatorAlert
    from shopman.shop.handlers.confirmation import StaleNewOrderAlertHandler

    _web_channel()
    order = _order("WEB-ENC-6", delivery_date=_tomorrow())
    _schedule(order)
    directive = Directive.objects.get(topic="order.stale_new_alert", payload__order_ref=order.ref)
    deadline = datetime.fromisoformat(directive.payload["deadline_at"])
    alert_at = datetime.fromisoformat(directive.payload["alert_at"])

    with patch("django.utils.timezone.now", return_value=alert_at + timedelta(seconds=1)):
        StaleNewOrderAlertHandler().handle(message=directive, ctx={})

    alert = OperatorAlert.objects.get(type="stale_new_order", order_ref=order.ref)
    assert alert.respond_by == deadline
    assert deadline_kind(alert) == "external"
    assert deadline_for(alert) == deadline
    assert timezone.localtime(deadline).strftime("%H:%M") in alert.message


# ── O canal ─────────────────────────────────────────────────────────────────


def test_prazo_de_encomenda_so_vale_com_prazo_automatico():
    with pytest.raises(ValueError, match="preorder_timeout_minutes"):
        ChannelConfig.from_dict({"confirmation": {"mode": "manual", "preorder_timeout_minutes": 60}}).validate()


@pytest.mark.parametrize("value", [0, -5, True, "60"])
def test_prazo_de_encomenda_e_inteiro_positivo(value):
    config = ChannelConfig.from_dict(
        {"confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "preorder_timeout_minutes": value}},
    )
    with pytest.raises(ValueError, match="preorder_timeout_minutes"):
        config.validate()


def test_auto_cancel_recusa_aviso_com_numero_proprio():
    config = ChannelConfig.from_dict(
        {"confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "stale_new_alert_minutes": 2}},
    )
    with pytest.raises(ValueError, match="stale_new_alert_minutes"):
        config.validate()


def test_migracao_leva_a_loja_online_a_5_e_60():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(
        ref="web",
        name="Loja online",
        config={
            "short_name": "Site",
            "confirmation": {"mode": "auto_cancel", "timeout_minutes": 30, "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
        },
    )
    whatsapp = Channel.objects.create(
        ref="whatsapp",
        name="WhatsApp",
        config={"confirmation": {"mode": "manual", "stale_new_alert_minutes": 10}},
    )
    whatsapp_before = dict(whatsapp.config)

    migration = importlib.import_module("shopman.shop.migrations.0114_prazo_de_aceite_5_no_dia_60_na_encomenda")
    migration.forwards(apps, None)
    migration.forwards(apps, None)  # idempotente

    web.refresh_from_db()
    whatsapp.refresh_from_db()
    assert web.config == {
        "short_name": "Site",
        "confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "preorder_timeout_minutes": 60},
        "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
    }
    assert whatsapp.config == whatsapp_before
    ChannelConfig.for_channel("web")  # valida


def test_migracao_nao_esmaga_prazo_ajustado_a_mao():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(
        ref="web",
        name="Loja online",
        config={"confirmation": {"mode": "auto_cancel", "timeout_minutes": 12, "preorder_timeout_minutes": 90}},
    )
    before = dict(web.config)

    migration = importlib.import_module("shopman.shop.migrations.0114_prazo_de_aceite_5_no_dia_60_na_encomenda")
    migration.forwards(apps, None)

    web.refresh_from_db()
    assert web.config == before
