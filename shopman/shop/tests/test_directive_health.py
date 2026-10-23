"""check_directive_health — observabilidade mínima da fila (ADR-003).

Três gatilhos viram OperatorAlert (debounce 15min): failed spike, backlog de
queued vencidas, heartbeat do process_directives envelhecido. Estado saudável
NÃO alerta; heartbeat desconhecido (cache por processo em dev/CI, worker nunca
visto) também não.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman import worker_heartbeat
from shopman.orderman.models import Directive

from shopman.backstage.models import OperatorAlert

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _run():
    call_command("check_directive_health", stdout=StringIO())


def _failed(n, *, minutes_ago=5):
    for _ in range(n):
        directive = Directive.objects.create(
            topic="notification.send", status="failed", payload={}, last_error="boom"
        )
        Directive.objects.filter(pk=directive.pk).update(
            updated_at=timezone.now() - timedelta(minutes=minutes_ago)
        )


def _overdue_queued(n, *, minutes_overdue=30):
    for _ in range(n):
        Directive.objects.create(
            topic="notification.send",
            status="queued",
            payload={},
            available_at=timezone.now() - timedelta(minutes=minutes_overdue),
        )


def _stale_heartbeat(minutes: int) -> None:
    worker_heartbeat.beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)
    cache.set(
        worker_heartbeat._KEY_TEMPLATE.format(name=worker_heartbeat.PROCESS_DIRECTIVES_WORKER),
        timezone.now() - timedelta(minutes=minutes),
        None,
    )


# ── failed spike ─────────────────────────────────────────────────────────────


def test_failed_spike_alerts():
    _failed(5)
    _run()
    alert = OperatorAlert.objects.get(type="directive_failed_spike")
    assert alert.severity == "error"


def test_failed_below_threshold_does_not_alert():
    _failed(4)
    _run()
    assert not OperatorAlert.objects.filter(type="directive_failed_spike").exists()


def test_old_failed_outside_window_does_not_alert():
    _failed(5, minutes_ago=120)  # janela default: 60 min
    _run()
    assert not OperatorAlert.objects.filter(type="directive_failed_spike").exists()


# ── backlog de queued vencidas ───────────────────────────────────────────────


def test_overdue_backlog_alerts():
    _overdue_queued(5)
    _run()
    alert = OperatorAlert.objects.get(type="directive_backlog")
    assert alert.severity == "error"


def test_fresh_queued_does_not_alert():
    # Na fila mas dentro do prazo (available_at recente/futuro) = saudável.
    for _ in range(10):
        Directive.objects.create(topic="notification.send", status="queued", payload={})
    _run()
    assert not OperatorAlert.objects.filter(type="directive_backlog").exists()


def test_small_overdue_backlog_does_not_alert():
    _overdue_queued(4)  # threshold default: 5
    _run()
    assert not OperatorAlert.objects.filter(type="directive_backlog").exists()


# ── heartbeat do worker ──────────────────────────────────────────────────────


def test_stale_heartbeat_alerts_critical():
    _stale_heartbeat(minutes=30)  # limiar default: 15 min
    _run()
    alert = OperatorAlert.objects.get(type="directive_worker_stale")
    assert alert.severity == "critical"


def test_fresh_heartbeat_does_not_alert():
    worker_heartbeat.beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)
    _run()
    assert not OperatorAlert.objects.filter(type="directive_worker_stale").exists()


def test_unknown_heartbeat_does_not_alert():
    # Chave ausente = desconhecido (locmem por processo, worker nunca visto).
    _run()
    assert not OperatorAlert.objects.filter(type="directive_worker_stale").exists()


# ── estado saudável e debounce ───────────────────────────────────────────────


def test_healthy_state_creates_no_alerts():
    Directive.objects.create(topic="notification.send", status="done", payload={})
    worker_heartbeat.beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER)
    _run()
    assert OperatorAlert.objects.count() == 0


def test_repeated_check_debounces_alert():
    _failed(5)
    _run()
    _run()
    assert OperatorAlert.objects.filter(type="directive_failed_spike").count() == 1


# ── heartbeats gravados pelos workers ────────────────────────────────────────


def test_process_directives_records_heartbeat():
    call_command("process_directives", stdout=StringIO())
    assert worker_heartbeat.last_beat(worker_heartbeat.PROCESS_DIRECTIVES_WORKER) is not None


def test_maintenance_worker_records_heartbeat():
    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_WORKER

    call_command("maintenance_worker", "--once", stdout=StringIO())
    assert worker_heartbeat.last_beat(MAINTENANCE_WORKER) is not None


# ── o aviso da fila não depende da fila (laudo O3) ───────────────────────────


@pytest.fixture
def paging(settings, monkeypatch):
    """E-mail configurado, despacho por signal DESLIGADO: só o caminho síncrono."""
    from types import SimpleNamespace
    from unittest.mock import Mock

    from shopman.shop.services import critical_alerts

    settings.SHOPMAN_ALERT_EMAIL = "owner@example.com"
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    monkeypatch.setattr("shopman.shop.adapters.notification_email.is_available", lambda *args: True)
    send = Mock(return_value=SimpleNamespace(success=True, outcome_unknown=False))
    monkeypatch.setattr(critical_alerts, "notify", send)
    return send


def _page(alert_type):
    return Directive.objects.get(
        payload__event="operator_critical", payload__context__alert_type=alert_type
    )


def test_worker_parado_sai_por_email_sem_o_worker(paging):
    _stale_heartbeat(minutes=30)
    _run()
    task = _page("directive_worker_stale")
    assert task.status == "done"
    assert task.payload["critical_delivery"] == "accepted"
    assert paging.call_count == 1


def test_backlog_sai_por_email_sem_o_worker(paging):
    _overdue_queued(5)
    _run()
    task = _page("directive_backlog")
    assert task.status == "done"
    assert paging.call_count == 1


def test_email_da_fila_respeita_o_debounce(paging):
    _stale_heartbeat(minutes=30)
    _run()
    _run()
    assert Directive.objects.filter(payload__event="operator_critical").count() == 1
    assert paging.call_count == 1


def test_email_que_falhou_e_retentado_no_ciclo_seguinte(paging, monkeypatch):
    available = {"ok": False}
    monkeypatch.setattr(
        "shopman.shop.adapters.notification_email.is_available", lambda *args: available["ok"]
    )
    _stale_heartbeat(minutes=30)
    _run()
    task = _page("directive_worker_stale")
    assert task.status == "queued"
    assert paging.call_count == 0

    available["ok"] = True
    Directive.objects.filter(pk=task.pk).update(available_at=timezone.now())
    _run()
    task.refresh_from_db()
    assert task.status == "done"
    assert paging.call_count == 1


def test_failed_spike_segue_pela_fila(paging):
    """Só os alertas DA fila saem síncronos; o resto mantém o caminho de sempre."""
    _failed(5)
    _run()
    assert not Directive.objects.filter(payload__event="operator_critical").exists()
    assert paging.call_count == 0
