"""Horário da loja ilegível GRITA: alerta ao gestor + Sentry, e a venda segue.

Decisão do dono (24/09/2026): log sozinho não serve. Se a regra de horário não
consegue ler a grade ou as datas de fechamento, TODO pedido passa sem a
conferência de horário até alguém corrigir — quem pode corrigir precisa saber.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from shopman.backstage.models import OperatorAlert
from shopman.shop.rules.validation import BusinessHoursRule

pytestmark = pytest.mark.django_db


def _quebra_a_loja():
    return patch("shopman.shop.models.Shop.load", side_effect=RuntimeError("banco fora"))


def test_grade_ilegivel_abre_alerta_e_erro_para_o_sentry(caplog):
    with _quebra_a_loja(), caplog.at_level(logging.ERROR, logger="shopman.shop.rules.validation"):
        assert BusinessHoursRule._get_opening_hours() is None  # a venda segue

    (alerta,) = OperatorAlert.objects.filter(type="shop_calendar_unreadable")
    assert alerta.severity == "error"
    assert "horário de funcionamento" in alerta.message
    assert alerta.get_type_display() == "Horário da loja ilegível"
    # logger.error com traceback é o que o LoggingIntegration do Sentry envia.
    record = next(r for r in caplog.records if "opening_hours" in r.getMessage())
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None


def test_datas_de_fechamento_ilegiveis_tambem_alertam():
    with _quebra_a_loja():
        assert BusinessHoursRule._get_closed_dates() == []

    (alerta,) = OperatorAlert.objects.filter(type="shop_calendar_unreadable")
    assert "datas de fechamento" in alerta.message


def test_o_alerta_e_deduplicado_por_causa():
    with _quebra_a_loja():
        for _ in range(5):
            BusinessHoursRule._get_opening_hours()
            BusinessHoursRule._get_closed_dates()

    # Um por causa (grade, datas), não um por pedido.
    assert OperatorAlert.objects.filter(type="shop_calendar_unreadable").count() == 2
