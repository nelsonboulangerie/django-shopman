"""O aviso de integração e o de reserva órfã fecham pelo fato (#3097, #3085).

- ``integration_failed`` fecha quando a MESMA integração volta a responder; o da
  emissão de NFC-e de um pedido fecha quando a nota daquele pedido sai.
- ``orphan_holds_released`` é informativo (as reservas já voltaram quando ele
  nasceu): fecha na varredura seguinte que não acha órfã.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from shopman.backstage.models import OperatorAlert
from shopman.shop.handlers.alert_resolution import _resolve_emit_integration_failure
from shopman.shop.services import observability
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db


def _failure(provider, operation, detail):
    observability.record_integration_failure(provider=provider, operation=operation, detail=detail)
    return OperatorAlert.objects.filter(type="integration_failed").order_by("-pk").first()


def _closed_by(alert):
    alert.refresh_from_db()
    return alert.resolved_by if alert.resolved_at else None


def test_success_closes_only_the_same_provider():
    sms = _failure("comtele_sms", "envio do código de login por SMS", "HTTP 503")
    maps = _failure("google_geocoding", "reverse_geocode", "status=OVER_QUERY_LIMIT")

    assert observability.record_integration_success("comtele_sms") == 1
    assert _closed_by(sms).endswith("voltou a responder")
    assert _closed_by(maps) is None


def test_geocoding_success_also_closes_the_blind_antifraud_alert():
    blind = _failure("google_geocoding", "antifraud_delivery_check", "antifraude de entrega rodou sem verificação")
    observability.record_integration_success("google_geocoding")
    assert _closed_by(blind) is not None


def test_success_without_open_alert_writes_nothing():
    assert observability.record_integration_success("comtele_sms") == 0


def test_nfce_authorized_closes_the_emit_failure_of_that_order_only():
    mine = _failure("fiscal", "emit_nfce", "pedido PDV-1: timeout")
    other = _failure("fiscal", "emit_nfce", "pedido PDV-2: timeout")
    _resolve_emit_integration_failure("PDV-1")
    assert _closed_by(mine) == "nfce-authorized"
    assert _closed_by(other) is None


def test_orphan_holds_alert_closes_on_the_next_clean_sweep():
    create_operator_alert(
        type="orphan_holds_released", severity="warning",
        message="2 reserva(s) órfã(s) devolvida(s) ao estoque/plano: 1x PAO.", dedupe_key="orphan_holds:1,2",
    )
    alert = OperatorAlert.objects.get(type="orphan_holds_released")
    call_command("sweep_orphan_holds", "--dry-run", stdout=StringIO())
    assert _closed_by(alert) is None, "ensaio não fecha nada"
    call_command("sweep_orphan_holds", stdout=StringIO())
    assert _closed_by(alert) == "sistema: reservas já devolvidas; nenhuma órfã na varredura seguinte"
