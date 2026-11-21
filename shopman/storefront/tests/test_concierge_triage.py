"""Triagem do Concierge (D32, aprovada pelo dono em 02/10/2026: "aprovo a triagem").

Protege quatro coisas, todas sem rede:

1. **A taxonomia é a aprovada.** 12 intenções (as de 23/09), 3 urgências, e a
   tabela intenção → destino da proposta. Nada fora disso sai da triagem, nem do
   Jev (a triagem não chama modelo de texto desde o WP-08).
2. **O sensível escala sempre.** Pessoa, reclamação, alergia e encomenda especial
   reconhecidas pela regra local vão para a equipe mesmo que o Jev discorde
   (``test_concierge_triage_jev``).
3. **O operador vê o cartão no lugar certo.** Equipe → sino do Gestor de pedidos
   (mesmo sem pedido na conversa); outra mesa → Admin, sem acordar o balcão.
4. **Ligado e incompleto, a subida avisa.** O system check do Concierge acusa o
   que falta, e desligado não diz nada.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop.models import Conversation, ConversationMessage
from shopman.shop.tests.ai_support import configure_ai
from shopman.storefront.checks import concierge_findings
from shopman.storefront.concierge import service, triage
from shopman.storefront.tests import test_concierge_engine as engine
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _binding,
    _receive,
)

# O cenário do motor (loja, cliente, conversa, transporte hermético), reaproveitado.
surface = engine.surface
customer = engine.customer
conversation = engine.conversation
outbox = engine.outbox

pytestmark = pytest.mark.django_db


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


def test_rules_summary_is_redacted():
    summary = triage.rules_summary("human", "quero falar com alguém, meu cpf é 123.456.789-09")
    assert "123.456.789-09" not in summary
    assert summary.startswith("Falar com uma pessoa.")


# ── 3. O turno e o cartão ────────────────────────────────────────────


def test_answered_turn_records_triage_on_message_and_conversation(conversation, outbox):
    _receive(conversation, "que horas vocês abrem amanhã?", "t1")
    result = service.run_turn(conversation.pk, _binding(conversation).pk)

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
    result = service.run_turn(conversation.pk, _binding(conversation).pk)

    assert result.handoff
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert conversation.handoff_reason == "Reclamação · agora"
    bell = alert_service.list_active_alerts(scope="orders")
    assert [alert.type for alert in bell] == ["concierge_handoff"]
    # Só a fala dela, entre aspas (coordenação, 20/11/2026): quem e por quê vão no
    # título, que a projeção escreve; onde responder, no botão.
    card = bell[0].message
    assert card == "“meu pedido veio queimado”"
    from shopman.backstage.projections.alerts import handoff_cards

    assert handoff_cards([bell[0].pk])[bell[0].pk]["subject"] == "Ana fez uma reclamação"


def test_job_goes_to_the_other_desk_and_stays_out_of_the_bell(conversation, outbox):
    from shopman.backstage.models import OperatorAlert
    from shopman.backstage.services import alerts as alert_service

    _receive(conversation, "boa tarde, vocês estão contratando? tenho currículo", "t3")
    result = service.run_turn(conversation.pk, _binding(conversation).pk)

    assert result.handoff and result.triage.destination == "other_desk"
    alert = OperatorAlert.objects.get(type="concierge_other_desk")
    assert alert.audience == "operations"
    assert alert.message.startswith("Vaga de emprego, urgência: pode esperar.")
    assert alert_service.list_active_alerts(scope="orders") == []
    conversation.refresh_from_db()
    assert conversation.flags["triage"]["destination"] == "other_desk"
    assert list(Conversation.objects.filter(flags__triage__destination="other_desk")) == [conversation]


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
    configure_ai("sk")
    settings.MANYCHAT_API_TOKEN = "tok"
    assert concierge_findings(_ready_config()) == []


def test_check_warns_that_observe_mode_does_not_answer(settings):
    configure_ai("sk")
    settings.MANYCHAT_API_TOKEN = "tok"
    findings = concierge_findings({**_ready_config(), "operation_mode": "observe"})
    assert [check_id for check_id, *_ in findings] == ["SHOPMAN_W022"]
    assert "observe" in findings[0][1]


def test_check_names_each_missing_piece(settings):
    configure_ai("")
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
    for piece in ("lista de assinantes vazia", "sem chave de ingresso",
                  "MANYCHAT_API_TOKEN", "campo de atendimento humano", "fuso da janela"):
        assert piece in messages
    # Sem conexão de IA não é pendência (WP-03): é aviso, à parte.
    assert "conexão de IA" not in messages


def test_without_ai_connection_the_check_only_warns(settings):
    """WP-03: sem conexão de IA a Concierge responde sem modelo; o check avisa e o
    ``concierge_check`` não reprova por isso."""
    from shopman.storefront.checks import check_concierge_readiness, concierge_notices

    configure_ai("")
    settings.MANYCHAT_API_TOKEN = "tok"
    settings.SHOPMAN_CONCIERGE = _ready_config()
    assert concierge_findings() == []
    notices = concierge_notices()
    assert notices and all("sem leitura por modelo" in message for _id, message, _hint in notices)
    assert {warning.id for warning in check_concierge_readiness(None)} == {"SHOPMAN_W022"}
    out = io.StringIO()
    call_command("concierge_check", stdout=out)
    assert "sem leitura por modelo" in out.getvalue()


def test_concierge_check_command_when_off(settings):
    settings.SHOPMAN_CONCIERGE = {**_ready_config(), "enabled": False}
    out = io.StringIO()
    call_command("concierge_check", stdout=out)
    assert "Concierge desligado" in out.getvalue()


def test_concierge_check_live_confirms_the_handoff_field(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = _ready_config()
    configure_ai("sk")
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


# ── Só um link: continua a fala anterior (#2910, msg-596) ─────────────


@pytest.mark.parametrize("text", ["[link omitido]", "https://drive.google.com/file/d/abc/view", "www.exemplo.com/cv.pdf"])
def test_a_bare_link_after_offering_a_resume_goes_to_the_other_desk(text):
    decision = triage.decide(text, context=[("Cliente", "Bom Dia, posso te mandar um Currículo")])

    assert decision.intent == "job"
    assert decision.destination == triage.OTHER_DESK


def test_a_bare_link_after_a_question_the_concierge_answers_stays_with_the_concierge():
    decision = triage.decide("https://exemplo.com/foto.jpg", context=[("Cliente", "tem croissant hoje?")])

    assert decision.destination == triage.ANSWER


def test_a_link_with_words_follows_the_usual_rule():
    decision = triage.decide(
        "olha esse bolo https://exemplo.com/bolo.jpg, vocês fazem?",
        context=[("Cliente", "posso te mandar um currículo?")],
    )

    assert decision.intent != "job"
