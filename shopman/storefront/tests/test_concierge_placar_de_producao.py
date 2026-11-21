"""Casos do placar de conversa em produção (21/11/2026), um por linha, no código de hoje.

- "Estarão abertos amanhã?" e "Amanhã vai ter?" deram "não entendi" duas vezes (m1983): a regra
  conhecia "aberto", não "abertos"; e a pergunta elíptica não olhava o produto de que se falava.
- "Aceitam pets?" (m1976): a regra conhecia "pet", não "pets".
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as django_settings

from shopman.storefront.concierge import dialogue, intents
from shopman.storefront.concierge.dialogue import Facts
from shopman.storefront.concierge.dialogue_eval import registry_copy

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=ZoneInfo(django_settings.TIME_ZONE))


@pytest.mark.parametrize(("text", "act"), [
    ("Estarão abertos amanhã?", "hours_delivery"),
    ("vocês estão abertos?", "hours_delivery"),
    ("Aceitam pets?", "house_info"),
    ("posso levar meu cachorro?", "house_info"),
])
def test_local_reader_knows_the_plural_forms(text, act):
    assert [a.act for a in intents.local_acts(text)] == [act]


def test_tomorrow_will_there_be_is_about_the_product_in_focus():
    state = {"v": dialogue.VERSION, "valid_until": "2026-11-21T23:00:00-03:00",
             "focus": {"ref": "PAIN-PERDU", "name": "Pain Perdu"}}
    facts = Facts(now=NOW)
    resolution = dialogue.resolve("Amanhã vai ter?", dialogue.effective(state, facts), facts, copy=registry_copy)
    assert resolution.reason == "elliptic_availability" and resolution.refs == ("PAIN-PERDU",)
    assert resolution.text == "tem Pain Perdu amanha"


def test_without_a_product_in_focus_it_is_not_guessed():
    facts = Facts(now=NOW)
    resolution = dialogue.resolve("Amanhã vai ter?", dialogue.effective({"v": dialogue.VERSION}, facts), facts,
                                  copy=registry_copy)
    assert resolution.reason != "elliptic_availability"
