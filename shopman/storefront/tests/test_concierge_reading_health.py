"""A Concierge sem modelo vira aviso no Gestor e sonda no Watchman (dono, 19/11/2026, camada 3).

Hoje isso só se descobria quando o cliente reclamava. Aqui:

- **A causa é dita**: sem chave, sem conexão, freio de gasto, provedor falhando.
- **Um aviso por causa**, cor de erro, no topo do Gestor (``on_screen``); não duplica a
  cada ciclo; resolve quando o modelo volta; outra causa troca o aviso.
- **A sonda do Watchman** falha com a Concierge atendendo sem modelo e pula com ela
  desligada.
"""

from __future__ import annotations

import pytest
from shopman.watchman.contracts import Status

from shopman.backstage.models import OperatorAlert
from shopman.shop.tests.ai_support import configure_ai
from shopman.storefront.concierge import reading_health
from shopman.storefront.tests.test_concierge_engine import CONCIERGE_SETTINGS
from shopman.storefront.watchman_checks import ConciergeReadingCheck

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def concierge_on(settings):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    reading_health.record_read(ok=True)


def _open():
    return list(OperatorAlert.objects.filter(type=reading_health.ALERT_TYPE, resolved_at__isnull=True))


def test_with_a_reader_the_concierge_reads_with_a_model_and_nothing_is_on_screen():
    configure_ai("sk-teste")
    assert reading_health.current() == reading_health.ReadingState(True)
    assert reading_health.sync_alert() == {"opened": 0, "resolved": 0}
    assert _open() == []


def test_without_a_key_one_error_alert_names_the_cause_and_does_not_repeat():
    configure_ai("")
    state = reading_health.current()
    assert state.without_model and state.cause == "no_connection"

    assert reading_health.sync_alert()["opened"] == 1
    assert reading_health.sync_alert()["opened"] == 0  # o próximo ciclo não duplica
    [alert] = _open()
    assert alert.severity == "error" and alert.audience == "orders"
    assert "sem modelo" in alert.message and "conexão de IA" in alert.message
    assert "—" not in alert.message


def test_a_connection_without_a_key_is_its_own_cause():
    connection = configure_ai("sk-teste")
    connection.set_api_key("")
    connection.save()
    assert reading_health.current().cause == "no_key"


def test_the_alert_goes_away_when_the_model_comes_back_and_changes_with_the_cause():
    configure_ai("")
    reading_health.sync_alert()
    assert len(_open()) == 1

    configure_ai("sk-teste")
    for _ in range(reading_health.PROVIDER_FAILURES):
        reading_health.record_read(ok=False)
    assert reading_health.current().cause == "provider_failing"
    reading_health.sync_alert()
    [alert] = _open()
    assert "provedor" in alert.message  # a causa velha saiu, a nova entrou

    reading_health.record_read(ok=True)
    assert reading_health.sync_alert()["resolved"] == 1
    assert _open() == []


def test_the_spend_brake_is_a_cause(monkeypatch):
    from shopman.shop import ai_governor

    configure_ai("sk-teste")

    def braked(purpose):
        raise ai_governor.AIDisabled("a IA está desligada na loja")

    monkeypatch.setattr(ai_governor, "check", braked)
    assert reading_health.current().cause == "brake"


def test_with_the_concierge_off_there_is_no_alert_and_the_probe_skips(settings):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "enabled": False}
    configure_ai("")
    assert not reading_health.current().active
    reading_health.sync_alert()
    assert _open() == []
    assert ConciergeReadingCheck().run(None).status is Status.SKIPPED


def test_the_probe_fails_without_a_model_and_passes_with_one():
    configure_ai("")
    failed = ConciergeReadingCheck().run(None)
    assert failed.status is Status.FAIL and failed.evidence == {"cause": "no_connection"}
    configure_ai("sk-teste")
    assert ConciergeReadingCheck().run(None).status is Status.PASS


def test_the_alert_asks_for_the_top_of_the_screen():
    from shopman.backstage.projections.alerts import build_operator_alerts_projection
    from shopman.backstage.services import alerts as alert_service

    configure_ai("")
    reading_health.sync_alert()
    projection = build_operator_alerts_projection(alerts=_open(), counts=alert_service.active_counts(scope="orders"))
    [row] = projection.alerts
    assert row.on_screen is True and row.subject == "Concierge sem modelo" and row.origin_label == "WhatsApp"


def test_the_alert_carries_the_button_that_solves_the_cause(settings, monkeypatch):
    """Dono, 20/11/2026: o aviso leva até a tela que resolve, não ensina o caminho."""
    from shopman.backstage.projections.alerts import build_operator_alerts_projection
    from shopman.backstage.services import alerts as alert_service

    settings.SHOPMAN_ADMIN_HOST = "admin.exemplo.com.br"
    configure_ai("")
    reading_health.sync_alert()
    counts = alert_service.active_counts(scope="orders")
    [row] = build_operator_alerts_projection(alerts=_open(), counts=counts, surface="orders").alerts
    [action] = [a for a in row.actions if a.kind == "open_alert_context"]
    assert (action.label, action.href) == ("Abrir conexões de IA", "https://admin.exemplo.com.br/admin/shop/aiconnection/")
    assert "(Admin" not in row.message and "Conexões de IA)" not in row.message

    configure_ai("sk-teste")

    def braked(purpose):
        from shopman.shop import ai_governor

        raise ai_governor.AIDisabled("a IA está desligada na loja")

    from shopman.shop import ai_governor

    monkeypatch.setattr(ai_governor, "check", braked)
    reading_health.sync_alert()
    [row] = build_operator_alerts_projection(alerts=_open(), counts=counts, surface="orders").alerts
    [action] = [a for a in row.actions if a.kind == "open_alert_context"]
    assert (action.label, action.href) == ("Abrir freio de IA", "https://admin.exemplo.com.br/admin/shop/shop/")
