import pytest


@pytest.fixture(autouse=True)
def clear_omotenashi_cache():
    from shopman.shop.omotenashi.copy import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


@pytest.fixture(autouse=True)
def pickup_grid_clock(monkeypatch):
    """A grade de HOJE lida às 08:00, quando quem chama não passa o relógio.

    A meia hora de hoje corta pelo agora; sem isto, um teste de checkout que
    escolhe "uma retirada de hoje" passaria de dia e quebraria à noite. Quem
    prova o corte pelo relógio passa o ``now`` explícito e não é tocado.
    """
    from datetime import datetime, time

    from django.utils import timezone

    from shopman.shop.services import business_calendar

    original = business_calendar.delivery_slots_for

    def pinned(day, *, now=None, shop=None):
        if now is None:
            now = timezone.make_aware(datetime.combine(timezone.localdate(), time(8, 0)))
        return original(day, now=now, shop=shop)

    monkeypatch.setattr(business_calendar, "delivery_slots_for", pinned)
