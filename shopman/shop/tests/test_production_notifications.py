"""
Notificações de produção (WP-PE2) — par alerta-na-tela + notification.send.

Todo alerta de produção vira OperatorAlert incondicionalmente; a notificação
ativa (directive de sistema, email→console com retry) é opt-in via
``Shop.defaults["production"]["notifications"]`` e filtrada por severidade.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Directive

from shopman.backstage.models import OperatorAlert
from shopman.shop.directives import NOTIFICATION_SEND, PRODUCTION_LATE_CHECK
from shopman.shop.handlers.production_alerts import (
    check_forgotten_planned_orders,
    check_late_started_orders,
    create_stock_short_alert,
    create_stock_shortfall_alert,
    maybe_create_low_yield_alert,
)
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="brioche",
        name="Brioche",
        output_sku="BRIOCHE",
        batch_size=1,
        meta={"max_started_minutes": 60},
    )


def _shop(notifications: dict):
    return Shop.objects.create(
        name="Nelson", defaults={"production": {"notifications": notifications}}
    )


def _notification_directives():
    return Directive.objects.filter(topic=NOTIFICATION_SEND)


def _late_started_wo(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10)
    type(wo).objects.filter(pk=wo.pk).update(started_at=timezone.now() - timedelta(hours=2))
    return wo


class TestNotificationGating:
    def test_disabled_by_default_creates_alert_only(self, recipe):
        create_stock_short_alert(
            work_order_ref="WO-X", output_sku="BRIOCHE", error="faltou farinha"
        )
        assert OperatorAlert.objects.filter(type="production_stock_short").exists()
        assert not _notification_directives().exists()

    def test_enabled_error_severity_notifies_stock_short(self, recipe):
        _shop({"enabled": True})
        create_stock_short_alert(
            work_order_ref="WO-X", output_sku="BRIOCHE", error="faltou farinha"
        )
        directive = _notification_directives().get()
        assert directive.payload["event"] == "production_stock_short"
        assert directive.payload["context"]["work_order_ref"] == "WO-X"
        assert directive.payload["context"]["error"] == "faltou farinha"

    def test_default_severities_skip_warnings(self, recipe):
        _shop({"enabled": True})  # severities default = ["error"]
        _late_started_wo(recipe)
        assert check_late_started_orders() == 1
        assert not _notification_directives().exists()

    def test_widened_severities_notify_warnings(self, recipe):
        _shop({"enabled": True, "severities": ["error", "warning"]})

        _late_started_wo(recipe)
        assert check_late_started_orders() == 1

        craft.plan(recipe, 5, date=date.today() - timedelta(days=1))
        assert check_forgotten_planned_orders() == 1

        events = sorted(d.payload["event"] for d in _notification_directives())
        assert events == ["production_forgotten", "production_late"]

    def test_low_yield_pairs_alert_and_notification(self, recipe):
        _shop({"enabled": True, "severities": ["warning"]})
        wo = craft.plan(recipe, 10, date=date.today())
        craft.start(wo, quantity=10)
        craft.finish(order=wo, finished=5)  # yield 50% < 80%
        wo.refresh_from_db()

        assert maybe_create_low_yield_alert(wo) is False  # signal já criou (dedup)
        assert OperatorAlert.objects.filter(type="production_low_yield").count() == 1
        directive = _notification_directives().get()
        assert directive.payload["event"] == "production_low_yield"
        assert directive.payload["context"]["yield_percent"] == 50

    def test_dedup_prevents_duplicate_notifications(self, recipe):
        _shop({"enabled": True, "severities": ["warning"]})
        _late_started_wo(recipe)
        assert check_late_started_orders() == 1
        assert check_late_started_orders() == 0  # dedup no alerta
        assert _notification_directives().count() == 1


class TestStockShortfallAlert:
    """A sub-baixa REAL de insumo (já commitada na ponte) vira OperatorAlert.

    Distinta de ``production_stock_short`` (falta prevista antes do finish): esta
    é ``production_stock_shortfall``, a falta que a ponte craftsman→stockman
    baixou a menos — não pode ficar só no log (dinheiro/estoque: falhar gritando).
    """

    def _shortfalls(self):
        from decimal import Decimal

        return [
            {
                "sku": "FARINHA",
                "needed": Decimal("1.0"),
                "issued": Decimal("0.4"),
                "short": Decimal("0.6"),
            }
        ]

    def test_creates_error_alert_naming_ingredient_and_shortfall(self, recipe):
        create_stock_shortfall_alert(
            work_order_ref="WO-9", output_sku="BRIOCHE", shortfalls=self._shortfalls()
        )
        alert = OperatorAlert.objects.get(type="production_stock_shortfall")
        assert alert.severity == "error"
        assert alert.order_ref == "WO-9"
        assert "FARINHA" in alert.message
        assert "0.6" in alert.message
        assert not _notification_directives().exists()  # opt-in, desligado por padrão

    def test_empty_shortfalls_is_a_noop(self, recipe):
        create_stock_shortfall_alert(
            work_order_ref="WO-9", output_sku="BRIOCHE", shortfalls=[]
        )
        assert not OperatorAlert.objects.filter(type="production_stock_shortfall").exists()

    def test_dedup_prevents_second_alert_for_same_wo(self, recipe):
        create_stock_shortfall_alert(
            work_order_ref="WO-9", output_sku="BRIOCHE", shortfalls=self._shortfalls()
        )
        create_stock_shortfall_alert(
            work_order_ref="WO-9", output_sku="BRIOCHE", shortfalls=self._shortfalls()
        )
        assert OperatorAlert.objects.filter(type="production_stock_shortfall").count() == 1

    def test_enabled_error_severity_notifies_with_jsonable_context(self, recipe):
        _shop({"enabled": True})  # severities default = ["error"]
        create_stock_shortfall_alert(
            work_order_ref="WO-9", output_sku="BRIOCHE", shortfalls=self._shortfalls()
        )
        directive = _notification_directives().get()
        assert directive.payload["event"] == "production_stock_shortfall"
        # Decimais viram string — o payload da Directive é JSON.
        short = directive.payload["context"]["shortfalls"][0]
        assert short == {
            "sku": "FARINHA",
            "needed": "1.0",
            "issued": "0.4",
            "short": "0.6",
        }


class TestSystemNotificationDelivery:
    def test_handler_routes_production_event_to_operator(self, settings):
        """O caminho de sistema entrega o template de produção sem order_ref."""
        from shopman.shop.handlers.notification import NotificationSendHandler
        from shopman.shop.models import NotificationTemplate

        NotificationTemplate.objects.create(
            event="production_late",
            subject="Produção {work_order_ref} atrasada",
            body="A produção {work_order_ref} ({output_sku}) está há {elapsed_minutes} min.",
            is_active=True,
        )
        directive = Directive.objects.create(
            topic=NOTIFICATION_SEND,
            payload={
                "event": "production_late",
                "context": {
                    "work_order_ref": "WO-2026-00001",
                    "output_sku": "BRIOCHE",
                    "elapsed_minutes": 95,
                },
            },
        )
        # Não deve levantar: email falha sem SMTP e console absorve.
        NotificationSendHandler().handle(message=directive, ctx={})

    def test_handler_routes_system_event_to_explicit_supplier_recipient(self, monkeypatch, settings):
        # ⚠️ O canal precisa DIZER que entrega, senão a cadeia o pula antes de
        # chegar no `notify` — e é isso que este teste mede (o roteamento até o
        # fornecedor, não a configuração do SMTP). O default da suíte é o backend
        # de console, que passou a se declarar indisponível de propósito: ele
        # imprime em stdout e devolvia sucesso, curto-circuitando SMS e WhatsApp.
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = "smtp.exemplo.test"
        # ...e um REMETENTE entregável. `is_available` também recusa domínio
        # reservado (`.local`, `example.*`), que é o default de `settings.py`:
        # SMTP de pé com remetente que não existe no DNS é o mesmo fail-open,
        # por outra porta. Aqui o alvo é o roteamento, então o remetente é real.
        settings.DEFAULT_FROM_EMAIL = "nelson@boulangerie.com.br"
        from shopman.shop.handlers.notification import NotificationSendHandler

        calls = []

        def fake_notify(*, event, recipient, context, backend):
            calls.append({
                "event": event,
                "recipient": recipient,
                "context": context,
                "backend": backend,
            })
            return SimpleNamespace(success=True, error=None)

        monkeypatch.setattr("shopman.shop.handlers.notification.notify", fake_notify)
        directive = Directive.objects.create(
            topic=NOTIFICATION_SEND,
            payload={
                "event": "purchase_request",
                "recipient": "compras@moinho.example",
                "backends": ["email"],
                "context": {
                    "supplier_name": "Moinho São Paulo",
                    "material_name": "Farinha T65",
                    "purchase_qty_display": "3 saco 25 kg",
                },
            },
        )

        NotificationSendHandler().handle(message=directive, ctx={})

        assert calls == [
            {
                "event": "purchase_request",
                "recipient": "compras@moinho.example",
                "backend": "email",
                "context": directive.payload["context"],
            }
        ]


class TestHeartbeatNotifies:
    def test_late_check_heartbeat_emits_notification_when_enabled(self, recipe):
        from shopman.shop.handlers.production_alerts import ProductionLateCheckHandler

        _shop({"enabled": True, "severities": ["error", "warning"]})
        _late_started_wo(recipe)
        Directive.objects.all().delete()

        heartbeat = Directive.objects.create(
            topic=PRODUCTION_LATE_CHECK, status="running", payload={}
        )
        ProductionLateCheckHandler().handle(message=heartbeat, ctx={})

        assert _notification_directives().count() == 1
        assert OperatorAlert.objects.filter(type="production_late").count() == 1
