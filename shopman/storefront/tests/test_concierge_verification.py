"""WP-05 do plano da Concierge: "não sei, vou verificar", pedir à equipe e devolver ao cliente.

Os sete cenários do "Pronto quando" (``docs/plans/CONCIERGE-PLANO-DE-ACAO.md``), cada um
com o nome que o plano dá, mais o que o cartão do sino precisa (endpoints e ações da
projeção), a copy e os prazos do Admin:

1. sem fato no expediente: cartão ``concierge_verify`` com a pergunta redigida, resposta
   com o prazo, e as outras partes da mesma mensagem respondidas;
2. a equipe responde e o cliente recebe "A equipe confirmou: ...", pelas regras de forma
   e pela janela de 24 horas;
3. "e aí?" durante a espera é respondido pelo estado, sem cartão novo;
4. "assumo a conversa" vira handoff;
5. fora do expediente, o prazo vem do calendário da casa;
6. fora da janela de 24 horas, nada é prometido;
7. turno revogado não grava ``verifying``.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.test import override_settings
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Conversation, Shop
from shopman.storefront.concierge import house_rules, intents, service, verification
from shopman.storefront.concierge.contracts import WindowEvidence
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    CONCIERGE_SETTINGS,
    SUBJECT,
    _binding,
    _event,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act

pytestmark = pytest.mark.django_db

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

PARKING = "vocês têm estacionamento? me liga no (43) 99876-5432"
TWO_PARTS = "tem pão francês? e " + PARKING


@pytest.fixture(autouse=True)
def plural(request, monkeypatch):
    """As intenções no plural para a coorte, DEPOIS da fixture da conversa (que grava as do agente)."""
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    if "conversation" in request.fixturenames:
        request.getfixturevalue("conversation")
        request.getfixturevalue("settings").SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS


def _receive(conversation, text: str, event_id: str, *, window_hours: int = 24):  # noqa: F811
    event = _event(text=text, event_id=event_id, subject=_binding(conversation).subject)
    if window_hours != 24:
        now = timezone.now()
        event = dataclasses.replace(
            event,
            window_evidence=WindowEvidence(
                policy="commercial-test-v1",
                source="authenticated-test-event",
                observed_at=now,
                valid_until=now + timedelta(hours=window_hours),
                assurance="provider_window",
            ),
        )
    return service.receive_inbound(event)


def _turn(conversation, text: str, acts, event_id: str, **receive):  # noqa: F811
    _receive(conversation, text, event_id, **receive)
    return service.run_turn(conversation.pk, _binding(conversation).pk, intents_client=ReaderClient(acts))


def _ask_parking(conversation, event_id="verificar-1", **receive):  # noqa: F811
    return _turn(
        conversation,
        TWO_PARTS,
        [_act("product_question", "tem pão francês?", "pão francês"), _act("house_info", PARKING)],
        event_id,
        **receive,
    )


def _cards():
    return OperatorAlert.objects.filter(type=verification.ALERT_TYPE)


def _record(conversation):  # noqa: F811
    conversation.refresh_from_db()
    return (conversation.flags or {}).get(verification.FLAG_KEY)


def _closed_until(days_ahead: int) -> None:
    """A casa fechada hoje, abrindo só daqui a ``days_ahead`` dias, das 7h às 19h."""
    weekday = DAYS[(timezone.localdate() + timedelta(days=days_ahead)).weekday()]
    shop = Shop.objects.get()
    shop.opening_hours = {weekday: {"open": "07:00", "close": "19:00"}}
    shop.save(update_fields=["opening_hours"])


# ── 1. Sem fato no expediente ─────────────────────────────────────────


def test_1_without_fact_in_business_hours_asks_the_team_and_answers_the_other_parts(conversation, outbox):  # noqa: F811
    result = _ask_parking(conversation)

    assert not result.handoff
    reply = outbox.sent[-1]
    assert "Pão Francês" in reply, "a outra parte da mesma mensagem é respondida"
    assert "não tenho essa informação aqui" in reply
    assert reply.rstrip().endswith("Já perguntei para a equipe e te respondo por aqui em até 10 minutos.")
    assert "Se quiser, chamo alguém da equipe" not in reply, "a oferta virou pergunta feita"

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE, "não é handoff: a conversa segue com a Concierge"
    record = _record(conversation)
    assert record["status"] == verification.OPEN
    assert [q["text"] for q in record["questions"]] == [verification.question_text(intents.Act("house_info", span=PARKING))]
    assert record["promise"]["kind"] == verification.NOW
    assert record["nudge_due_at"] and record["handoff_due_at"]

    card = _cards().get()
    assert card.audience == "orders", "vai ao sino do Gestor de pedidos"
    assert record["alert_pk"] == card.pk
    assert "estacionamento" in card.message
    assert "99876-5432" not in card.message, "a pergunta vai redigida para o cartão"
    assert "Prometemos responder até " in card.message
    assert card.respond_by == timezone.datetime.fromisoformat(record["nudge_due_at"]), (
        "o sino conta até o prazo prometido, e só até ele"
    )
    assert "Pergunta do cliente" not in card.message and "Cliente:" not in card.message


def test_1_the_first_deadline_comes_from_the_channel_config_in_the_admin(conversation, outbox):  # noqa: F811
    channel = Channel.objects.get(ref="whatsapp")
    channel.config = {**channel.config, "confirmation": {**channel.config["confirmation"],
                                                          "concierge_verify_nudge_minutes": 15}}
    channel.save(update_fields=["config"])

    _ask_parking(conversation)

    assert "em até 15 minutos" in outbox.sent[-1]


def test_1_a_question_with_the_team_called_in_the_turn_opens_no_verification(conversation, outbox):  # noqa: F811
    """Com reclamação junto, a equipe assume e vê todas as partes: não há verificação à parte."""
    result = _turn(
        conversation,
        "o pão de ontem veio queimado, quero reclamar. e vocês têm estacionamento?",
        [_act("complaint", "o pão de ontem veio queimado, quero reclamar"), _act("house_info", "vocês têm estacionamento?")],
        "verificar-reclamacao",
    )

    assert result.handoff
    assert _record(conversation) is None
    assert not _cards().exists()


# ── 2. A equipe responde e a resposta volta pela Concierge ────────────


def test_2_the_team_answers_and_the_customer_receives_it_through_the_concierge(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()

    result = verification.answer(card.pk, "Temos sim — duas vagas na frente da loja.", actor="ana")

    assert result.ok and not result.code
    assert outbox.sent[-1] == "A equipe confirmou: Temos sim, duas vagas na frente da loja."
    assert "—" not in outbox.sent[-1], "passa pelas regras de forma (R12, sem travessão)"
    record = _record(conversation)
    assert record["status"] == verification.ANSWERED and record["closed_by"] == "ana"
    card.refresh_from_db()
    assert card.resolved_at is not None, "o cartão fecha quando a resposta sai"
    assert verification.answer(card.pk, "de novo", actor="ana").code == "not_open"


def test_2_outside_the_24h_window_the_answer_does_not_go_and_the_question_stays_open(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    sent = len(outbox.sent)
    past = timezone.now() - timedelta(minutes=1)
    for message in conversation.messages.filter(kind="inbound"):
        envelope = dict(message.envelope)
        envelope["window_evidence"] = {**envelope["window_evidence"], "valid_until": past.isoformat()}
        message.envelope = envelope
        message.save(update_fields=["envelope"])

    result = verification.answer(card.pk, "Temos sim, duas vagas.", actor="ana")

    assert not result.ok and result.code == "not_sent" and result.detail == "window_closed"
    assert len(outbox.sent) == sent, "fora da janela, nada sai"
    assert _record(conversation)["status"] == verification.OPEN, "a pergunta continua aberta no cartão"
    card.refresh_from_db()
    assert card.resolved_at is None


def test_2_an_answer_with_personal_data_is_held_and_nothing_goes(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    sent = len(outbox.sent)

    result = verification.answer(card.pk, "Liga para o Jorge no 123.456.789-09", actor="ana")

    assert not result.ok and result.code == "house_rule_held" and "R13" in result.detail
    assert len(outbox.sent) == sent
    assert verification.answer(card.pk, "   ", actor="ana").code == "empty_answer"


# ── 3. "E aí?" durante a espera ───────────────────────────────────────


def test_3_e_ai_while_waiting_is_answered_by_the_state_without_a_new_card(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    reader = ReaderClient([])
    _receive(conversation, "e aí?", "verificar-e-ai")
    result = service.run_turn(conversation.pk, _binding(conversation).pk, intents_client=reader)

    assert not result.handoff
    assert outbox.sent[-1].startswith("Ainda estou esperando a equipe confirmar sobre “")
    assert outbox.sent[-1].endswith("Assim que chegar, te aviso por aqui.")
    assert not reader.requests, "a espera é respondida pelo estado, sem leitura"
    assert _cards().count() == 1
    assert len(_record(conversation)["questions"]) == 1


def test_3_a_new_question_while_waiting_joins_the_same_card(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    _turn(conversation, "e tem wi-fi aí?", [_act("house_info", "e tem wi-fi aí?")], "verificar-wifi")

    assert outbox.sent[-1].endswith("Juntei isso à pergunta que já fiz para a equipe e te respondo tudo junto por aqui.")
    assert _cards().count() == 1, "uma verificação aberta por conversa"
    card = _cards().get()
    assert "1) “" in card.message and "2) “" in card.message and "wi" in card.message
    assert len(_record(conversation)["questions"]) == 2


# ── 4. "Assumo a conversa" ────────────────────────────────────────────


def test_4_taking_over_the_conversation_becomes_a_handoff(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()

    result = verification.take_over(card.pk, actor="ana")

    assert result.ok
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert outbox.sent[-1] == "Alguém da equipe continua com você por aqui."
    assert outbox.flags[-1] is True, "a marca de atendimento humano vai ao ManyChat"
    assert _record(conversation)["status"] == verification.TAKEN_OVER
    card.refresh_from_db()
    assert card.resolved_at is not None
    assert not OperatorAlert.objects.filter(type="concierge_handoff").exists(), (
        "quem assumiu já é a equipe: sem cartão de cliente esperando atendente"
    )
    assert verification.answer(card.pk, "tarde demais", actor="ana").code in {"not_open", "with_team"}


# ── 5. Fora do expediente ─────────────────────────────────────────────


def test_5_outside_business_hours_the_deadline_comes_from_the_house_calendar(conversation, outbox):  # noqa: F811
    _closed_until(1)

    result = _ask_parking(conversation, window_hours=48)

    assert not result.handoff
    assert outbox.sent[-1].rstrip().endswith("Já deixei a pergunta com a equipe e te respondo por aqui até amanhã às 7h10.")
    record = _record(conversation)
    assert record["promise"]["kind"] == verification.LATER
    due = timezone.localtime(timezone.datetime.fromisoformat(record["nudge_due_at"]))
    assert (due.date(), due.hour, due.minute) == (timezone.localdate() + timedelta(days=1), 7, 10)
    assert "Prometemos responder até amanhã às 7h10." in _cards().get().message


# ── 6. Fora da janela de 24 horas ─────────────────────────────────────


def test_6_outside_the_24h_window_nothing_is_promised(conversation, outbox):  # noqa: F811
    _closed_until(3)

    result = _ask_parking(conversation)

    assert not result.handoff
    reply = outbox.sent[-1]
    assert "Quem confirma isso é a equipe, que volta " in reply
    assert reply.rstrip().endswith("Se puder, me escreva de novo nesse horário.")
    assert "te respondo" not in reply and "perguntei" not in reply
    assert _record(conversation) is None, "nada volta pela conversa: nenhuma verificação abre"
    assert not _cards().exists()
    parts = conversation.flags["dialogue"]["parts"]
    assert [row["state"] for row in parts] == ["answered", "unanswered"], "a parte não fica em espera"


# ── 7. Turno revogado ─────────────────────────────────────────────────


def test_7_a_revoked_turn_does_not_write_verifying(conversation, outbox, monkeypatch):  # noqa: F811
    original = intents.run

    def revoked_after_reading(conversation, **kwargs):  # noqa: F811
        outcome = original(conversation, **kwargs)
        # Entrada nova (ou a equipe assumindo) no meio do turno: o fence anda.
        Conversation.objects.filter(pk=conversation.pk).update(turn_fence=F("turn_fence") + 1)
        return outcome

    monkeypatch.setattr(intents, "run", revoked_after_reading)
    result = _ask_parking(conversation)

    assert result.fallback == "revoked"
    assert _record(conversation) is None
    assert not _cards().exists()
    assert not outbox.sent


# ── O cartão no sino: endpoints e ações ───────────────────────────────


@pytest.fixture
def gestor(db):
    user = User.objects.create_user("gestor-verificar", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"
        )
    )
    return user


def test_the_bell_card_carries_the_answer_and_take_over_actions(conversation, outbox, client, gestor):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    client.force_login(gestor)

    payload = client.get("/api/v1/backstage/alerts/?scope=orders&surface=orders").json()

    row = next(alert for alert in payload["alerts"] if alert["pk"] == card.pk)
    kinds = {action["kind"]: action for action in row["actions"]}
    assert kinds["answer_concierge_verification"]["href"] == (
        f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/answer/"
    )
    assert kinds["take_over_conversation"]["href"].endswith("/concierge-verification/take-over/")
    assert "estacionamento" in row["message"] and "Dedupe" not in row["message"]
    assert row["subject"] == "Ana espera a resposta da equipe", "quem espera vai no título"
    assert row["origin_label"] == "WhatsApp"
    assert row["deadline_kind"] == "house", "a promessa vencida fica na tela"


def test_the_answer_endpoint_sends_and_reports_errors_in_the_house_dialect(conversation, outbox, client, gestor):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    client.force_login(gestor)
    url = f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/answer/"

    empty = client.post(url, {"text": ""}, content_type="application/json")
    assert empty.status_code == 422 and empty.json()["field"] == "text"
    assert empty.json()["error"]["code"] == "empty_answer"

    sent = client.post(url, {"text": "Temos sim, duas vagas."}, content_type="application/json")
    assert sent.status_code == 200 and sent.json()["ok"] is True
    assert outbox.sent[-1] == "A equipe confirmou: Temos sim, duas vagas."

    again = client.post(url, {"text": "de novo"}, content_type="application/json")
    assert again.status_code == 404, "o cartão já fechou"


def test_the_take_over_endpoint_hands_the_conversation_to_the_team(conversation, outbox, client, gestor):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    client.force_login(gestor)

    response = client.post(f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/take-over/")

    assert response.status_code == 200 and response.json()["ok"] is True
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF


def test_an_operator_without_the_orders_audience_cannot_answer(conversation, outbox, client):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    bare = User.objects.create_user("sem-pedidos", password="pw", is_staff=True)
    client.force_login(bare)

    response = client.post(
        f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/answer/",
        {"text": "Temos sim."},
        content_type="application/json",
    )

    assert response.status_code in {403, 404}
    assert _record(conversation)["status"] == verification.OPEN


# ── Copy e configuração ───────────────────────────────────────────────


def test_default_copy_of_the_verification_obeys_the_house_rules():
    from shopman.shop.omotenashi.copy import resolve_copy

    for key in verification.COPY_KEYS:
        message = resolve_copy(key, moment="*").message
        assert message and "—" not in message and "–" not in message, key
        receipts = frozenset({house_rules.VERIFY, house_rules.TEAM_NOTIFIED})
        if key == verification.HANDOFF_COPY_KEY:
            receipts |= {house_rules.HANDOFF}
        filled = message.replace("{minutes}", "10").replace("{when}", "amanhã às 7h10").replace(
            "{part}", "estacionamento").replace("{answer}", "temos sim.")
        review = house_rules.review([filled], house_rules.ReplyContext(receipts=receipts))
        assert not review.held, (key, review.held)
        assert review.texts == [filled], (key, review.violations)


@pytest.mark.parametrize(
    ("nudge", "handoff"),
    [(0, 30), (10, 10), (30, 10), (True, 30), (10, "30")],
)
def test_the_deadlines_reject_what_does_not_make_sense(nudge, handoff):
    config = ChannelConfig.from_dict({"confirmation": {"concierge_verify_nudge_minutes": nudge,
                                                       "concierge_verify_handoff_minutes": handoff}})
    with pytest.raises(ValueError):
        config.validate()


def test_the_deadlines_default_to_the_owners_decision():
    config = ChannelConfig()
    assert (config.confirmation.concierge_verify_nudge_minutes, config.confirmation.concierge_verify_handoff_minutes) == (10, 30)
    config.validate()


@pytest.mark.parametrize(
    ("text", "expected"),
    [("e aí?", True), ("E aí", True), ("alguma novidade?", True), ("conseguiu ver?", True),
     ("já confirmaram?", True), ("você não me respondeu", True), ("tem croissant?", False),
     ("e aí, tem croissant?", False), ("obrigada", False)],
)
def test_asks_for_news(text, expected):
    assert verification.asks_for_news(text) is expected


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
def test_the_memory_sees_the_open_verification_as_verifying(conversation, outbox):  # noqa: F811
    from shopman.storefront.concierge import dialogue

    _ask_parking(conversation)
    conversation.refresh_from_db()

    memory = dialogue.for_turn(conversation)

    assert memory.state["verifying"]["questions"] == [q["text"] for q in _record(conversation)["questions"]]
    assert "verifying" not in (conversation.flags or {}).get(dialogue.FLAG_KEY, {}), (
        "o estado da espera não é gravado na memória: vem da verificação"
    )


# ── Fora do turno: a porta de equipe do framework (N7) ────────────────


def test_open_for_opens_the_verification_outside_a_turn_with_the_card(conversation, outbox):  # noqa: F811
    record = verification.open_for(conversation, "vocês fazem bolo de casamento?", actor="framework-n7")

    assert record and record["status"] == verification.OPEN and record["_new"]
    assert record["opened_by"] == "framework-n7"
    assert [q["text"] for q in record["questions"]] == ["vocês fazem bolo de casamento?"]
    stored = _record(conversation)
    assert stored["opened_by"] == "framework-n7" and stored["promise"]["kind"] in {verification.NOW, verification.LATER}
    assert _cards().count() == 1
    assert outbox.sent == []  # quem fala com o cliente é quem chamou

    again = verification.open_for(conversation, "e entregam em Cambé?")
    assert again and not again["_new"]
    assert len(_record(conversation)["questions"]) == 2 and _cards().count() == 1


def test_open_for_does_nothing_without_a_question_or_with_the_team(conversation):  # noqa: F811
    assert verification.open_for(conversation, "   ") is None
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.HANDOFF)
    assert verification.open_for(conversation, "tem estacionamento?") is None
    assert _record(conversation) is None and not _cards().exists()
