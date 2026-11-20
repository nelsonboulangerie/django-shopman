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


# ── Os defeitos da primeira passada em produção (19/11/2026, 22h11Z) ──────────────


def _observed_entry(*, phone="", subject="5543988887777", ago=timedelta(0), external_id="mc-9"):
    conversation = Conversation.objects.create(phone=phone, customer_ref="cust-9", channel_ref="whatsapp")
    binding = ConversationBinding.objects.create(conversation=conversation, provider="manychat", account="acc-1",
                                                 transport_channel="whatsapp", subject=subject,
                                                 connection_key="manychat-whatsapp-primary")
    message = ConversationMessage.objects.create(conversation=conversation, binding=binding, role="user",
                                                 kind="inbound", text="qual o horário?", external_id=external_id)
    if ago:
        ConversationMessage.objects.filter(pk=message.pk).update(created_at=timezone.now() - ago)
        message.refresh_from_db()
    return message


def test_a_conversation_without_phone_is_transported_by_the_channel(entry):
    """375 de 375 falharam em produção: sem telefone, a identidade virava anônima COM sujeito."""
    message = _observed_entry(phone="")
    assert shadow.identity_of(message) == "transported"
    result = run()
    assert result["sweep"]["failed"] == 0
    decision = ConversationalDecision.objects.get(message=message)
    assert decision.document["context"]["snapshot_hash"].startswith("sha256:")


def test_an_anonymous_entry_carries_no_subject_and_still_decides(entry):
    """Sem telefone e sem ligação de canal (o banco não aceita ligação sem número): anônima, sem sujeito."""
    conversation = Conversation.objects.create(channel_ref="whatsapp")
    message = ConversationMessage(conversation=conversation, role="user", kind="inbound", text="oi")
    assert shadow.identity_of(message) == "anonymous"
    from shopman.storefront.concierge.profile import build_profile

    decision, snapshot, _, _ = shadow.decide_entry(message, profile=build_profile(environment="shadow"))
    assert snapshot.identity.assurance == "anonymous" and snapshot.identity.subject_ref is None
    assert decision.decision_id


def test_the_outcome_window_counts_from_the_entry_not_from_the_decision(entry):
    """No acumulado a decisão é de hoje; a janela de 24 h e 7 dias é a da mensagem do cliente."""
    message = _observed_entry(phone="5543988887777", ago=timedelta(days=10), external_id="mc-old")
    run()
    decision = ConversationalDecision.objects.get(message=message)
    outcomes = {o.metric: o for o in ConversationalOutcome.objects.filter(decision=decision)}
    assert outcomes["orders_24h"].window_start == decision.entry_at
    assert outcomes["orders_24h"].observation == "observed" and outcomes["orders_7d"].observation == "observed"


def test_entries_that_always_fail_never_starve_the_new_ones(entry, monkeypatch):
    """Entrada que falha sempre volta a cada ciclo, mas não ocupa o lote: as novas seguem decididas."""
    broken = [_observed_entry(phone="1", subject=f"55430000000{n}", external_id=f"mc-b{n}", ago=timedelta(days=30))
              for n in range(3)]
    real = shadow.decide_entry

    def flaky(message, **kwargs):
        if message.pk in {m.pk for m in broken}:
            raise ValueError("defeito permanente")
        return real(message, **kwargs)

    monkeypatch.setattr(shadow, "decide_entry", flaky)
    with mock.patch.object(shadow.logger, "warning") as warning:
        result = shadow.sweep(limit=2)
    assert result == {"enabled": 1, "decided": 1, "failed": 3}
    assert ConversationalDecision.objects.filter(message=entry).exists()
    # Um aviso só no ciclo, com a contagem; nunca um por entrada.
    assert warning.call_count == 1 and warning.call_args.args[1] == 3


# ── A junção que anda (segunda passada em produção, 20/11/2026, 15h40Z) ───────────


def test_the_join_moves_on_instead_of_rereading_the_same_oldest_decisions(entry):
    """Com mais decisões do que o teto, as novas ganham resultado no ciclo seguinte."""
    old = [_observed_entry(phone="", subject=f"77{n:08d}", external_id=f"mc-o{n}", ago=timedelta(days=30))
           for n in range(3)]
    shadow.sweep(limit=10)
    total = ConversationalDecision.objects.count()
    assert total == 4  # as três antigas e a da fixture
    first = shadow.join_outcomes(limit=2)
    second = shadow.join_outcomes(limit=2)
    assert first["recorded"] > 0 and second["recorded"] > 0
    with_outcome = ConversationalDecision.objects.filter(outcomes__isnull=False).distinct().count()
    assert with_outcome == total
    # As antigas, com as duas janelas fechadas, têm resultado final e não voltam ao lote.
    for message in old:
        decision = ConversationalDecision.objects.get(message=message)
        assert {o.observation for o in decision.outcomes.filter(superseded_by__isnull=True)} == {"observed"}
    assert not shadow.pending_outcomes(timezone.now()).filter(message__in=old).exists()


