"""O Jev decidindo a intenção na Concierge (pedido do dono, 02/10/2026, D-028).

Duas metades, sem rede (o Jev é um transporte falso):

1. **A troca.** Com ``triage_classifier = "jev"`` a intenção é a mais provável do
   Jev acima do corte; o sensível da regra local continua vencendo; falha, chave
   ausente ou nenhuma intenção acima do corte devolvem a decisão à regra; o texto
   sai redigido.
2. **A sombra.** O ciclo do piloto grava, em cada mensagem nova, a decisão da
   regra e a do Jev, e o relatório conta onde discordam. Nada muda para o cliente.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from shopman.shop.models import ConversationMessage
from shopman.storefront.concierge import intent_pilot, triage
from shopman.storefront.concierge.intent_benchmark import ContenderNotConfigured, Prediction
from shopman.storefront.tests.test_concierge_engine import CONCIERGE_SETTINGS
from shopman.storefront.tests.test_intent_pilot import _conversation, _inbound

pytestmark = pytest.mark.django_db


class FakeJev:
    """Devolve probabilidades fixas e guarda o texto que recebeu."""

    model = "jev-test"

    def __init__(self, scores=None, *, error: Exception | None = None):
        self.given = scores or {}
        self.error = error
        self.texts: list[str] = []

    def scores(self, sample, categories):
        self.texts.append(sample.text)
        if self.error:
            raise self.error
        return Prediction(
            intents={c.ref: self.given.get(c.ref, 0.01) for c in categories}, latency_ms=120.0
        )


@pytest.fixture
def jev_on(settings):
    settings.SHOPMAN_CONCIERGE = {
        **CONCIERGE_SETTINGS,
        "triage_with_model": True,
        "triage_classifier": "jev",
    }


# ── 1. A troca ───────────────────────────────────────────────────────


def test_jev_decides_the_intent_when_chosen(jev_on):
    jev = FakeJev({"partnership": 0.93, "hours_delivery": 0.4})

    decision = triage.decide("vocês abrem domingo? queria gravar um vídeo", client=jev)

    assert (decision.intent, decision.source, decision.destination) == ("partnership", "jev", "other_desk")
    assert decision.urgency == "can_wait"  # o Jev não dá urgência: vale a da tabela


def test_sensitive_from_the_rules_still_wins_over_jev(jev_on):
    jev = FakeJev({"order": 0.99})

    decision = triage.decide("quero falar com um atendente", client=jev)

    assert (decision.intent, decision.source, decision.destination) == ("human", "rules", "team")


@pytest.mark.parametrize(
    "jev",
    [
        FakeJev(error=RuntimeError("rede caiu")),
        FakeJev(error=ContenderNotConfigured("sem chave")),
        FakeJev({"order": 0.3}),  # nenhuma acima do corte
    ],
    ids=["falha", "sem-chave", "abaixo-do-corte"],
)
def test_without_a_useful_answer_from_jev_the_rules_decide(jev_on, jev):
    decision = triage.decide("que horas vocês abrem?", client=jev)

    assert (decision.intent, decision.source) == ("hours_delivery", "rules")


def test_the_text_goes_to_jev_redacted(jev_on):
    jev = FakeJev({"order": 0.9})

    triage.decide("quero 2 pães, meu cpf é 123.456.789-09", client=jev)

    assert "123.456.789-09" not in jev.texts[0]
    assert "2 pães" in jev.texts[0]


def test_the_default_classifier_is_still_anthropic(settings):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "triage_with_model": True}
    assert triage.classifier() == "anthropic"


def test_model_switch_off_keeps_jev_out(settings):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "triage_with_model": False, "triage_classifier": "jev"}
    jev = FakeJev({"partnership": 0.99})

    decision = triage.decide("que horas vocês abrem?", client=jev)

    assert decision.source == "rules" and jev.texts == []


# ── 2. A sombra ──────────────────────────────────────────────────────


def test_shadow_stamps_rules_and_jev_side_by_side():
    conversation = _conversation()
    message = _inbound("que horas vocês abrem domingo?", conversation)
    jev = FakeJev({"hours_delivery": 0.88})

    assert intent_pilot.shadow_triage(contender=jev) == 1

    shadow = ConversationMessage.objects.get(pk=message.pk).envelope["triage_shadow"]
    assert (shadow["rules"], shadow["jev"], shadow["model"]) == ("hours_delivery", "hours_delivery", "jev-test")
    assert shadow["jev_scores"]["hours_delivery"] == 0.88
    assert len(shadow["jev_scores"]) == 12

    # A mensagem já com sombra não volta ao Jev.
    assert intent_pilot.shadow_triage(contender=jev) == 0
    assert len(jev.texts) == 1


def test_provider_failure_stops_the_batch_without_stamping():
    _inbound("que horas vocês abrem?")
    jev = FakeJev(error=RuntimeError("cota"))

    assert intent_pilot.shadow_triage(contender=jev) == 0
    assert not ConversationMessage.objects.filter(envelope__has_key="triage_shadow").exists()


def test_shadow_needs_the_approved_provider(settings):
    settings.SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED = frozenset({"anthropic"})
    _inbound("que horas vocês abrem?")

    with pytest.raises(ContenderNotConfigured):
        intent_pilot.shadow_triage()


def test_report_counts_agreement_and_where_jev_would_escalate():
    conversation = _conversation()
    _inbound("que horas vocês abrem?", conversation)
    intent_pilot.shadow_triage(contender=FakeJev({"hours_delivery": 0.9}))
    _inbound("o pão de ontem estava duro", conversation)  # a regra não vê reclamação
    intent_pilot.shadow_triage(contender=FakeJev({"complaint": 0.95}))

    out = io.StringIO()
    call_command("concierge_triage_shadow", stdout=out)
    report = out.getvalue()

    assert "2 mensagens" in report
    assert "Mesma intenção que a regra local: 1 (50%)" in report
    assert "Jev viu sensível e a regra não (1)" in report
    assert "regra: product_question  Jev: complaint" in report
