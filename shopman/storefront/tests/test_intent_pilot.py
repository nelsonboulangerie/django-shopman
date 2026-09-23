"""Piloto de intenções: vocabulário, sorteio, rotulagem no Admin e o placar.

Nenhum teste chama rede: LLM e Jev recebem transporte falso, embeddings usam
vetores de brinquedo. O que se fixa é a disciplina do piloto — texto de cliente
sempre redigido, provedor externo só com permissão escrita, várias intenções
por mensagem — e a conta do placar.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage, Shop
from shopman.shop.services.ai_pricing import Price
from shopman.storefront.concierge.intent_benchmark import (
    Category,
    ContenderNotConfigured,
    ContenderResponseError,
    EmbeddingContender,
    JevContender,
    LLMContender,
    Prediction,
    RegexContender,
    Sample,
    Scoreboard,
    gold_samples,
    load_categories,
    parse_jev_boolean,
    run,
)
from shopman.storefront.models import IntentCategory, MessageIntentSample, SampleStatus


@pytest.fixture
def categories(db):
    call_command("setup_intent_categories")
    return {category.ref: category for category in IntentCategory.objects.all()}


def _conversation():
    conversation = Conversation.objects.create(phone="+5543999990000")
    ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="bakery-primary",
        transport_channel="whatsapp",
        subject=f"sub-{conversation.pk}",
        connection_key="manychat-whatsapp-primary",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance="transport_subject",
    )
    return conversation


def _inbound(text, conversation=None):
    conversation = conversation or _conversation()
    return ConversationMessage.objects.create(
        conversation=conversation,
        binding=conversation.transport_bindings.first(),
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text=text,
        content=[{"type": "text", "text": text}],
    )


def _labeled(text, *refs, categories):
    sample = MessageIntentSample.objects.create(message=_inbound(text), status=SampleStatus.LABELED)
    sample.intents.set([categories[ref] for ref in refs])
    return sample


# ── Vocabulário e sorteio ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_setup_creates_the_proposed_vocabulary_and_never_overwrites(categories):
    assert list(categories) == [
        "order", "product_question", "hours_delivery", "order_status",
        "complaint", "allergy", "special_order", "human",
    ]
    assert {ref for ref, c in categories.items() if c.sensitive} == {"complaint", "allergy", "human"}
    IntentCategory.objects.filter(ref="order").update(name="Compra")
    call_command("setup_intent_categories")
    assert IntentCategory.objects.get(ref="order").name == "Compra"
    assert IntentCategory.objects.count() == 8


@pytest.mark.django_db
def test_sample_picks_only_customer_text_once():
    conversation = _conversation()
    wanted = _inbound("Vocês abrem domingo?", conversation)
    _inbound("", conversation)  # sem texto (mídia)
    ConversationMessage.objects.create(
        conversation=conversation, binding=conversation.transport_bindings.first(), role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY, text="Abrimos sim!",
    )
    call_command("sample_intent_messages", limit=10)
    assert list(MessageIntentSample.objects.values_list("message_id", flat=True)) == [wanted.pk]
    call_command("sample_intent_messages", limit=10)  # de novo: nada duplicado
    assert MessageIntentSample.objects.count() == 1


@pytest.mark.django_db
def test_sample_follows_the_message_when_it_is_erased():
    sample = MessageIntentSample.objects.create(message=_inbound("Quero um bolo"))
    sample.message.delete()  # retenção ou pedido do titular
    assert not MessageIntentSample.objects.exists()


@pytest.mark.django_db
def test_labelers_and_classifiers_see_the_redacted_text():
    sample = MessageIntentSample.objects.create(
        message=_inbound("Meu CPF é 123.456.789-09, sou alérgica a nozes e quero 2 croissants")
    )
    text = sample.redacted_text()
    assert "123.456.789-09" not in text and "nozes" not in text
    assert "[alergia: detalhe omitido]" in text  # a intenção continua legível


# ── Rotulagem no Admin ──────────────────────────────────────────────────────


@pytest.fixture
def admin_client(db):
    Shop.objects.create(name="Test Shop", brand_name="Test", short_name="TS", primary_color="#C5A55A", default_ddd="43")
    user = User.objects.create_superuser("admin", "admin@test.com", "pass")
    client = Client()
    client.login(username="admin", password="pass")
    client.user = user
    return client


@pytest.mark.django_db
def test_labeling_several_intents_signs_and_moves_to_the_next(admin_client, categories):
    first = MessageIntentSample.objects.create(message=_inbound("Quero 2 croissants, vocês abrem domingo?"))
    second = MessageIntentSample.objects.create(message=_inbound("Cadê meu pedido?"))
    url = reverse("admin:storefront_messageintentsample_change", args=[first.pk])

    page = admin_client.get(url)
    assert page.status_code == 200
    assert "Quero 2 croissants" in page.content.decode()

    response = admin_client.post(url, {
        "intents": [categories["order"].pk, categories["hours_delivery"].pk],
        "status": SampleStatus.LABELED,
        "note": "",
    })
    assert response.status_code == 302
    assert response["Location"] == reverse("admin:storefront_messageintentsample_change", args=[second.pk])
    first.refresh_from_db()
    assert set(first.intents.values_list("ref", flat=True)) == {"order", "hours_delivery"}
    assert first.labeled_by == admin_client.user and first.labeled_at is not None


@pytest.mark.django_db
def test_label_queue_lists_and_skips(admin_client, categories):
    sample = MessageIntentSample.objects.create(message=_inbound("kkkkk"))
    changelist = reverse("admin:storefront_messageintentsample_changelist")
    assert admin_client.get(changelist).status_code == 200
    admin_client.post(changelist, {"action": "skip_selected", "_selected_action": [sample.pk]})
    sample.refresh_from_db()
    assert sample.status == SampleStatus.SKIPPED
    assert admin_client.get(reverse("admin:storefront_intentcategory_changelist")).status_code == 200


# ── Concorrentes ────────────────────────────────────────────────────────────

CATS = [
    Category("order", "Pedido", "quer comprar", False),
    Category("hours_delivery", "Horário", "horário ou entrega", False),
    Category("allergy", "Alergia", "alergia", True),
    Category("human", "Pessoa", "falar com atendente", True),
]


def test_regex_is_single_label_and_speaks_the_pilot_vocabulary():
    sample = Sample(1, "Quero falar com um atendente, sou alérgico a glúten", frozenset({"human", "allergy"}))
    prediction = RegexContender().predict(sample, CATS)
    assert prediction.intents == {"human": 1.0}  # primeira causa que casa, uma só


_VECTORS = {
    "pedido: quer comprar": [1.0, 0.0, 0.0],
    "horário: horário ou entrega": [0.0, 1.0, 0.0],
    "alergia: alergia": [0.0, 0.0, 1.0],
    "pessoa: falar com atendente": [-1.0, 0.0, 0.0],
    "quero pão, abre domingo?": [0.7, 0.7, 0.0],
}


def test_embedding_marks_every_intent_above_the_cut():
    contender = EmbeddingContender(embed=lambda texts: [_VECTORS[t] for t in texts], min_similarity=0.5)
    contender.prepare(CATS)
    prediction = contender.predict(Sample(1, "Quero pão, abre domingo?", frozenset()), CATS)
    assert set(prediction.intents) == {"order", "hours_delivery"}


def test_external_contenders_need_written_approval(settings):
    settings.SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED = False
    settings.AI_ASSIST_API_KEY = "k"
    settings.JEV_API_KEY = "k"
    with pytest.raises(ContenderNotConfigured, match="SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED"):
        LLMContender(client=object())
    with pytest.raises(ContenderNotConfigured, match="SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED"):
        JevContender(session=object())


class _FakeClient:
    def __init__(self, text):
        self.calls = []
        message = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=500, output_tokens=30),
            stop_reason="end_turn",
        )

        def create(**kwargs):
            self.calls.append(kwargs)
            return message

        self.messages = SimpleNamespace(create=create)


def test_llm_returns_several_intents_and_drops_the_unsure(settings):
    settings.SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED = True
    client = _FakeClient(
        '{"intents": [{"ref": "order", "confidence": 0.9}, {"ref": "hours_delivery", "confidence": 0.8},'
        ' {"ref": "human", "confidence": 0.2}]}'
    )
    contender = LLMContender(model="claude-haiku-4-5", client=client)
    prediction = contender.predict(Sample(1, "Quero pão, abre domingo?", frozenset()), CATS)
    assert prediction.intents == {"order": 0.9, "hours_delivery": 0.8}
    assert (prediction.input_tokens, prediction.output_tokens) == (500, 30)
    assert "<<<\nQuero pão, abre domingo?\n>>>" in client.calls[0]["messages"][0]["content"]


def test_llm_intent_outside_the_list_is_an_error(settings):
    settings.SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED = True
    contender = LLMContender(client=_FakeClient('{"intents": [{"ref": "elogio", "confidence": 0.9}]}'))
    with pytest.raises(ContenderResponseError):
        contender.predict(Sample(1, "Amei!", frozenset()), CATS)


class _FakeSession:
    def __init__(self, payload):
        self.payload, self.sent = payload, []

    def post(self, url, *, json, headers, timeout):
        self.sent.append(json)
        return SimpleNamespace(status_code=200, text="", json=lambda: self.payload)


def test_jev_asks_one_yes_no_per_intent_in_one_call(settings):
    settings.SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED = True
    settings.JEV_API_KEY = "k"
    session = _FakeSession({
        "answers": {
            "order": {"answer": True, "confidence": 0.95},
            "hours_delivery": {"answer": "yes", "confidence": 0.7},
            "allergy": {"answer": False, "confidence": 0.9},
            "human": {"value": "no", "probabilities": {"yes": 0.1, "no": 0.9}},
        },
        "usage": {"input_tokens": 90},
    })
    prediction = JevContender(session=session).predict(Sample(1, "Quero pão, abre domingo?", frozenset()), CATS)
    assert set(session.sent[0]["questions"]) == {"order", "hours_delivery", "allergy", "human"}
    assert session.sent[0]["state"] == {"customer_message": "Quero pão, abre domingo?"}
    assert set(prediction.intents) == {"order", "hours_delivery"}
    assert prediction.input_tokens == 90


def test_jev_boolean_parser_names_unknown_shapes():
    assert parse_jev_boolean({"answers": {"q": {"answer": False, "confidence": 0.8}}}, question="q") == pytest.approx(0.2)
    with pytest.raises(ContenderResponseError, match="Chaves recebidas"):
        parse_jev_boolean({"output": "?"}, question="q")


# ── Placar ──────────────────────────────────────────────────────────────────


def test_scoreboard_counts_sets_multi_intent_and_sensitive_recall():
    board = Scoreboard(contender="x", price=Price())
    board.add(Sample(1, "", frozenset({"order", "hours_delivery"})), Prediction({"order": 1, "hours_delivery": 1}))
    board.add(Sample(2, "", frozenset({"allergy", "order"})), Prediction({"order": 1}))
    board.add(Sample(3, "", frozenset()), Prediction({"human": 1}))
    board.add(Sample(4, "", frozenset({"human"})), Prediction({}, error="quebrou"))
    assert (board.total, board.exact, board.multi_total, board.multi_exact, board.errors) == (4, 1, 2, 1, 1)
    precision, recall, f1 = board.micro()
    assert precision == pytest.approx(3 / 4) and recall == pytest.approx(3 / 5)
    assert f1 == pytest.approx(2 * 0.75 * 0.6 / 1.35)
    assert board.recall(["allergy", "human"]) == 0.0


@pytest.mark.django_db
def test_gold_ignores_pending_and_inactive_intents(categories):
    _labeled("Quero pão e sou celíaca", "order", "allergy", categories=categories)
    MessageIntentSample.objects.create(message=_inbound("ainda não rotulada"))
    IntentCategory.objects.filter(ref="allergy").update(active=False)
    samples = gold_samples()
    assert [sample.gold for sample in samples] == [frozenset({"order"})]
    assert "allergy" not in {c.ref for c in load_categories()}


@pytest.mark.django_db
def test_command_reports_without_external_contenders_and_csv_has_no_text(categories, settings, tmp_path, capsys):
    settings.SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED = False
    with pytest.raises(CommandError, match="Gabarito vazio"):
        call_command("benchmark_intent_classifiers", contender=["regex"])
    _labeled("Quero falar com um atendente e fazer um pedido", "human", "order", categories=categories)
    _labeled("Vocês abrem domingo?", "hours_delivery", categories=categories)
    out_csv = tmp_path / "intencoes.csv"
    call_command("benchmark_intent_classifiers", csv=str(out_csv))
    out = capsys.readouterr().out
    assert "llm: fora do placar" in out and "jev: fora do placar" in out
    assert "2 mensagens rotuladas (1 com 2+ intenções" in out
    rows = out_csv.read_text(encoding="utf-8")
    assert "regex" in rows and "atendente" not in rows  # sem texto de cliente


def test_run_survives_a_failing_contender():
    class Broken:
        name = "broken"

        def predict(self, sample, categories):
            raise TimeoutError("sem rede")

    boards = run([Sample(1, "oi", frozenset({"order"}))], CATS, [Broken()], prices={})
    assert boards[0].errors == 1 and "TimeoutError" in boards[0].rows[0][4]
