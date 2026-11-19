"""A decisão em sombra da Concierge (N5): o que o framework faria, sem fazer nada.

O que estes testes seguram:

- K36: em sombra, nenhuma chamada às portas de escrita nem envio. Espiões nas portas reais
  (``ShopmanCommerceExecute.execute``, o envio do transporte) provam que nada foi chamado;
- K01: a mesma entrada varrida duas vezes grava um registro só;
- o registro não tem texto do cliente: a mensagem entra por referência;
- o que deriva da observação some com ela no ``purge_observations``;
- K33: janela não fechada grava ``censored``, sem valor; madura, ``observed`` substitui;
- desligada pela ``Shop`` (o padrão), a varredura não toca em nada.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from conversational_commerce.testing.conformance import conformance
from django.core.management import call_command
from django.utils import timezone

from shopman.shop.models import (
    Channel,
    Conversation,
    ConversationalDecision,
    ConversationalOutcome,
    ConversationBinding,
    ConversationMessage,
    Shop,
)
from shopman.storefront.concierge import service, shadow

pytestmark = pytest.mark.django_db

TEXT = "qual o horário de vocês hoje? meu nome é Fulana"


@pytest.fixture
def entry():
    Shop.objects.create(name="Nelson Boulangerie", conversational_shadow_enabled=True)
    Channel.objects.create(ref="whatsapp", name="WhatsApp", config={})
    conversation = Conversation.objects.create(phone="5543999990000", customer_ref="cust-1", channel_ref="whatsapp")
    binding = ConversationBinding.objects.create(conversation=conversation, provider="manychat", account="acc-1",
                                                 transport_channel="whatsapp", subject="5543999990000",
                                                 connection_key="manychat-whatsapp-primary")
    return ConversationMessage.objects.create(conversation=conversation, binding=binding, role="user",
                                              kind="inbound", text=TEXT, external_id="mc-1")


def run():
    out = StringIO()
    call_command("concierge_shadow_decisions", stdout=out)
    return json.loads(out.getvalue())


@conformance("K36", scope="adapter")
def test_k36_shadow_decides_and_never_writes_or_sends(entry):
    writes = ("shopman.shop.services.checkout.process", "shopman.storefront.concierge.discount._grant",
              "shopman.storefront.concierge.cancellation._execute", "shopman.storefront.concierge.order_addition.apply",
              "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter.send_text",
              "shopman.storefront.concierge.transport.send_for", "shopman.shop.ai.resolve")
    spies = [mock.patch(target) for target in writes]
    called = [spy.start() for spy in spies]
    try:
        result = run()
    finally:
        for spy in spies:
            spy.stop()
    assert result["sweep"] == {"enabled": 1, "decided": 1, "failed": 0}
    assert [target for target, spy in zip(writes, called, strict=True) if spy.called] == []
    decision = ConversationalDecision.objects.get(message=entry)
    assert decision.environment == "shadow" and "inform" in decision.chosen_moves  # o horário, com fato
    assert "ask_hours" in decision.acts


@conformance("K01", invariants=("N12",), scope="adapter")
def test_k01_the_same_entry_swept_twice_is_one_record(entry):
    run()
    second = run()
    assert second["sweep"]["decided"] == 0
    assert ConversationalDecision.objects.filter(message=entry).count() == 1


def test_the_record_carries_no_customer_text(entry):
    run()
    decision = ConversationalDecision.objects.get(message=entry)
    stored = json.dumps({"document": decision.document, "acts": decision.acts, "blocked": decision.blocked,
                         "unknown": decision.unknown_facts})
    assert "Fulana" not in stored and "horário" not in stored
    assert decision.decision_hash.startswith("sha256:") and decision.snapshot_hash.startswith("sha256:")


def test_what_derives_from_an_observation_goes_with_it(entry):
    run()
    decision = ConversationalDecision.objects.get(message=entry)
    ConversationalOutcome.objects.create(
        decision=decision, outcome_id="out-1", metric="orders_24h", window_start=timezone.now(),
        window_end=timezone.now() + timedelta(hours=24), observation="censored", source="orderman")
    # A entrada observada (não atendida) que a retenção venceu: é a que a limpeza apaga.
    ConversationMessage.objects.filter(pk=entry.pk).update(
        automation_eligible=False, envelope={"processing_mode": "observe"},
        retention_until=timezone.now() - timedelta(minutes=1))
    service.purge_observations(now=timezone.now())
    assert not ConversationalDecision.objects.exists() and not ConversationalOutcome.objects.exists()


@conformance("K33", invariants=("N21",), scope="adapter")
def test_k33_open_window_is_censored_and_the_mature_one_supersedes(entry):
    run()
    decision = ConversationalDecision.objects.get(message=entry)
    opened = {o.metric: o for o in ConversationalOutcome.objects.filter(decision=decision)}
    assert {m: (o.observation, o.value) for m, o in opened.items()} == {
        "orders_24h": ("censored", None), "orders_7d": ("censored", None)}
    assert shadow.join_outcomes()["recorded"] == 0  # nada mudou: não grava de novo
    later = decision.decided_at + timedelta(days=2)
    assert shadow.join_outcomes(now=later)["recorded"] == 1
    mature = ConversationalOutcome.objects.get(decision=decision, metric="orders_24h", superseded_by__isnull=True)
    assert (mature.observation, mature.value, mature.supersedes_id) == ("observed", 0, opened["orders_24h"].pk)
    assert ConversationalOutcome.objects.filter(decision=decision, metric="orders_24h").count() == 2


def test_off_by_default_the_sweep_touches_nothing(entry):
    Shop.objects.update(conversational_shadow_enabled=False)
    result = run()
    assert result == {"join": {"enabled": 0, "recorded": 0}, "sweep": {"decided": 0, "enabled": 0, "failed": 0}}
    assert not ConversationalDecision.objects.exists()


def test_a_failing_entry_never_stops_the_cycle(entry):
    with mock.patch.object(shadow, "decide_entry", side_effect=RuntimeError("fonte fora")):
        result = run()
    assert result["sweep"] == {"enabled": 1, "decided": 0, "failed": 1}
    assert not ConversationalDecision.objects.exists()
