"""Uma retirada de HOJE que a grade oferece, a qualquer hora em que a suíte rode.

A grade de hoje é a meia hora do expediente que ainda dá (``fulfillment_window``),
e por isso depende do relógio e do expediente da loja. Os testes de checkout que
só precisam de "uma retirada válida hoje" (CPF na nota, contrato de preço,
recuperação do commit…) não estão provando o horário: estão provando outra coisa
e precisam de um horário que a loja aceite.

O relógio da grade fica parado às 08:00 de hoje pelo ``conftest`` desta suíte
(``pickup_grid_clock``), quando quem chama não passa o próprio. Aqui só se garante
o expediente (a loja de teste nasce sem horário, e loja sem horário não tem grade
de hoje) e se devolve a primeira meia hora oferecida. O horário em si está
provado com o relógio parado em ``test_pickup_slots.py``.
"""

from __future__ import annotations

EVERY_DAY = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def today_pickup_slot() -> str:
    from django.utils import timezone

    from shopman.shop.models import Shop
    from shopman.shop.services.fulfillment_window import delivery_windows_for

    shop = Shop.load()
    if shop is not None and not shop.opening_hours:
        shop.opening_hours = {day: {"open": "00:00", "close": "23:59"} for day in EVERY_DAY}
        shop.save(update_fields=["opening_hours"])
    windows = delivery_windows_for(timezone.localdate())
    assert windows, "a loja de teste precisa de expediente hoje para haver retirada"
    return windows[0]["ref"]