def test_unknown_with_a_closed_window_is_final(entry):
    """Sem identidade e com a janela fechada, não há mais o que medir: a decisão sai do lote."""
    message = _observed_entry(phone="", subject="7700000099", external_id="mc-anon", ago=timedelta(days=30))
    Conversation.objects.filter(pk=message.conversation_id).update(customer_ref="")
    shadow.sweep(limit=10)
    shadow.join_outcomes()
    decision = ConversationalDecision.objects.get(message=message)
    assert {o.observation for o in decision.outcomes.filter(superseded_by__isnull=True)} == {"unknown"}
    assert not shadow.pending_outcomes(timezone.now()).filter(pk=decision.pk).exists()


def test_an_open_window_comes_back_until_it_closes(entry):
    run()
    decision = ConversationalDecision.objects.get(message=entry)
    assert shadow.pending_outcomes(timezone.now()).filter(pk=decision.pk).exists()  # janela aberta, censored
    later = decision.entry_at + timedelta(days=8)
    shadow.join_outcomes(now=later)
    assert not shadow.pending_outcomes(later).filter(pk=decision.pk).exists()


# ── O caminho até o pedido pelo assinante ligado (#2853) ───────────────────────────


def _subscriber_customer(ref, subject, *, active=True):
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
    from shopman.guestman.models import Customer

    customer = Customer.objects.create(ref=ref, first_name="Cliente", is_active=active)
    CustomerIdentifier.objects.create(customer=customer, identifier_type=IdentifierType.MANYCHAT,
                                      identifier_value=subject, source_system="manychat")
    return customer


def _order(customer_ref, at, ref):
    from shopman.orderman.models import Order

    order = Order.objects.create(ref=ref, channel_ref="whatsapp", session_key=f"s-{ref}", status="new",
                                 data={"customer_ref": customer_ref})
    Order.objects.filter(pk=order.pk).update(created_at=at)


def _anonymous_entry(subject, external_id, ago=timedelta(days=10)):
    message = _observed_entry(phone="", subject=subject, external_id=external_id, ago=ago)
    Conversation.objects.filter(pk=message.conversation_id).update(customer_ref="")
    return message


def _current(decision):
    return {o.metric: o for o in decision.outcomes.filter(superseded_by__isnull=True)}


def test_a_conversation_without_phone_reaches_the_order_by_the_linked_subscriber(entry):
    """Sem telefone e sem cliente na conversa, o assinante ligado pelo guestman leva ao pedido."""
    message = _anonymous_entry("3100000001", "mc-link")
    _subscriber_customer("cust-link", "3100000001")
    _order("cust-link", message.created_at + timedelta(hours=2), "ORD-LINK")
    shadow.sweep(limit=10)
    shadow.join_outcomes()
    decision = ConversationalDecision.objects.get(message=message)
    assert decision.customer_ref == "cust-link"
    outcomes = _current(decision)
    assert (outcomes["orders_24h"].observation, outcomes["orders_24h"].value) == ("observed", 1)
    assert (outcomes["orders_7d"].observation, outcomes["orders_7d"].value) == ("observed", 1)


def test_an_unknown_comes_back_when_the_subscriber_gets_linked_later(entry):
    """O unknown de janela fechada é final só enquanto não há caminho; ligado depois, ele é medido."""
    message = _anonymous_entry("3100000002", "mc-later")
    shadow.sweep(limit=10)
    shadow.join_outcomes()
    decision = ConversationalDecision.objects.get(message=message)
    assert {o.observation for o in _current(decision).values()} == {"unknown"}
    assert not shadow.pending_outcomes(timezone.now()).filter(pk=decision.pk).exists()

    _subscriber_customer("cust-later", "3100000002")
    _order("cust-later", message.created_at + timedelta(days=2), "ORD-LATER")
    assert shadow.pending_outcomes(timezone.now()).filter(pk=decision.pk).exists()
    shadow.join_outcomes()
    outcomes = _current(decision)
    assert (outcomes["orders_24h"].observation, outcomes["orders_24h"].value) == ("observed", 0)
    assert (outcomes["orders_7d"].observation, outcomes["orders_7d"].value) == ("observed", 1)
    assert outcomes["orders_7d"].supersedes is not None, "o unknown fica no histórico, substituído"
    assert not shadow.pending_outcomes(timezone.now()).filter(pk=decision.pk).exists()


def test_two_customers_or_an_inactive_one_stay_unknown(entry):
    """Ambíguo ou cliente inativo: a sombra não escolhe nem ressuscita, segue sem identidade."""
    ambiguous = _anonymous_entry("3100000003", "mc-amb")
    ConversationBinding.objects.create(conversation_id=ambiguous.conversation_id, provider="manychat",
                                       account="acc-1", transport_channel="instagram", subject="3100000004",
                                       connection_key="manychat-instagram")
    _subscriber_customer("cust-a", "3100000003")
    _subscriber_customer("cust-b", "3100000004")
    inactive = _anonymous_entry("3100000005", "mc-off")
    _subscriber_customer("cust-off", "3100000005", active=False)

    assert shadow.customer_ref_of(ambiguous.conversation_id) == ""
    assert shadow.customer_ref_of(inactive.conversation_id) == ""
    shadow.sweep(limit=10)
    shadow.join_outcomes()
    for message in (ambiguous, inactive):
        decision = ConversationalDecision.objects.get(message=message)
        assert {o.observation for o in _current(decision).values()} == {"unknown"}
