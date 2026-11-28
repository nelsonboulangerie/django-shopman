# ruff: noqa: F401, F811
"""O Jev escolhe o SKU entre os candidatos da busca (item 4 da auditoria do Jev, 21/11/2026).

"pode ser 2 baguettes então" achou Baguette de Tradition e Jambon-Beurre (a descrição do
sanduíche cita "baguette"), e a casa perguntou "Qual deles?". O Jev, como decisor tipado, escolhe
quando tem certeza; com dúvida, a pergunta ao cliente continua sendo a resposta.
"""

from __future__ import annotations

import pytest

from shopman.storefront.concierge import intents
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _listed,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _cart, _turn

pytestmark = pytest.mark.django_db

ORDER = "pode ser 2 baguettes entao, meu cpf é 123.456.789-09"


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def baguettes(surface, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _listed("TRADI", "Baguette de Tradition", description="Baguette de fermentação natural", stock="20")
    # Duas baguetes no nome: o Jambon-Beurre do ar, que só cita "baguette" na descrição, deixou de
    # ser candidato (``test_a_description_only_match_is_not_a_candidate``), e a dúvida que o Jev
    # resolve é entre duas baguetes de verdade.
    _listed("BVIEN", "Baguette Viennoise", description="Baguete de massa amanteigada", stock="20")


def _jev(monkeypatch, choice, confidence=0.92, *, boom=False):
    from shopman.shop import ai

    sent = []
    monkeypatch.setattr(ai, "jev_endpoint", lambda **kw: ("https://jev.invalid", "k", "jev-test"))

    def post(session, url, key, body, **kw):
        if boom:
            raise TimeoutError("fora")
        sent.append(body)
        criteria = body["questions"]["sku"]["criteria"]
        keys = list(criteria)
        # "nome:X": o Jev escolhe o candidato que tem esse nome, seja qual for a posição dele.
        picked = next(k for k, text in criteria.items() if choice[5:] in text) if choice.startswith("nome:") else choice
        probs = {k: (0.9 if k == picked else 0.1 / max(1, len(keys) - 1)) for k in keys}
        return FakeResponse({"answers": {"sku": {"type": "choice", "choice": picked, "probabilities": probs,
                                                 "confidence": confidence}}, "usage": {"input_tokens": 80}})

    monkeypatch.setattr(ai, "jev_post", post)
    return sent


def _order(conversation):
    return _turn(conversation, ORDER, [_act("order", ORDER, "baguettes", 2)])


def test_a_sure_jev_picks_the_sku_and_the_cart_gets_it(conversation, outbox, baguettes, monkeypatch):
    sent = _jev(monkeypatch, "nome:Baguette de Tradition")

    reply = _order(conversation)

    assert _cart(conversation) == {"TRADI": 2}, reply
    assert "Qual deles?" not in reply
    body = sent[0]
    assert "123.456.789-09" not in body["state"]["customer_message"]  # redigido
    assert set(body["questions"]["sku"]["criteria"]) == {"p1", "p2", "other"}


@pytest.mark.parametrize(("choice", "confidence"), [("p1", 0.6), ("other", 0.95)])
def test_doubt_or_none_of_these_asks_which(conversation, outbox, baguettes, monkeypatch, choice, confidence):
    _jev(monkeypatch, choice, confidence)

    reply = _order(conversation)

    assert reply.startswith("Qual deles?") and _cart(conversation) == {}, reply


def test_a_fallen_jev_never_picks(conversation, outbox, baguettes, monkeypatch):
    _jev(monkeypatch, "p1", boom=True)

    reply = _order(conversation)

    assert reply.startswith("Qual deles?") and _cart(conversation) == {}, reply


def test_a_description_only_match_is_not_a_candidate(conversation, outbox, surface, settings, monkeypatch):
    """O caso do ar (21/11/2026): "baguettes" achava o Jambon-Beurre pela descrição. A palavra
    que distingue o pedido está no NOME da Baguette de Tradition, e ela vai à sacola sem
    pergunta e sem chamar o Jev."""
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _listed("TRADI", "Baguette de Tradition", description="Baguette de fermentação natural", stock="20")
    _listed("JB", "Jambon-Beurre", description="Baguette com presunto e manteiga", stock="20")
    sent = _jev(monkeypatch, "p2")

    reply = _order(conversation)

    assert _cart(conversation) == {"TRADI": 2}, reply
    assert "Qual deles?" not in reply
    assert not [body for body in sent if "sku" in body["questions"]]  # o Jev não escolheu SKU
