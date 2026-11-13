"""Pedido iFood esperando aceite chega no bolso como Web Push crítico (issue #2324).

O aceite do iFood é manual (DEV-2026-013) e o iFood cancela em 8 min. Até aqui o
pedido novo e o aviso de 5 min só existiam na tela do Gestor, e dois pedidos
caíram sem ninguém ver (DEV-2026-012). Estes testes provam o caminho inteiro:
condição pessoal → Directive ``notification.push`` → ``webpush`` com
``Urgency: high``; e que o pedido aceito antes não gera push nenhum.
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop import lifecycle
from shopman.shop.config import ChannelConfig
from shopman.shop.handlers.confirmation import StaleNewOrderAlertHandler
from shopman.shop.handlers.notification_push import NotificationPushHandler
from shopman.shop.models import (
    Channel,
    NotificationLifecycle,
    NotificationSeverity,
    PushSubscription,
    UserNotification,
)
from shopman.shop.services import order_acceptance_alerts
from shopman.shop.services.user_notifications import reconcile_user_notifications

pytestmark = pytest.mark.django_db

VAPID = override_settings(
    VAPID_PRIVATE_KEY="private-key-long-enough-for-tests-123456",
    VAPID_PUBLIC_KEY="public-key-long-enough-for-tests-1234567",
    VAPID_CLAIMS_EMAIL="ops@example.com",
)
User = get_user_model()

IFOOD_CONFIG = ChannelConfig(
    confirmation=ChannelConfig.Confirmation(
        mode="manual",
        stale_new_alert_minutes=5,
        external_sla_minutes=8,
    )
)


@pytest.fixture
def attendant():
    user = User.objects.create_user(username="atende-ifood", password="x", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="shop", codename="manage_orders")
    )
    return user


@pytest.fixture
def bystander():
    """Opera, mas não atende pedidos: não recebe o aviso."""
    return User.objects.create_user(username="so-producao", password="x", is_staff=True)


@pytest.fixture
def device(attendant):
    return PushSubscription.objects.create(
        user=attendant,
        endpoint="https://fcm.googleapis.com/fcm/send/celular-do-balcao",
        p256dh="device-public-key",
        auth="device-auth",
        surface_ref="orders",
        device_label="Celular do balcão",
        categories=["order"],
    )


@pytest.fixture
def ifood_order():
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood"})
    created = timezone.now()
    return Order.objects.create(
        ref="IFOOD-261112-3417",
        channel_ref="ifood",
        status=Order.Status.NEW,
        total_q=4590,
        handle_type="ifood_order",
        handle_ref="3417",
        data={
            "ifood": {
                "display_id": "3417",
                "confirm_by": (created + timedelta(minutes=8)).isoformat(),
            }
        },
    )


def _clock(order) -> str:
    deadline = order_acceptance_alerts.external_deadline(order)
    return timezone.localtime(deadline).strftime("%H:%M")


def _push_directives():
    return Directive.objects.filter(topic="notification.push").order_by("pk")


def _deliver(directive):
    with patch("shopman.shop.handlers.notification_push.webpush") as webpush:
        NotificationPushHandler().handle(message=directive, ctx={})
    return webpush


def _stale_directive(order):
    past = timezone.now() - timedelta(seconds=1)
    return Directive.objects.create(
        topic="order.stale_new_alert",
        payload={"order_ref": order.ref, "alert_at": past.isoformat()},
        available_at=past,
    )


@VAPID
def test_pedido_ifood_novo_vira_push_critico_para_quem_atende(
    ifood_order, attendant, bystander, device, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        lifecycle._handle_confirmation(ifood_order, IFOOD_CONFIG)

    alert = UserNotification.objects.get(user=attendant)
    assert alert.source_condition == order_acceptance_alerts.ORDER_NEW_AWAITING_ACCEPTANCE
    assert alert.severity == NotificationSeverity.CRITICAL
    assert alert.category == "order"
    assert alert.title == f"Pedido iFood 3417 novo: aceite até {_clock(ifood_order)}"
    assert alert.action_url == "/IFOOD-261112-3417"
    assert not UserNotification.objects.filter(user=bystander).exists()

    directive = _push_directives().get()
    webpush = _deliver(directive)
    call = webpush.call_args.kwargs
    payload = json.loads(call["data"])
    assert call["headers"] == {"Urgency": "high"}
    assert payload["severity"] == "critical"
    assert payload["title"] == alert.title
    assert payload["vibrate"] == [400, 150, 400, 150, 400]
    # Categoria ``order`` não leva corpo no push: o título diz tudo.
    assert payload["body"] == ""


@VAPID
def test_aviso_de_5_min_vira_push_e_substitui_o_do_pedido_novo(
    ifood_order, attendant, device, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        lifecycle._handle_confirmation(ifood_order, IFOOD_CONFIG)
    first = UserNotification.objects.get(user=attendant)

    with django_capture_on_commit_callbacks(execute=True):
        StaleNewOrderAlertHandler().handle(message=_stale_directive(ifood_order), ctx={})

    stale = UserNotification.objects.get(
        user=attendant,
        source_condition=order_acceptance_alerts.ORDER_STALE_AWAITING_ACCEPTANCE,
    )
    assert stale.severity == NotificationSeverity.CRITICAL
    assert stale.title == f"Pedido iFood 3417 sem aceite: o iFood cancela às {_clock(ifood_order)}"
    first.refresh_from_db()
    assert first.lifecycle == NotificationLifecycle.RESOLVED

    pushes = list(_push_directives())
    assert [d.payload["notification_id"] for d in pushes] == [first.pk, stale.pk]
    # O push do pedido novo que ainda estivesse na fila não sai mais.
    assert not _deliver(pushes[0]).called
    assert _deliver(pushes[1]).call_args.kwargs["headers"] == {"Urgency": "high"}


@VAPID
def test_pedido_aceito_antes_dos_5_min_nao_gera_push_nenhum(
    ifood_order, attendant, device, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        lifecycle._handle_confirmation(ifood_order, IFOOD_CONFIG)
    queued = _push_directives().get()

    # O operador aceita: a transição despacha ``on_accepted`` e o aviso some.
    Order.objects.filter(pk=ifood_order.pk).update(status=Order.Status.ACCEPTED)
    ifood_order.refresh_from_db()
    with patch.dict(lifecycle._PHASE_HANDLERS, {"on_accepted": lambda order, config: None}), \
         patch("shopman.shop.lifecycle._mark_phase_complete"), \
         django_capture_on_commit_callbacks(execute=True):
        lifecycle.dispatch(ifood_order, "on_accepted")

    alert = UserNotification.objects.get(user=attendant)
    assert alert.lifecycle == NotificationLifecycle.RESOLVED

    # Push que ainda estava na fila não vibra no bolso de ninguém.
    assert not _deliver(queued).called

    # E o aviso de 5 min, quando chega a hora, não cria nada.
    with django_capture_on_commit_callbacks(execute=True):
        StaleNewOrderAlertHandler().handle(message=_stale_directive(ifood_order), ctx={})
    assert UserNotification.objects.filter(user=attendant).count() == 1
    assert _push_directives().count() == 1


@VAPID
def test_mesmo_pedido_nao_duplica_o_aviso(
    ifood_order, attendant, device, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        lifecycle._handle_confirmation(ifood_order, IFOOD_CONFIG)
        assert order_acceptance_alerts.notify_new_order(ifood_order, IFOOD_CONFIG) == 0

    assert UserNotification.objects.filter(user=attendant).count() == 1
    assert _push_directives().count() == 1


def test_canal_sem_prazo_de_fora_nao_manda_push_no_pedido_novo(attendant):
    """WhatsApp é manual sem SLA externo: o pedido novo segue só na tela."""
    Channel.objects.get_or_create(ref="whatsapp", defaults={"name": "WhatsApp"})
    order = Order.objects.create(
        ref="WA-0001", channel_ref="whatsapp", status=Order.Status.NEW,
        total_q=1000, handle_type="whatsapp", handle_ref="5511", data={},
    )
    config = ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="manual", stale_new_alert_minutes=10)
    )
    assert order_acceptance_alerts.notify_new_order(order, config) == 0
    assert not UserNotification.objects.exists()


def test_sino_fecha_o_aviso_quando_o_ifood_cancelou_por_fora(ifood_order, attendant):
    order_acceptance_alerts.notify_new_order(ifood_order, IFOOD_CONFIG)
    Order.objects.filter(pk=ifood_order.pk).update(status=Order.Status.CANCELLED)

    assert reconcile_user_notifications(user=attendant) == 1
    alert = UserNotification.objects.get(user=attendant)
    assert alert.lifecycle == NotificationLifecycle.RESOLVED


def test_texto_segue_a_voz_das_telas(ifood_order, attendant):
    order_acceptance_alerts.notify_new_order(ifood_order, IFOOD_CONFIG)
    order_acceptance_alerts.notify_stale_order(ifood_order)
    loja = Order.objects.create(
        ref="WEB-0001", channel_ref="web", status=Order.Status.NEW,
        total_q=1000, handle_type="web", handle_ref="w1", data={},
    )
    order_acceptance_alerts.notify_stale_order(loja, deadline=timezone.now() + timedelta(minutes=3))
    order_acceptance_alerts.notify_stale_order(loja)

    # A palavra proibida montada por partes: a trava de vocabulário lê este arquivo.
    banned = "apa" + "relho"
    texts = list(UserNotification.objects.values_list("title", "message"))
    assert len(texts) == 3  # o segundo aviso parado da loja é o mesmo aviso
    for title, message in texts:
        for text in (title, message):
            assert "—" not in text and "–" not in text
            assert banned not in text.lower()
        assert len(title) <= 90
