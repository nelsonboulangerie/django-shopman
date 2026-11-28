"""WP-16: a resposta da equipe que chega depois da janela de 24 horas do WhatsApp.

Com o modelo aprovado pela Meta ligado (``concierge_answer_ready`` com flow), a resposta fora
da janela dispara o modelo e fica guardada; a próxima mensagem do cliente reabre a janela e
recebe "A equipe confirmou: ...", uma vez só. Sem o modelo ligado, vale o WP-05: nada é
prometido nem enviado fora da janela. O "Pronto quando" do plano, item por item.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.storefront.concierge import verification
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    _binding,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_verification import (  # noqa: F401 (fixtures)
    _ask_parking,
    _cards,
    _closed_until,
    _record,
    _turn,
    plural,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def template(monkeypatch):
    """O modelo aprovado ligado: o flow existe, e o envio é gravado."""
    sent = []
    from shopman.shop.adapters import notification_manychat

    monkeypatch.setattr(
        notification_manychat, "sends_as_flow", lambda event: event == verification.ANSWER_READY_EVENT
    )

    def send(recipient, template, context=None, **config):
        sent.append((recipient, template))
        return True

    monkeypatch.setattr(notification_manychat, "send", send)
    return sent


def _close_the_window(conversation):  # noqa: F811
    past = timezone.now() - timedelta(minutes=1)
    for message in conversation.messages.filter(kind="inbound"):
        envelope = dict(message.envelope)
        envelope["window_evidence"] = {**envelope["window_evidence"], "valid_until": past.isoformat()}
        message.envelope = envelope
        message.save(update_fields=["envelope"])


def test_1_an_answer_outside_the_window_sends_the_approved_message_and_keeps_the_answer(conversation, outbox, template):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    _close_the_window(conversation)
    sent = len(outbox.sent)

    result = verification.answer(card.pk, "Temos sim, duas vagas na frente.", actor="ana")

    assert result.ok, result
    assert template == [(_binding(conversation).subject, verification.ANSWER_READY_EVENT)]
    assert len(outbox.sent) == sent, "texto livre não sai fora da janela"
    record = _record(conversation)
    assert record["status"] == verification.STORED
    assert record["reply"] == "A equipe confirmou: Temos sim, duas vagas na frente."
    card.refresh_from_db()
    assert card.resolved_at is not None, "a equipe já respondeu: o cartão fecha"


def test_2_the_next_message_receives_the_kept_answer_once(conversation, outbox, template):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    _close_the_window(conversation)
    verification.answer(card.pk, "Temos sim, duas vagas na frente.", actor="ana")

    _turn(conversation, "oi, pode mandar", [_act("greet", "oi")], "depois-1")
    first = outbox.sent[-1]
    _turn(conversation, "obrigada", [_act("thanks", "obrigada")], "depois-2")

    assert first == "A equipe confirmou: Temos sim, duas vagas na frente."
    assert outbox.sent.count(first) == 1, "a resposta guardada sai uma vez só"
    assert _record(conversation)["status"] == verification.ANSWERED


def test_3_without_the_template_nothing_is_promised_nor_sent_outside_the_window(conversation, outbox):  # noqa: F811
    _closed_until(3)

    _ask_parking(conversation)

    assert "Quem confirma isso é a equipe, que volta " in outbox.sent[-1]
    assert _record(conversation) is None and not _cards().exists()


def test_3_without_the_template_an_answer_outside_the_window_does_not_go(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    _close_the_window(conversation)

    result = verification.answer(card.pk, "Temos sim.", actor="ana")

    assert not result.ok and result.detail == "window_closed"
    assert _record(conversation)["status"] == verification.OPEN


def test_with_the_template_the_promise_holds_beyond_the_window(conversation, outbox, template):  # noqa: F811
    _closed_until(3)

    _ask_parking(conversation)

    record = _record(conversation)
    assert record is not None and record["promise"]["kind"] == verification.LATER, record
    assert "te aviso" in outbox.sent[-1] or "respondo" in outbox.sent[-1], outbox.sent[-1]


def test_4_an_answer_inside_the_window_follows_wp05(conversation, outbox, template):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()

    result = verification.answer(card.pk, "Temos sim, duas vagas.", actor="ana")

    assert result.ok and template == [], "dentro da janela, o modelo não é usado"
    assert outbox.sent[-1] == "A equipe confirmou: Temos sim, duas vagas."
    assert _record(conversation)["status"] == verification.ANSWERED


# ── #3005: o segundo prazo fora da janela não passa à equipe ────────────


def test_the_second_deadline_outside_the_window_keeps_the_card_and_does_not_hand_off(conversation, outbox, template):  # noqa: F811
    """Regra escrita (#3005): o "a equipe assume" não chegaria ao cliente, e a equipe não
    escreveria no Live Chat. A conversa fica com a Concierge, o cartão segue aberto e a resposta
    da equipe pelo cartão sai pelo modelo aprovado (WP-16)."""
    from shopman.shop.models import Conversation

    _ask_parking(conversation)
    card = _cards().get()
    _close_the_window(conversation)
    record = _record(conversation)
    late = timezone.now() + timedelta(hours=2)
    sent = len(outbox.sent)

    counts = verification.sweep(now=max(late, verification._parse(record["handoff_due_at"]) + timedelta(minutes=1)))

    conversation.refresh_from_db()
    assert counts["handed_off"] == 0 and counts[verification.KEPT_OUT_OF_WINDOW] == 1, counts
    assert conversation.state == Conversation.State.ACTIVE
    assert len(outbox.sent) == sent, "nada de texto livre fora da janela"
    card.refresh_from_db()
    assert card.resolved_at is None, "o cartão segue esperando a equipe"

    result = verification.answer(card.pk, "Temos sim, duas vagas na frente.", actor="ana")
    assert result.ok and template, result  # a resposta sai pelo modelo aprovado
