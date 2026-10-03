"""Cortesia não é pergunta: "bom dia" recebe bom dia (observação do dono, 03/10/2026).

Os casos de turno inteiro (modelo, busca e resposta) moram em
``test_concierge_engine.py``, junto do cenário com catálogo e FAQ.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from shopman.storefront.concierge import small_talk


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("bom dia", "greeting"),
        ("Bom dia, tudo bem?", "greeting"),
        ("oi", "greeting"),
        ("Oiii!!", "greeting"),
        ("Olá bom dia", "greeting"),
        ("oi boa tarde", "greeting"),
        ("boa noite pessoal 💛", "greeting"),
        ("tudo bem? e com você?", "greeting"),
        ("obrigado", "thanks"),
        ("Muito obrigada pela ajuda!", "thanks"),
        ("valeu", "thanks"),
        ("tchau", "farewell"),
        ("obrigado, até logo", "farewell"),
    ],
)
def test_courtesy_alone_is_small_talk(text, kind):
    assert small_talk.small_talk_kind(text) == kind


@pytest.mark.parametrize(
    "text",
    [
        "tem croissant hoje?",
        "Bom dia, tem croissant hoje?",
        "o levain tem glúten?",
        "oi, quero falar com uma pessoa",
        "como está o meu pedido?",
        "ok",
        "sim",
        "Ah ótimo",
        "confirmo",
        "",
    ],
)
def test_anything_beyond_courtesy_is_not_small_talk(text):
    assert small_talk.small_talk_kind(text) == ""


def test_strip_keeps_only_the_question():
    assert small_talk.strip_small_talk("Bom dia, tudo bem? Tem croissant hoje?") == "tem croissant hoje"
    assert small_talk.strip_small_talk("Bom dia, tudo bem?") == ""
    assert small_talk.strip_small_talk("qual o pão do dia?") == "qual o pao do dia"


def test_the_salutation_comes_back_as_the_customer_said_it():
    assert small_talk.opening_salutation("oi boa tarde") == "Boa tarde"
    assert small_talk.opening_salutation("Bom dia, tem croissant?") == "Bom dia"
    assert small_talk.opening_salutation("oi") == ""


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(7, "Bom dia"), (11, "Bom dia"), (12, "Boa tarde"), (17, "Boa tarde"), (18, "Boa noite"), (2, "Boa noite")],
)
def test_salutation_for_now_follows_the_shop_clock(hour, expected, settings):
    tz = ZoneInfo(settings.TIME_ZONE)
    assert small_talk.salutation_for_now(datetime(2026, 10, 3, hour, 0, tzinfo=tz)) == expected


def _copy(key):
    from shopman.shop.omotenashi.copy import resolve_copy

    return resolve_copy(key, moment="*").message


@pytest.mark.django_db
def test_replies_are_one_line_in_the_concierge_voice():
    greeting = small_talk.reply_for("Bom dia, tudo bem?", kind="greeting", copy=_copy)
    first = small_talk.reply_for("bom dia", kind="greeting", shop_name="Nelson Boulangerie", is_first_turn=True, copy=_copy)
    thanks = small_talk.reply_for("obrigado", kind="thanks", copy=_copy)
    farewell = small_talk.reply_for("tchau", kind="farewell", copy=_copy)

    assert greeting == "Bom dia! Tudo ótimo por aqui, obrigada. Em que posso ajudar? 💛"
    assert first == "Bom dia! Aqui é a concierge da Nelson Boulangerie. Em que posso ajudar? 💛"
    assert thanks == "Nós que agradecemos! Qualquer coisa, é só chamar. 💛"
    assert farewell == "Até logo! Quando precisar, é só chamar. 💛"
    for reply in (greeting, first, thanks, farewell):
        assert "\n" not in reply and len(reply) <= 120
        assert "—" not in reply
