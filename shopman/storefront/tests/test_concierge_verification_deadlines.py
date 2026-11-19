"""WP-06 do plano da Concierge: os prazos do "vou verificar".

O relógio é dado à varredura (``verification.sweep(now=...)``), um minuto antes e no
minuto de cada prazo:

- primeiro prazo: o cartão sobe a urgente e o cliente recebe UM aviso (uma vez só);
- segundo prazo: a conversa vai para a equipe, com a pergunta no cartão;
- com a casa fechada, o relógio não corre;
- a varredura não cria cliente de modelo.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Conversation
from shopman.storefront.concierge import verification
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_verification import (  # noqa: F401 (fixtures)
    _ask_parking,
    _cards,
    _closed_until,
    _record,
    plural,
)

pytestmark = pytest.mark.django_db

NUDGE = "Ainda estou confirmando com a equipe. Assim que eu tiver a resposta, te aviso por aqui."
HANDOFF = "Alguém da equipe continua com você por aqui."


def _due(record: dict, key: str) -> datetime:
    return datetime.fromisoformat(record[key])


@pytest.fixture
def opened(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    return _record(conversation)


def test_one_minute_before_the_first_deadline_nothing_happens(conversation, outbox, opened):  # noqa: F811
    sent = len(outbox.sent)

    counts = verification.sweep(now=_due(opened, "nudge_due_at") - timedelta(minutes=1))

    assert counts["nudged"] == 0 and len(outbox.sent) == sent
    assert not _record(conversation)["nudged_at"]
    assert _cards().get().severity == "warning"


def test_at_the_first_deadline_the_card_goes_urgent_and_the_customer_gets_one_notice(
    conversation, outbox, opened  # noqa: F811
):
    due = _due(opened, "nudge_due_at")
    sent = len(outbox.sent)

    assert verification.sweep(now=due)["nudged"] == 1
    assert verification.sweep(now=due + timedelta(minutes=1))["nudged"] == 0

    assert outbox.sent[sent:] == [NUDGE], "o aviso sai uma vez só"
    card = _cards().get()
    assert card.severity == verification.URGENT_SEVERITY
    assert card.respond_by == _due(opened, "handoff_due_at"), "o sino conta até o segundo prazo"
    record = _record(conversation)
    assert record["status"] == verification.OPEN and record["nudged_at"]
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE


def test_one_minute_before_the_second_deadline_the_conversation_stays(conversation, outbox, opened):  # noqa: F811
    verification.sweep(now=_due(opened, "nudge_due_at"))

    verification.sweep(now=_due(opened, "handoff_due_at") - timedelta(minutes=1))

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE
    assert _record(conversation)["status"] == verification.OPEN


def test_at_the_second_deadline_the_conversation_goes_to_the_team_with_the_question(
    conversation, outbox, opened  # noqa: F811
):
    verification.sweep(now=_due(opened, "nudge_due_at"))

    counts = verification.sweep(now=_due(opened, "handoff_due_at"))

    assert counts["handed_off"] == 1
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert outbox.sent[-1] == HANDOFF
    assert outbox.flags[-1] is True
    assert _record(conversation)["status"] == verification.HANDED_OFF
    assert _cards().get().resolved_at is not None, "o cartão da verificação fecha"
    handoff = OperatorAlert.objects.get(type="concierge_handoff")
    assert "estacionamento" in handoff.message, "o cartão de handoff leva a pergunta"
    assert "ninguém respondeu no prazo" in handoff.message
    assert verification.sweep(now=_due(opened, "handoff_due_at") + timedelta(minutes=5))["handed_off"] == 0


def test_the_second_deadline_without_the_first_notice_hands_off_without_a_late_notice(
    conversation, outbox, opened  # noqa: F811
):
    """O worker parado no primeiro prazo: no segundo, vale o handoff, sem aviso atrasado."""
    sent = len(outbox.sent)

    verification.sweep(now=_due(opened, "handoff_due_at"))

    assert outbox.sent[sent:] == [HANDOFF]


def test_with_the_house_closed_the_clock_does_not_run(conversation, outbox):  # noqa: F811
    _closed_until(1)
    _ask_parking(conversation, window_hours=48)
    record = _record(conversation)
    sent = len(outbox.sent)

    # Hoje, a qualquer hora, nada corre: os prazos contam a partir da abertura de amanhã.
    tonight = timezone.localtime().replace(hour=23, minute=59, second=0, microsecond=0)
    counts = verification.sweep(now=tonight)
    assert counts["nudged"] == 0 and counts["handed_off"] == 0

    # E um prazo que, por qualquer razão (o calendário mudou), já tenha passado espera a casa abrir.
    conversation.refresh_from_db()
    flags = dict(conversation.flags)
    flags[verification.FLAG_KEY] = {
        **record,
        "nudge_due_at": (timezone.now() - timedelta(hours=1)).isoformat(),
        "handoff_due_at": (timezone.now() - timedelta(minutes=30)).isoformat(),
    }
    Conversation.objects.filter(pk=conversation.pk).update(flags=flags)
    counts = verification.sweep()
    assert counts["nudged"] == 0 and counts["handed_off"] == 0
    assert len(outbox.sent) == sent
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE

    # Com a casa aberta de novo (na abertura de amanhã), o relógio volta a correr.
    Conversation.objects.filter(pk=conversation.pk).update(
        flags={**flags, verification.FLAG_KEY: record}
    )
    assert verification.sweep(now=_due(record, "nudge_due_at"))["nudged"] == 1


def test_an_answered_verification_is_not_touched_by_the_clock(conversation, outbox, opened):  # noqa: F811
    verification.answer(_cards().get().pk, "Temos sim, duas vagas.", actor="ana")
    sent = len(outbox.sent)

    counts = verification.sweep(now=_due(opened, "handoff_due_at"))

    assert counts["open"] == 0 and len(outbox.sent) == sent


def test_a_conversation_already_with_the_team_closes_the_verification_quietly(conversation, outbox, opened):  # noqa: F811
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.HANDOFF)
    sent = len(outbox.sent)

    counts = verification.sweep(now=_due(opened, "nudge_due_at"))

    assert counts["closed_with_team"] == 1 and len(outbox.sent) == sent
    assert _record(conversation)["status"] == verification.HANDED_OFF
    assert _cards().get().resolved_at is not None


def test_the_sweep_never_creates_a_model_client(conversation, outbox, opened, monkeypatch):  # noqa: F811
    def no_client(*args, **kwargs):
        raise AssertionError("a varredura dos prazos criou cliente de modelo")

    monkeypatch.setattr("shopman.shop.ai.anthropic_client", no_client)
    monkeypatch.setattr("shopman.storefront.concierge.intent_benchmark.JevContender", no_client)

    verification.sweep(now=_due(opened, "nudge_due_at"))
    verification.sweep(now=_due(opened, "handoff_due_at"))

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF


def test_the_command_runs_the_sweep(conversation, outbox, opened, capsys):  # noqa: F811
    call_command("concierge_verification_sweep")

    assert '"open": 1' in capsys.readouterr().out
