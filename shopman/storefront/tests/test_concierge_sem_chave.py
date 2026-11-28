"""WP-03 do plano da Concierge: atende sem chave e só manda texto redigido.

Dois contratos, os dois de /privacidade e da operação:

- **Sem chave, ela existe.** Sem ``AIConnection`` (ou com o freio cortando), o turno
  vai pelo caminho sem modelo: porteiro, divisão local, executores, uma mensagem.
- **O leitor de IA só recebe texto redigido.** A frase pública aprovada pelo dono
  (16/11, PR #2520): "Nome, documento, e-mail, telefone, endereço, pagamento, alergia
  ou doença que você escrever não são enviados: a loja apaga tudo isso do texto antes."
  Vale para a leitura de partes (``intents``), o Jev (``decision``) e o pré-rótulo
  (``labeling``). O executor de cada parte trabalha sobre o texto ORIGINAL.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.test import override_settings

from shopman.shop.models import ConversationMessage
from shopman.shop.tests.ai_support import configure_ai
from shopman.storefront.concierge import intents, observation_privacy, service, triage
from shopman.storefront.concierge.intent_benchmark import Prediction
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    CONCIERGE_SETTINGS,
    SUBJECT,
    _binding,
    _receive,
    alpha_menu,
    conversation,
    customer,
    house_notice,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act

CUSTOMER_NAME = "Maria Souza"

#: (fala, trechos que não podem sair). Uma linha por categoria da frase pública.
FALAS = [
    ("Oi, aqui é a Maria Souza, tem croissant?", ("Maria", "Souza")),
    ("meu nome é joana prado, tem croissant?", ("joana",)),
    ("Sou a Helena Duarte, tem croissant?", ("Helena", "Duarte")),
    ("Maria aqui, tem croissant?", ("Maria",)),
    ("tem croissant? obrigada, Beatriz Lima", ("Beatriz", "Lima")),
    ("meu CPF é 123.456.789-09, tem croissant?", ("123.456.789-09",)),
    ("me liga no (43) 99876-5432, tem croissant?", ("99876-5432",)),
    ("manda pra maria@exemplo.com, tem croissant?", ("maria@exemplo.com",)),
    ("paga no cartão 4111 1111 1111 1111, tem croissant?", ("4111",)),
    ("entrega na Rua das Flores, 120? tem croissant?", ("Rua das Flores",)),
    ("sou alérgica a castanha, tem croissant?", ("castanha",)),
    ("tenho diabetes, tem croissant?", ("diabetes",)),
    ("minha filha de 6 anos adora, tem croissant?", ("6 anos",)),
]


@pytest.fixture(autouse=True)
def reading_route(monkeypatch):
    """O modelo da rota ``intents`` sem banco: o pedido da leitura sai igual."""
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")


class JevFalso:
    """O Jev de mentira: guarda o texto que receberia."""

    def __init__(self):
        self.sent: list[str] = []

    def scores(self, sample, categories):
        self.sent.append(sample.text)
        return Prediction(intents={"product_question": 0.9})


def _reading_sent(text: str, note: str = "") -> str:
    reader = ReaderClient([_act("product_question", "tem croissant?", "croissant")])
    intents.read_with_model(text, memory_note=note, client=reader)
    assert reader.requests
    return str(reader.requests[0]["messages"])


def _assert_without(pieces, sent: str, who: str) -> None:
    for piece in pieces:
        assert piece.casefold() not in sent.casefold(), f"{who} recebeu {piece!r}: {sent}"


# ── (a) Sem chave, ela responde ───────────────────────────────────────


@pytest.fixture
def without_ai(monkeypatch):
    """Nenhuma conexão de IA, e qualquer tentativa de criar cliente de modelo reprova."""
    configure_ai("")

    def no_client(*args, **kwargs):
        raise AssertionError("cliente de modelo criado num turno sem conexão de IA")

    monkeypatch.setattr("shopman.shop.ai.anthropic_client", no_client)
    monkeypatch.setattr("shopman.storefront.concierge.intent_benchmark.JevContender", no_client)


@pytest.mark.django_db
def test_without_ai_connection_the_concierge_is_not_disabled(conversation, without_ai):  # noqa: F811 (fixtures)
    assert service.disabled_reason() == ""


@pytest.mark.django_db
def test_without_ai_connection_a_whole_turn_answers_courtesy_and_product(
    conversation, outbox, without_ai  # noqa: F811 (fixtures)
):
    """Sem chave, a leitura em partes responde sem modelo."""
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "bom dia", "sem-chave-1")
        first = service.run_turn(conversation.pk, _binding(conversation).pk)
        _receive(conversation, "tem pão francês?", "sem-chave-2")
        second = service.run_turn(conversation.pk, _binding(conversation).pk)

    assert not first.handoff and not second.handoff
    assert first.fallback == "" and second.fallback == ""
    assert len(outbox.sent) == 2
    assert "bom dia" in outbox.sent[0].casefold()
    assert "Pão Francês" in outbox.sent[1]
    stamps = ConversationMessage.objects.filter(conversation=conversation, kind="reply")
    assert all(not (stamp.usage or {}).get("calls") for stamp in stamps)


@pytest.mark.django_db
def test_the_brake_cutting_the_reading_mid_turn_falls_to_the_path_without_model(
    conversation, outbox, monkeypatch  # noqa: F811 (fixtures)
):
    """Com chave, mas o freio corta (``AINotConfigured``) quando a leitura vai chamar o modelo."""
    from shopman.shop.ai import AINotConfigured

    def braked(*args, **kwargs):
        raise AINotConfigured("freio: teto do dia")

    monkeypatch.setattr("shopman.shop.ai.anthropic_client", braked)
    _receive(conversation, "tem pão francês?", "freio-1")
    result = service.run_turn(conversation.pk, _binding(conversation).pk)

    assert not result.handoff and result.fallback == ""
    assert "Pão Francês" in outbox.sent[-1]


# ── (b) O leitor de IA só recebe texto redigido ───────────────────────


@pytest.mark.parametrize(("text", "pieces"), FALAS)
def test_the_reading_never_receives_personal_data(text, pieces):
    with observation_privacy.known_names(CUSTOMER_NAME):
        sent = _reading_sent(text)
    assert "croissant" in sent
    _assert_without((*pieces, "Maria", "Souza"), sent, "A leitura de partes")


@pytest.mark.parametrize(("text", "pieces"), FALAS)
def test_the_jev_never_receives_personal_data(text, pieces):
    jev = JevFalso()
    with observation_privacy.known_names(CUSTOMER_NAME):
        triage.jev_scores(text, contender=jev)
    assert jev.sent and "croissant" in jev.sent[0]
    _assert_without((*pieces, "Maria", "Souza"), jev.sent[0], "O Jev")


def test_the_known_name_is_released_after_the_block():
    with observation_privacy.known_names(CUSTOMER_NAME):
        pass
    assert "Maria" in observation_privacy.redact_observation_text("Maria aqui").text


@pytest.mark.django_db
def test_a_whole_turn_sends_neither_the_name_nor_personal_data_to_jev_or_reading(
    conversation, outbox  # noqa: F811 (fixtures)
):
    """O ``customer_name`` da conversa entra no redator pelo turno (``service.run_turn``)."""
    conversation.customer_name = CUSTOMER_NAME
    conversation.save(update_fields=["customer_name"])
    jev = JevFalso()
    reader = ReaderClient([
        _act("product_question", "tem pão francês?", "pão francês"),
        _act("house_info", "vocês aceitam vale refeição?"),
    ])
    text = "Maria aqui, meu CPF é 123.456.789-09. tem pão francês? e vocês aceitam vale refeição?"
    _receive(conversation, text, "nome-no-turno")
    with override_settings(
        SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "triage_with_model": True}
    ):
        service.run_turn(conversation.pk, _binding(conversation).pk, triage_client=jev, intents_client=reader)

    assert jev.sent and reader.requests
    sent = [*jev.sent, *(str(request["messages"]) for request in reader.requests)]
    for each in sent:
        _assert_without(("Maria", "Souza", "123.456.789-09"), each, "O leitor de IA")
    assert "Pão Francês" in outbox.sent[-1]
    # O nome não ficou preso no redator depois do turno.
    assert "Maria" in observation_privacy.redact_observation_text("Maria aqui").text


@pytest.mark.django_db
def test_the_labeling_sample_drops_the_name_the_conversation_knows(conversation):  # noqa: F811 (fixtures)
    from shopman.storefront.models import MessageIntentSample

    conversation.customer_name = CUSTOMER_NAME
    conversation.save(update_fields=["customer_name"])
    _receive(conversation, "Maria aqui, tem croissant?", "rotulo-1")
    message = ConversationMessage.objects.filter(conversation=conversation, kind="inbound").latest("pk")
    sample = MessageIntentSample.objects.create(message=message)
    assert sample.redacted_text() == "[nome omitido] aqui, tem croissant?"


# ── (c) A nota de estado não leva pedido nem nome ─────────────────────


def test_the_state_note_does_not_carry_the_order_number_nor_the_name():
    facts = SimpleNamespace(
        open_order=SimpleNamespace(label="pedido ABC123, retirada hoje", status="new"),
        recent_order=SimpleNamespace(label="pedido XYZ987, entrega ontem", status="completed"),
    )
    memory = SimpleNamespace(state={}, facts=facts)
    note = intents.reading_note(memory)
    assert "ABC123" not in note and "XYZ987" not in note
    assert "pedido em aberto" in note

    with observation_privacy.known_names(CUSTOMER_NAME):
        sent = _reading_sent("tem croissant?", note="Pedido aberto do cliente: pedido ABC123 (novo). Maria Souza")
    _assert_without(("ABC123", "Maria", "Souza"), sent, "A nota da leitura")


# ── (d) O executor lê o texto original ────────────────────────────────


def test_the_span_that_comes_back_is_the_original_text():
    original = "tem croissant? minha filha é alérgica a leite. Maria aqui, queria 2 baguetes"
    assert intents.original_span("minha filha é [alergia: detalhe omitido]", original) == (
        "minha filha é alérgica a leite"
    )
    assert intents.original_span("[nome omitido] aqui, queria 2 baguetes", original) == (
        "Maria aqui, queria 2 baguetes"
    )
    assert intents.original_span("tem croissant?", original) == "tem croissant?"


@pytest.mark.django_db
def test_the_allergy_warning_still_reads_the_original_allergen(conversation, outbox, house_notice):  # noqa: F811 (fixtures)
    """A leitura vê "[alergia: detalhe omitido]"; o aviso de alérgenos sai certo mesmo assim.

    Com o trecho redigido, o executor perguntaria "a que é a alergia?"; com o original,
    responde com os alérgenos declarados do croissant e o aviso da casa.
    """
    reader = ReaderClient([
        _act("product_question", "tem croissant?", "croissant"),
        _act("allergy", "minha filha é [alergia: detalhe omitido]"),
    ])
    text = "tem croissant? minha filha é alérgica a leite"
    _receive(conversation, text, "alergia-original")
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        service.run_turn(conversation.pk, _binding(conversation).pk, intents_client=reader)

    _assert_without(("leite",), str(reader.requests[0]["messages"]), "A leitura de partes")
    from shopman.storefront.concierge import allergens
    from shopman.storefront.tests.test_concierge_engine import CHANNEL

    # O trecho redigido não diz a que é a alergia: sozinho, levaria à pergunta.
    assert allergens.decision("minha filha é [alergia: detalhe omitido]", channel_ref=CHANNEL) == (
        allergens.ASK_WHICH
    )
    reply = outbox.sent[-1]
    assert house_notice in reply
    assert "a que é a alergia" not in reply
    assert "já chamei a equipe" not in reply
    found = intents.plan(
        text, rules_intent=triage.classify_rules(text)[0], rules_source="rules",
        client=ReaderClient([_act("allergy", "minha filha é [alergia: detalhe omitido]")]),
    )
    allergy = [act for act in found.acts if act.act == "allergy"]
    assert allergy and all("leite" in act.span for act in allergy)


# ── (e) Nome de produto não é nome de gente ───────────────────────────


@pytest.mark.parametrize("text", ["tem pão Maria?", "bolo de rolo tem hoje?", "aqui é a padaria?", "sou cliente"])
def test_product_names_and_plain_phrases_are_not_erased(text):
    with observation_privacy.known_names(CUSTOMER_NAME):
        redacted = observation_privacy.redact_observation_text(text)
    assert redacted.text == text
    assert "name" not in redacted.categories
