"""Triagem do Concierge (D32, aprovada pelo dono em 02/10/2026: "aprovo a triagem").

Protege quatro coisas, todas sem rede:

1. **A taxonomia é a aprovada.** 12 intenções (as de 23/09), 3 urgências, e a
   tabela intenção → destino da proposta. Nada fora disso sai da triagem, nem do
   modelo.
2. **O sensível escala sempre.** Pessoa, reclamação, alergia e encomenda especial
   reconhecidas pela regra local vão para a equipe mesmo que o modelo discorde.
3. **O operador vê o cartão no lugar certo.** Equipe → sino do Gestor de pedidos
   (mesmo sem pedido na conversa); outra mesa → Admin, sem acordar o balcão.
4. **Ligado e incompleto, a subida avisa.** O system check do Concierge acusa o
   que falta, e desligado não diz nada.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.checks import concierge_findings
from shopman.storefront.concierge import service, triage
from shopman.storefront.tests import test_concierge_engine as engine
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    ScriptedClient,
    _binding,
    _receive,
    _response,
    _text,
)

# O cenário do motor (loja, cliente, conversa, transporte hermético), reaproveitado.
surface = engine.surface
customer = engine.customer
conversation = engine.conversation
outbox = engine.outbox

pytestmark = pytest.mark.django_db


class JsonClient:
    """Cliente do modelo de triagem: devolve um texto fixo e guarda o pedido."""

    def __init__(self, payload):
        self.payload = payload
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(self.payload, Exception):
            raise self.payload
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


# ── 1. Taxonomia ─────────────────────────────────────────────────────


def test_the_routing_table_is_the_approved_one():
    assert triage.INTENTS == (
        "order", "product_question", "hours_delivery", "order_status", "special_order", "house_info",
        "complaint", "allergy", "human", "job", "partnership", "supplier_offer",
    )
    assert triage.URGENCIES == ("now", "today", "can_wait")
    answers = {ref for ref, (destination, _u) in triage.ROUTES.items() if destination == triage.ANSWER}
    team = {ref for ref, (destination, _u) in triage.ROUTES.items() if destination == triage.TEAM}
    other = {ref for ref, (destination, _u) in triage.ROUTES.items() if destination == triage.OTHER_DESK}
    assert answers == {"hours_delivery", "house_info", "product_question", "order_status", "order"}
    assert team == {"human", "complaint", "allergy", "special_order"}
    assert other == {"job", "partnership", "supplier_offer"}
    assert {ref: triage.ROUTES[ref][1] for ref in team} == {
        "human": "now", "complaint": "now", "allergy": "now", "special_order": "today",
    }
    assert {triage.ROUTES[ref][1] for ref in other} == {"can_wait"}


@pytest.mark.parametrize(("text", "intent"), [
    ("quero falar com alguém da equipe", "human"),
    ("meu pedido veio queimado", "complaint"),
    ("sou celíaca, tem glúten?", "allergy"),
    ("preciso de uma encomenda especial para um casamento", "special_order"),
    ("vocês estão contratando? queria mandar meu currículo", "job"),
    ("sou influenciadora e queria propor uma parceria", "partnership"),
    ("sou representante de uma distribuidora de farinha", "supplier_offer"),
    ("meu pedido já saiu?", "order_status"),
    ("que horas vocês abrem domingo?", "hours_delivery"),
    ("aceitam vale refeição? tem estacionamento?", "house_info"),
    ("quero 2 baguetes para amanhã", "order"),
    ("tem croissant de amêndoa hoje?", "product_question"),
])
def test_rules_recognize_each_of_the_twelve_intents(text, intent):
    assert triage.classify_rules(text) == (intent, "rules")


def test_rules_never_invent_an_intent():
    assert triage.classify_rules("oi") == (triage.FALLBACK_INTENT, "default")


# ── 2. Decisão ───────────────────────────────────────────────────────


def test_sensitive_rule_wins_over_the_model():
    client = JsonClient({"intent": "product_question", "urgency": "can_wait", "summary": "Pergunta de pão."})
    decision = triage.decide("sou celíaca, tem glúten no pão?", client=client)
    assert (decision.intent, decision.urgency, decision.destination) == ("allergy", "now", "team")
    assert decision.summary == "Pergunta de pão."


def test_model_proposes_intent_urgency_and_summary():
    client = JsonClient({"intent": "order", "urgency": "today", "summary": "Quer encomendar pães para sábado."})
    decision = triage.decide("dá pra separar umas coisas pra sábado?", client=client)
    assert (decision.intent, decision.urgency, decision.destination, decision.source) == (
        "order", "today", "answer", "model",
    )
    assert decision.summary == "Quer encomendar pães para sábado."
    prompt = client.requests[0]["messages"][0]["content"]
    for ref in triage.INTENTS:
        assert f"- {ref}:" in prompt


def test_model_sensitive_proposal_escalates_too():
    client = JsonClient({"intent": "complaint", "urgency": "can_wait", "summary": "Cobrança errada."})
    decision = triage.decide("olha, a conta de ontem ficou estranha", client=client)
    assert (decision.intent, decision.urgency, decision.destination) == ("complaint", "now", "team")


@pytest.mark.parametrize("payload", [
    {"intent": "invented_intent", "urgency": "now", "summary": "x"},
    "não é JSON",
    RuntimeError("rede caiu"),
])
def test_unreadable_or_failing_model_falls_back_to_rules(payload):
    decision = triage.decide("que horas vocês fecham?", client=JsonClient(payload))
    assert (decision.intent, decision.source, decision.destination) == ("hours_delivery", "rules", "answer")
    assert "que horas vocês fecham?" in decision.summary


def test_model_urgency_outside_the_three_is_discarded():
    client = JsonClient({"intent": "hours_delivery", "urgency": "urgentissimo", "summary": "Horário."})
    assert triage.decide("abre amanhã?", client=client).urgency == "today"


def test_other_desk_never_wakes_anyone_even_if_the_model_says_now():
    client = JsonClient({"intent": "job", "urgency": "now", "summary": "Procura vaga."})
    decision = triage.decide("tem vaga de padeiro?", client=client)
    assert (decision.destination, decision.urgency) == ("other_desk", "can_wait")


def test_second_order_turn_the_chat_cannot_close_goes_to_the_team():
    previous = {"intent": "order", "destination": "answer", "message_ids": [1]}
    decision = triage.decide("quero mesmo assim, 2 baguetes", previous=previous, message_ids=[2])
    assert (decision.destination, decision.urgency, decision.escalated_by) == ("team", "now", "order_not_closed")


def test_order_repeat_is_not_escalated_when_the_chat_can_close_it():
    previous = {"intent": "order", "destination": "answer", "message_ids": [1]}
    decision = triage.decide("quero 2 baguetes", previous=previous, message_ids=[2], commercial_authority=True)
    assert decision.destination == "answer"


def test_a_replayed_turn_does_not_count_as_a_second_attempt():
    previous = {"intent": "order", "destination": "answer", "message_ids": [1]}
    decision = triage.decide("quero pão\nna verdade, três", previous=previous, message_ids=[1, 2])
    assert decision.destination == "answer"


def test_model_is_off_without_the_switch(settings):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS}
    settings.AI_ASSIST_API_KEY = "sk-teste"
    assert triage.classify_with_model("oi", []) is None


def test_rules_summary_is_redacted():
    summary = triage.rules_summary("human", "quero falar com alguém, meu cpf é 123.456.789-09")
    assert "123.456.789-09" not in summary
    assert summary.startswith("Falar com uma pessoa.")


# ── 3. O turno e o cartão ────────────────────────────────────────────


def test_answered_turn_records_triage_on_message_and_conversation(conversation, outbox):
    _receive(conversation, "que horas vocês abrem amanhã?", "t1")
    client = ScriptedClient(_response(_text("Abrimos às 7h."), stop_reason="end_turn"))
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=client)

    assert not result.handoff and result.triage.intent == "hours_delivery"
    conversation.refresh_from_db()
    assert conversation.flags["triage"]["destination"] == "answer"
    assert conversation.flags["triage"]["urgency"] == "today"
    assert "que horas vocês abrem amanhã?" in conversation.summary
    inbound = ConversationMessage.objects.get(conversation=conversation, kind="inbound", text__startswith="que horas")
    assert inbound.envelope["triage"]["intent"] == "hours_delivery"


def test_complaint_card_reaches_the_orders_bell_without_an_order(conversation, outbox):
    from shopman.backstage.services import alerts as alert_service

    _receive(conversation, "meu pedido veio queimado", "t2")
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())

    assert result.handoff
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert conversation.handoff_reason == "Reclamação · agora"
    bell = alert_service.list_active_alerts(scope="orders")
    assert [alert.type for alert in bell] == ["concierge_handoff"]
    card = bell[0].message
    assert card.startswith("Reclamação, urgência: agora.")
    assert "meu pedido veio queimado" in card
    assert "Cliente: Ana." in card
    assert "Live Chat do ManyChat" in card


def test_job_goes_to_the_other_desk_and_stays_out_of_the_bell(conversation, outbox):
    from shopman.backstage.models import OperatorAlert
    from shopman.backstage.services import alerts as alert_service

    _receive(conversation, "boa tarde, vocês estão contratando? tenho currículo", "t3")
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())

    assert result.handoff and result.triage.destination == "other_desk"
    alert = OperatorAlert.objects.get(type="concierge_other_desk")
    assert alert.audience == "operations"
    assert alert.message.startswith("Vaga de emprego, urgência: pode esperar.")
    assert alert_service.list_active_alerts(scope="orders") == []
    conversation.refresh_from_db()
    assert conversation.flags["triage"]["destination"] == "other_desk"
    assert list(Conversation.objects.filter(flags__triage__destination="other_desk")) == [conversation]


def test_triage_model_is_injected_per_turn(conversation, outbox):
    _receive(conversation, "olha, sobre a conta de ontem", "t4")
    triage_client = JsonClient({"intent": "complaint", "urgency": "now", "summary": "Contesta a conta de ontem."})
    result = service.run_turn(
        conversation.pk, _binding(conversation).pk, client=ScriptedClient(), triage_client=triage_client
    )
    assert result.handoff and result.triage.source == "model"
    conversation.refresh_from_db()
    assert conversation.summary == "Contesta a conta de ontem."


# ── 4. O check do Concierge ──────────────────────────────────────────


def _ready_config():
    return {
        **CONCIERGE_SETTINGS,
        "operation_mode": "assist",
        "connections": {
            "manychat-whatsapp-primary": {
                "active": True,
                "provider": "manychat",
                "account": "acc",
                "channel": "whatsapp",
                "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
                "options": {
                    "authentication": {"scheme": "api_key", "keys": ["k"]},
                    "allowed_subjects": ["123"],
                    "handoff_field": "concierge_handoff",
                    "response_window": {"timezone": "America/Sao_Paulo"},
                },
            }
        },
    }


def test_check_is_silent_while_the_concierge_is_off(settings):
    settings.SHOPMAN_CONCIERGE = {**_ready_config(), "enabled": False, "operation_mode": "observe"}
    assert concierge_findings() == []
    from shopman.storefront.checks import check_concierge_readiness

    assert check_concierge_readiness(None) == []


def test_check_passes_when_everything_is_there(settings):
    settings.AI_ASSIST_API_KEY = "sk"
    settings.MANYCHAT_API_TOKEN = "tok"
    assert concierge_findings(_ready_config()) == []


def test_check_warns_that_observe_mode_does_not_answer(settings):
    settings.AI_ASSIST_API_KEY = "sk"
    settings.MANYCHAT_API_TOKEN = "tok"
    findings = concierge_findings({**_ready_config(), "operation_mode": "observe"})
    assert [check_id for check_id, *_ in findings] == ["SHOPMAN_W022"]
    assert "observe" in findings[0][1]


def test_check_names_each_missing_piece(settings):
    settings.AI_ASSIST_API_KEY = ""
    settings.MANYCHAT_API_TOKEN = ""
    config = _ready_config()
    options = config["connections"]["manychat-whatsapp-primary"]["options"]
    options.update(
        authentication={"scheme": "api_key", "keys": []},
        allowed_subjects=[],
        handoff_field="",
        response_window={},
    )
    messages = " | ".join(message for _id, message, _hint in concierge_findings(config))
    for piece in ("AI_ASSIST_API_KEY", "lista de assinantes vazia", "sem chave de ingresso",
                  "MANYCHAT_API_TOKEN", "campo de atendimento humano", "fuso da janela"):
        assert piece in messages


def test_concierge_check_command_when_off(settings):
    settings.SHOPMAN_CONCIERGE = {**_ready_config(), "enabled": False}
    out = io.StringIO()
    call_command("concierge_check", stdout=out)
    assert "Concierge desligado" in out.getvalue()


def test_concierge_check_live_confirms_the_handoff_field(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = _ready_config()
    settings.AI_ASSIST_API_KEY = "sk"
    settings.MANYCHAT_API_TOKEN = "tok"
    from shopman.storefront.management.commands import concierge_check

    monkeypatch.setattr(
        concierge_check.Command, "_fetch_custom_fields", lambda self: [{"name": "concierge_handoff"}]
    )
    out = io.StringIO()
    call_command("concierge_check", "--live", stdout=out)
    assert "campo concierge_handoff existe" in out.getvalue()

    monkeypatch.setattr(concierge_check.Command, "_fetch_custom_fields", lambda self: [])
    with pytest.raises(CommandError):
        call_command("concierge_check", "--live", stdout=io.StringIO())


def test_concierge_check_ids_do_not_collide_with_the_shop_checks():
    import pathlib
    import re

    shop_checks = (pathlib.Path(__file__).resolve().parents[2] / "shop" / "checks.py").read_text(encoding="utf-8")
    used_in_shop = set(re.findall(r'id="(SHOPMAN_[EW]\d+)"', shop_checks))
    assert used_in_shop and {"SHOPMAN_W022", "SHOPMAN_W023"}.isdisjoint(used_in_shop)
