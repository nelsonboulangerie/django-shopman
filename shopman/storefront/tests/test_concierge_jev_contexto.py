"""1b da auditoria do Jev: a última fala da casa no estado do Jev, redigida (adendo à D-040).

Dono, 21/11/2026: "desde que seguro perante LGPD, sim". Só a ÚLTIMA fala da casa, pelo
mesmo redator da fala do cliente, sem código de pedido nem valores; nada além disso.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.storefront.concierge import triage
from shopman.storefront.concierge.intent_benchmark import Category, JevContender, Sample

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def customer_name():
    """O nome da conversa, como o turno vivo o prende antes da triagem (``service.run_turn``)."""
    from shopman.storefront.concierge import observation_privacy

    token = observation_privacy.bind_known_names("Ana")
    yield
    observation_privacy.release_known_names(token)

SUMMARY = (
    "Ana, aqui está o resumo do pedido W29: 2 Baguette de Tradition, total R$ 32,00. "
    "Retirada amanhã na loja. Se precisar, me liga no (43) 99876-5432. Responda ‘confirmo 4821’."
)


def test_the_house_line_goes_redacted_without_name_phone_order_or_value():
    line = triage.house_line([("Cliente", "quero 2 baguetes"), ("Casa", SUMMARY), ("Cliente", "na verdade não queria pagar")])

    assert "Baguette de Tradition" in line and "Retirada amanhã" in line, "o assunto fica"
    for personal in ("Ana", "99876", "W29", "32,00", "R$"):
        assert personal not in line, (personal, line)


def test_only_the_last_house_line_and_nothing_without_one():
    context = [("Casa", "Bom dia! Como posso ajudar?"), ("Cliente", "oi"), ("Casa", "Temos croissant hoje.")]

    assert triage.house_line(context) == "Temos croissant hoje."
    assert triage.house_line([("Cliente", "oi")]) == ""


def test_the_jev_receives_the_house_line_in_the_state_only_when_there_is_one():
    from shopman.shop.tests.ai_support import configure_jev

    configure_jev("k")
    sent = []

    class Session:
        def post(self, url, *, json, headers, timeout):
            sent.append(json)
            payload = {"answers": {"intent": {"type": "choice", "choice": "order", "probabilities": {"order": 1.0}}}}
            return SimpleNamespace(status_code=200, text="", json=lambda: payload)

    contender = JevContender(session=Session())
    categories = [Category("order", "Pedido", "quer comprar")]
    contender.scores(Sample(1, "não queria pagar", frozenset(), house_line=triage.house_line([("Casa", SUMMARY)])), categories)
    contender.scores(Sample(2, "oi", frozenset()), categories)

    assert set(sent[0]["state"]) == {"customer_message", "previous_store_message"}
    assert "Ana" not in sent[0]["state"]["previous_store_message"]
    assert set(sent[1]["state"]) == {"customer_message"}


def test_the_triage_hands_the_house_line_to_the_jev(monkeypatch):
    seen = {}

    def classify(text, *, contender=None, with_parts=False, house=""):
        seen["house"] = house
        return None

    monkeypatch.setattr(triage, "classify_with_jev", classify)
    monkeypatch.setattr(triage, "jev_enabled", lambda: True)

    triage.decide("na verdade eu não queria pagar não", context=[("Casa", SUMMARY)], channel_ref="whatsapp")

    assert "Baguette de Tradition" in seen["house"] and "Ana" not in seen["house"]
