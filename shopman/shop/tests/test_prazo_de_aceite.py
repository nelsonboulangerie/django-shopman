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


# ── Loja aberta nas duas pontas: o prazo não vence com a casa fechada ───────


def _shop_7_to_19():
    hours = {"open": "07:00", "close": "19:00"}
    Shop.objects.create(
        name="Loja",
        timezone="America/Sao_Paulo",
        opening_hours=dict.fromkeys(
            ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"), hours,
        ),
    )
    return ZoneInfo("America/Sao_Paulo")


def _alert_at(order: Order):
    return Directive.objects.get(topic="order.stale_new_alert", payload__order_ref=order.ref).available_at


def test_encomenda_paga_na_ultima_hora_nao_vence_com_a_loja_fechada():
    """18:30 + 60 min com a casa fechando às 19:00: 30 hoje, 30 depois de abrir."""
    tz = _shop_7_to_19()
    _web_channel()
    evening = datetime(2026, 11, 9, 18, 30, tzinfo=tz)
    order = _order("WEB-ENC-7", delivery_date=evening.date() + timedelta(days=2))

    with patch("django.utils.timezone.now", return_value=evening):
        timer = _schedule(order)

    assert datetime.fromisoformat(timer.payload["expires_at"]) == datetime(2026, 11, 10, 7, 30, tzinfo=tz)
    # O aviso de 1/3 (20 min de loja aberta) ainda cabe no mesmo dia.
    assert _alert_at(order) == datetime(2026, 11, 9, 18, 50, tzinfo=tz)
    # Às 19:30, com a casa fechada, o pedido NÃO é cancelado.
    assert _run_timer_at(order, datetime(2026, 11, 9, 19, 30, tzinfo=tz)).status == Order.Status.NEW


def test_aviso_da_encomenda_tambem_espera_a_abertura():
    """18:50 + 60: sobram 10 min hoje. O aviso (20 min) sai 10 min depois de abrir, não às 19:10."""
    tz = _shop_7_to_19()
    _web_channel()
    evening = datetime(2026, 11, 9, 18, 50, tzinfo=tz)
    order = _order("WEB-ENC-8", delivery_date=evening.date() + timedelta(days=2))

    with patch("django.utils.timezone.now", return_value=evening):
        timer = _schedule(order)

    assert datetime.fromisoformat(timer.payload["expires_at"]) == datetime(2026, 11, 10, 7, 50, tzinfo=tz)
    assert _alert_at(order) == datetime(2026, 11, 10, 7, 10, tzinfo=tz)


def test_pedido_do_dia_pago_a_dois_minutos_de_fechar_continua_na_abertura():
    tz = _shop_7_to_19()
    _web_channel()
    closing = datetime(2026, 11, 9, 18, 58, tzinfo=tz)
    order = _order("WEB-DIA-5")

    with patch("django.utils.timezone.now", return_value=closing):
        timer = _schedule(order)

    assert datetime.fromisoformat(timer.payload["expires_at"]) == datetime(2026, 11, 10, 7, 3, tzinfo=tz)
    assert _alert_at(order) == datetime(2026, 11, 9, 18, 59, 40, tzinfo=tz)


# ── As entradas reais do prazo ──────────────────────────────────────────────


def test_timer_grava_o_prazo_que_conta():
    _web_channel()

    assert _schedule(_order("WEB-DIA-6")).payload["timeout_minutes"] == 5
    assert _schedule(_order("WEB-ENC-9", delivery_date=_tomorrow())).payload["timeout_minutes"] == 60


def test_cartao_autorizado_de_encomenda_comeca_o_prazo_de_60():
    from shopman.shop.lifecycle import start_acceptance_deadline

    _web_channel()
    order = _order("WEB-ENC-10", delivery_date=_tomorrow())
    before = timezone.now()

    start_acceptance_deadline(order)

    timer = Directive.objects.get(topic="confirmation.timeout", payload__order_ref=order.ref)
    assert timer.payload["source"] == "card_authorized"
    assert timer.payload["timeout_minutes"] == 60
    assert before + timedelta(minutes=60) <= timer.available_at <= timezone.now() + timedelta(minutes=60)


def test_auto_confirm_com_prazo_de_encomenda_aceita_sozinho_aos_60_sem_aviso():
    from shopman.shop.lifecycle import _schedule_confirmation_timeout

    _web_channel({
        "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "preorder_timeout_minutes": 60},
        "payment": WEB["payment"],
    })
    order = _order("WEB-ENC-11", delivery_date=_tomorrow())
    before = timezone.now()

    timer = _schedule_confirmation_timeout(
        order, ChannelConfig.for_channel("web"), action="confirm", source="order_created",
    )

    assert timer.payload["timeout_minutes"] == 60
    assert before + timedelta(minutes=60) <= timer.available_at <= timezone.now() + timedelta(minutes=60)
    assert not Directive.objects.filter(topic="order.stale_new_alert", payload__order_ref=order.ref).exists()


# ── O padrão da loja não derruba o canal ────────────────────────────────────


def test_aviso_padrao_da_loja_nao_desce_para_o_canal_auto_cancel():
    """``Shop.defaults`` com o aviso dos canais manuais não pode derrubar a loja online."""
    Shop.objects.create(name="Loja", defaults={"confirmation": {"stale_new_alert_minutes": 10}})
    _web_channel()
    Channel.objects.update_or_create(
        ref="whatsapp",
        defaults={"name": "WhatsApp", "is_active": True, "config": {"confirmation": {"mode": "manual"}}},
    )

    assert ChannelConfig.for_channel("web").confirmation.stale_new_alert_minutes == 0
    assert ChannelConfig.for_channel("whatsapp").confirmation.stale_new_alert_minutes == 10


def test_aviso_declarado_no_proprio_canal_auto_cancel_continua_recusado():
    Shop.objects.create(name="Loja", defaults={"confirmation": {"stale_new_alert_minutes": 10}})
    _web_channel({**WEB, "confirmation": {**WEB["confirmation"], "stale_new_alert_minutes": 10}})

    with pytest.raises(ValueError, match="stale_new_alert_minutes"):
        ChannelConfig.for_channel("web")
