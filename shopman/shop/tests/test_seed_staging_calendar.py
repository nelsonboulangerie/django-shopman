"""O seed data datas relativas ao calendário da loja, não a literais.

Duas garantias:
  1. Sob o piloto automático de staging a loja abre 24/7 — quem testa às 22h ou
     no domingo consegue pedir.
  2. "A loja abre neste dia?" é respondida pelo calendário em TODOS os seeders
     (produção futura, encomenda, histórico). Antes, três literais
     ``weekday() == 6`` copiavam o horário da Nelson à mão e deixavam buracos de
     domingo numa loja que abre todo dia.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.utils import timezone

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


def _command():
    from config.management.commands.seed import Command

    command = Command()
    command.stdout = StringIO()
    return command


def _next_sunday() -> date:
    today = timezone.localdate()
    return today + timedelta(days=(6 - today.weekday()) % 7 or 7)


def test_seed_keeps_nelson_hours_without_the_flag(settings):
    settings.SHOPMAN_STAGING_AUTOPILOT = False

    _command()._seed_shop()

    shop = Shop.load()
    assert shop.opening_hours["monday"] == {"open": "09:00", "close": "18:00"}
    assert "sunday" not in shop.opening_hours
    assert shop.defaults["closed_dates"], "feriados da Nelson seguem valendo"


def test_seed_opens_around_the_clock_under_staging_autopilot(settings):
    settings.SHOPMAN_STAGING_AUTOPILOT = True
    settings.SHOPMAN_ENVIRONMENT = "staging"

    _command()._seed_shop()

    shop = Shop.load()
    assert set(shop.opening_hours) == {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    }
    assert all(
        window == {"open": "00:00", "close": "23:59"}
        for window in shop.opening_hours.values()
    )
    assert shop.defaults["closed_dates"] == []


def test_store_is_open_right_now_under_staging_autopilot(settings):
    """A pergunta que importa para o testador: dá para pedir AGORA?"""
    from shopman.shop.services.business_calendar import current_business_state

    settings.SHOPMAN_STAGING_AUTOPILOT = True
    settings.SHOPMAN_ENVIRONMENT = "staging"
    _command()._seed_shop()

    assert current_business_state().is_closed is False


def test_seed_asks_the_calendar_which_days_the_shop_operates(settings):
    """O filtro de dia segue o horário da loja — não um domingo literal."""
    settings.SHOPMAN_STAGING_AUTOPILOT = False
    command = _command()
    command._seed_shop()

    sunday = _next_sunday()
    assert command._shop_operates_on(sunday) is False
    assert command._shop_operates_on(sunday + timedelta(days=1)) is True

    # Mesma pergunta, loja 24/7: a resposta MUDA. Um literal não mudaria.
    settings.SHOPMAN_STAGING_AUTOPILOT = True
    settings.SHOPMAN_ENVIRONMENT = "staging"
    command = _command()
    command._seed_shop()

    assert command._shop_operates_on(sunday) is True


def test_seed_calendar_respects_closed_dates(settings):
    """Feriado no calendário tira o dia do seed — produção e histórico incluídos."""
    settings.SHOPMAN_STAGING_AUTOPILOT = False
    command = _command()
    command._seed_shop()

    shop = Shop.load()
    holiday = next(
        d for d in (timezone.localdate() + timedelta(days=n) for n in range(1, 15))
        if d.weekday() != 6
    )
    shop.defaults = {**shop.defaults, "closed_dates": [{"date": holiday.isoformat()}]}
    shop.save(update_fields=["defaults"])

    command = _command()  # cache do shop começa limpo
    assert command._shop_operates_on(holiday) is False
