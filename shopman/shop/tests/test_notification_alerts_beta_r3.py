"""Avisos e worker: achados do beta de 06/11/2026 (3a rodada).

Cada teste aqui reprova sem o conserto correspondente:

- W1: aviso INTERNO (estoque baixo, pedido de compra) que não sai vira alerta
  com texto próprio e a causa real, não o texto de aviso ao cliente do pedido.
- W2: o ``notification.send`` tem régua própria de retry; o alerta só sai
  quando ela acaba.
- W4: aviso crítico sem canal falha (retry e alerta), não é pulado.
- W6: alertas da fila sem jargão nem travessão; o ERROR de "sem e-mail" sai
  uma vez só.
- W7: o alerta do lifecycle não se repete com a causa aberta.
- PIXEXP-08: alerta ao operador em português, sem chave interna nem erro cru.
- PIXEXP-09: em DEBUG o console entra no fim da cadeia do cliente sem opt-out.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

#: Identificador de máquina (snake_case) ou inglês de erro: não aparece na tela.
_MACHINE_TEXT = re.compile(r"\b[a-z]+_[a-z_]+\b|\b(backend|available|unknown|pending|notification)\b")


def _order(**data):
    order = MagicMock()
    order.ref = "ORD-R3"
    order.total_q = 5000
    order.status = "new"
    order.handle_type = ""
    order.handle_ref = ""
    order.data = data
    order.snapshot = {"items": [], "data": {}}
    order.channel_ref = "web"
    order.channel = SimpleNamespace(ref="web", name="Web", config={})
    return order


def _open_notification_alerts(order_ref=None):
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(type="notification_failed", resolved_at__isnull=True)
    if order_ref is not None:
        qs = qs.filter(order_ref=order_ref)
    return list(qs)


# ── W2: régua própria do aviso ──────────────────────────────────────────────


def test_notification_handler_declares_a_retry_window_of_minutes_not_seconds():
    from shopman.orderman.dispatch import retry_policy

    from shopman.shop.handlers.notification import NotificationSendHandler

    handler = NotificationSendHandler()
    max_attempts, _ = retry_policy(handler, 1)
    total_wait = sum(retry_policy(handler, attempt)[1] for attempt in range(1, max_attempts))

    assert max_attempts == 6
    # A régua padrão (2+4+8+16 = 30 s) perdia o aviso numa queda de 1 minuto.
    assert total_wait >= 8 * 60


@pytest.mark.django_db
@pytest.mark.parametrize(("attempts", "exhausted"), [(5, False), (6, True)])
def test_order_notice_alerts_only_when_the_handler_window_ends(attempts, exhausted):
    from shopman.orderman.models import Order

    from shopman.shop.handlers.notification import NotificationSendHandler

    Order.objects.create(
        ref="ORD-R3W2", channel_ref="web", session_key="s-r3w2", status="new", total_q=1500,
        data={"customer_phone": "+5543999999999"},
    )
    directive = Directive.objects.create(
        topic="notification.send",
        dedupe_key="notification.send:ORD-R3W2:order_ready",
        payload={"order_ref": "ORD-R3W2", "template": "order_ready",
                 "notification_delivery": {"status": "failed", "outcome": "not_applied"}},
        attempts=attempts,
        status="running",
    )

    def rejected(order, template, payload):
        payload["notification_delivery"] = {"status": "failed", "outcome": "not_applied"}
        return False, "provider timeout"

    expected = DirectiveTerminalError if exhausted else DirectiveTransientError
    with patch(
        "shopman.shop.handlers.notification.notification_svc.deliver_order_notification",
        side_effect=rejected,
    ):
        with pytest.raises(expected):
            NotificationSendHandler().handle(message=directive, ctx={})

    assert len(_open_notification_alerts("ORD-R3W2")) == (1 if exhausted else 0)


# ── PIXEXP-08: alerta de aviso de pedido em português ───────────────────────


@pytest.mark.django_db
def test_exhausted_order_notice_alert_speaks_portuguese_without_machine_names():
    from shopman.shop.handlers.notification import NotificationSendHandler

    NotificationSendHandler()._escalate(
        "NB-R3-X96", "order_cancelled", "no active notification backend available", attempts=6,
    )

    [alert] = _open_notification_alerts("NB-R3-X96")
    assert '"Pedido cancelado"' in alert.message
    assert "nenhum canal de envio está ligado" in alert.message
    assert "6 tentativas" in alert.message
    assert not _MACHINE_TEXT.search(alert.message), alert.message
    assert "—" not in alert.message


@pytest.mark.django_db
def test_raw_provider_error_never_reaches_the_operator():
    from shopman.shop.handlers.notification import NotificationSendHandler

    NotificationSendHandler()._escalate("NB-R3-PRV", "order_ready", "HTTP 503 upstream_unavailable", attempts=6)

    [alert] = _open_notification_alerts("NB-R3-PRV")
    assert "upstream" not in alert.message
    assert "o canal recusou o envio" in alert.message
    assert '"Pedido pronto"' in alert.message


@pytest.mark.django_db
def test_order_notice_alert_dedupes_by_the_readable_name():
    from shopman.shop.handlers.notification import NotificationSendHandler

    handler = NotificationSendHandler()
    handler._escalate("NB-R3-DUP", "waitlist_available", "provider timeout", attempts=6)
    handler._escalate("NB-R3-DUP", "waitlist_available", "provider timeout", attempts=6)

    assert len(_open_notification_alerts("NB-R3-DUP")) == 1


def test_dead_pix_charge_status_is_said_in_portuguese():
    from shopman.shop.services.pix_confirmation import _charge_status_label

    # A cobrança morta ainda ``pending`` é a que venceu: "encerrada (pending)"
    # era inglês e contradição.
    assert _charge_status_label("pending") == "vencida"
    assert _charge_status_label("cancelled") == "cancelada"
    assert _charge_status_label("anything_else") == "fora do prazo"


# ── W1: aviso interno não vira aviso ao cliente ─────────────────────────────


def _unavailable_email_backend():
    return SimpleNamespace(is_available=lambda recipient=None: False)


@pytest.mark.django_db
def test_exhausted_stock_alert_email_is_a_system_alert_with_the_real_cause():
    from shopman.shop.handlers.notification import NotificationSendHandler

    directive = Directive.objects.create(
        topic="notification.send",
        payload={
            "event": "stock.alert.triggered",
            "backends": ["email"],
            "recipient": "ti@example.com",
            "context": {"sku": "AGUA-MINERAL-PRATA-310", "product_name": "Água mineral Prata"},
        },
        attempts=6,
        status="running",
    )

    with patch("shopman.shop.notifications.get_backend", return_value=_unavailable_email_backend()):
        with pytest.raises(DirectiveTerminalError):
            NotificationSendHandler().handle(message=directive, ctx={})

    [alert] = _open_notification_alerts("")
    assert "alerta de estoque baixo de Água mineral Prata (AGUA-MINERAL-PRATA-310)" in alert.message
    assert "e-mail não está configurado" in alert.message
    assert "cliente do pedido" not in alert.message
    assert "desconhecido" not in alert.message
    assert "  " not in alert.message


@pytest.mark.django_db
def test_system_notice_before_the_window_ends_retries_without_alert():
    from shopman.shop.handlers.notification import NotificationSendHandler

    directive = Directive.objects.create(
        topic="notification.send",
        payload={"event": "stock.alert.triggered", "backends": ["email"], "recipient": "ti@example.com",
                 "context": {"sku": "SKU-1", "product_name": "Pão"}},
        attempts=5,
        status="running",
    )

    with patch("shopman.shop.notifications.get_backend", return_value=_unavailable_email_backend()):
        with pytest.raises(DirectiveTransientError):
            NotificationSendHandler().handle(message=directive, ctx={})

    assert _open_notification_alerts("") == []


@pytest.mark.django_db
def test_exhausted_purchase_request_points_to_the_supplier_not_the_customer():
    from shopman.shop.handlers.notification import NotificationSendHandler

    NotificationSendHandler()._escalate_system(
        "purchase_request",
        {"purchase_ref": "PC-FARINHA-01", "supplier_name": "Moinho Sul"},
        ["WhatsApp recusou o envio"],
        attempts=6,
    )

    [alert] = _open_notification_alerts("")
    assert "pedido de compra PC-FARINHA-01 não chegou ao fornecedor Moinho Sul" in alert.message
    assert "contato do fornecedor" in alert.message
    assert "cliente" not in alert.message


# ── W4: crítico implica obrigatório ─────────────────────────────────────────


@pytest.mark.django_db
def test_critical_order_accepted_without_any_channel_fails_instead_of_skipping():
    from shopman.shop.services.notification import deliver_order_notification

    order = _order(customer_ref="CLI-001")
    payload = {"order_ref": order.ref, "customer_ref": "CLI-001"}

    with (
        patch("shopman.shop.services.notification._resolve_backend_chain", return_value=["manychat"]),
        patch("shopman.shop.services.notification._revoked_notification_channels", return_value=set()),
    ):
        success, error = deliver_order_notification(order, "order_accepted", payload)

    assert success is False
    assert error == "no active notification recipient available"
    assert payload["notification_delivery"]["status"] == "failed"


def test_critical_templates_are_required():
    from shopman.shop.services.notification import (
        CRITICAL_NOTIFICATION_TEMPLATES,
        requires_active_notification,
    )

    assert all(requires_active_notification(template) for template in CRITICAL_NOTIFICATION_TEMPLATES)


# ── PIXEXP-09: console no fim da cadeia em dev ──────────────────────────────


@pytest.mark.parametrize(("debug", "expected"), [
    (True, ["manychat", "sms", "email", "console"]),
    (False, ["manychat", "sms", "email"]),
])
def test_dev_console_closes_the_chain_of_a_customer_without_opt_out(debug, expected):
    from shopman.shop.services.notification import _filter_backend_chain

    order = _order(customer_ref="CLI-NEW")
    with (
        override_settings(DEBUG=debug),
        patch("shopman.shop.services.notification._revoked_notification_channels", return_value=set()),
    ):
        chain = _filter_backend_chain(
            order,
            ["manychat", "sms", "email", "console"],
            payload={"customer_ref": "CLI-NEW"},
            requires_active=True,
        )

    assert chain == expected


@pytest.mark.parametrize("chain", [["console", "manychat", "sms"], ["manychat", "console", "sms"]])
def test_dev_console_never_goes_ahead_of_real_channels(chain):
    from shopman.shop.services.notification import _filter_backend_chain

    with (
        override_settings(DEBUG=True),
        patch("shopman.shop.services.notification._revoked_notification_channels", return_value=set()),
    ):
        filtered = _filter_backend_chain(
            _order(customer_ref="CLI-NEW"), chain, payload={"customer_ref": "CLI-NEW"}, requires_active=True,
        )

    assert filtered == ["manychat", "sms", "console"]


# ── W6: alertas da fila ─────────────────────────────────────────────────────


@pytest.mark.django_db
@override_settings(
    SHOPMAN_DIRECTIVE_FAILED_ALERT_THRESHOLD=1,
    SHOPMAN_DIRECTIVE_BACKLOG_ALERT_THRESHOLD=1,
    SHOPMAN_ALERT_EMAIL="",
)
def test_queue_health_alerts_speak_the_operator_language():
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from shopman.backstage.models import OperatorAlert
    from shopman.backstage.projections.alerts import readable_message

    old = timezone.now() - timedelta(hours=1)
    Directive.objects.bulk_create([
        Directive(topic="r3.failed", payload={}, status="failed"),
        Directive(topic="r3.queued", payload={}, status="queued", available_at=old),
        Directive(topic="r3.queued", payload={}, status="queued", available_at=old),
    ])

    call_command("check_directive_health")

    alerts = list(OperatorAlert.objects.filter(type__in=["directive_failed_spike", "directive_backlog"]))
    assert {a.type for a in alerts} == {"directive_failed_spike", "directive_backlog"}
    for alert in alerts:
        # O que a tela mostra: a mensagem sem o marcador de dedupe do banco.
        shown = readable_message(alert.message)
        assert "—" not in shown, shown
        assert not re.search(r"directive|worker|pipeline|process_directives|Admin", shown), shown
        assert "tarefa" in shown


@pytest.mark.django_db
@override_settings(SHOPMAN_ALERT_EMAIL="")
def test_missing_alert_email_is_logged_once_per_critical_queue_alert():
    from shopman.shop.services import critical_alerts
    from shopman.shop.services.observability import create_operator_alert

    with patch.object(critical_alerts, "logger") as logger:
        alert = create_operator_alert(
            type="directive_worker_stale", severity="critical", message="parado",
            dedupe_key="r3:worker_stale",
        )
        assert critical_alerts.deliver_now(alert) is None

    missing = [c for c in logger.error.call_args_list if "external_recipient_missing" in c.args[0]]
    assert len(missing) == 1


# ── W7: alerta do lifecycle não se repete ───────────────────────────────────


@pytest.mark.django_db
def test_redispatched_phase_does_not_duplicate_the_open_alert():
    from shopman.backstage.models import OperatorAlert
    from shopman.shop.lifecycle import _create_alert

    order = SimpleNamespace(ref="NB-R3-U37")
    _create_alert(order, "payment_awaiting_confirmation")
    _create_alert(order, "payment_awaiting_confirmation")

    open_alerts = OperatorAlert.objects.filter(
        type="payment_awaiting_confirmation", order_ref="NB-R3-U37", resolved_at__isnull=True,
    )
    assert open_alerts.count() == 1
