"""Promover a resposta da equipe a pergunta frequente (WP-15).

O "Pronto quando" do plano, item por item: rascunho não publicado com a origem; texto
redigido e no limite; sem IA, os textos originais; promover duas vezes, um rascunho só;
a Concierge só usa depois de publicada. E o endpoint do cartão respondido.
"""

from __future__ import annotations

import json

import pytest

from shopman.shop.models import FAQEntry, Shop
from shopman.storefront.concierge import faq_promotion, verification
from shopman.storefront.tests.test_concierge_verification import (  # noqa: F401 (fixtures)
    _ask_parking,
    _cards,
    conversation,
    customer,
    gestor,
    outbox,
    plural,
    surface,
)

pytestmark = pytest.mark.django_db

ANSWER = "Temos estacionamento na rua de trás, com vagas para clientes."


def _answered(conversation, answer=ANSWER):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    result = verification.answer(card.pk, answer, actor="ana")
    assert result.ok, result
    return card


def _without_ai(monkeypatch):
    from shopman.shop.services import copy_assist

    def refuse(*args, **kwargs):
        raise copy_assist.CopyAssistNotConfigured("sem conexão")

    monkeypatch.setattr(copy_assist, "suggest", refuse)


def _ai_says(monkeypatch, payload: dict, calls: list | None = None):
    from shopman.shop.services import copy_assist

    def fake(prompt, **kwargs):
        if calls is not None:
            calls.append((prompt, kwargs))
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(copy_assist, "suggest", fake)


def test_1_promoting_creates_an_unpublished_draft_with_its_origin(conversation, outbox, monkeypatch):  # noqa: F811
    card = _answered(conversation)
    calls: list = []
    _ai_says(monkeypatch, {
        "question": "Vocês têm estacionamento?",
        "answer": "Sim, temos vagas para clientes na rua de trás.",
        "search_terms": "estacionamento, vaga, carro",
    }, calls)

    result = faq_promotion.promote(card.pk, actor="ana")

    assert result.ok and not result.code
    entry = FAQEntry.objects.get(ref=result.detail)
    assert entry.is_published is False
    assert (entry.question, entry.search_terms) == ("Vocês têm estacionamento?", "estacionamento, vaga, carro")
    from shopman.shop.concierge_verification import origin_of

    assert origin_of(entry.ref) == (conversation.pk, _record_id(conversation))
    assert "Promovida da verificação" in entry.history.first().history_change_reason
    assert calls and calls[0][1]["purpose"] == "concierge", "texto de cliente só pela conexão liberada para ele"


def test_2_the_suggestion_never_carries_contacts_and_respects_the_limit(conversation, outbox, monkeypatch):  # noqa: F811
    card = _answered(conversation)
    calls: list = []
    _ai_says(monkeypatch, {
        "question": "Tem estacionamento? Liga no (43) 99876-5432",
        "answer": "Sim. " + "Vagas na rua de trás. " * 150 + " Escreva para ana@exemplo.com.br",
        "search_terms": "estacionamento",
    }, calls)

    entry = FAQEntry.objects.get(ref=faq_promotion.promote(card.pk, actor="ana").detail)

    sent_prompt = calls[0][0]
    assert "99876" not in sent_prompt, "a pergunta do cliente vai redigida (tinha o telefone dele)"
    for text in (entry.question, entry.answer, entry.search_terms):
        assert "99876" not in text and "ana@exemplo" not in text
    assert len(entry.answer) <= faq_promotion.ANSWER_CHARS
    assert len(entry.question) <= faq_promotion.QUESTION_CHARS


def test_3_without_ai_the_draft_keeps_the_original_texts(conversation, outbox, monkeypatch):  # noqa: F811
    card = _answered(conversation)
    _without_ai(monkeypatch)

    entry = FAQEntry.objects.get(ref=faq_promotion.promote(card.pk, actor="ana").detail)

    assert entry.answer == ANSWER
    assert "estacionamento" in entry.question and "99876" not in entry.question
    assert entry.search_terms == ""
    assert "sem IA" in entry.history.first().history_change_reason


def test_4_promoting_twice_keeps_one_draft(conversation, outbox, monkeypatch):  # noqa: F811
    card = _answered(conversation)
    _without_ai(monkeypatch)

    first = faq_promotion.promote(card.pk, actor="ana")
    again = faq_promotion.promote(card.pk, actor="bia")

    assert again.ok and again.code == "already_promoted" and again.detail == first.detail
    assert FAQEntry.objects.filter(ref=first.detail).count() == 1


def test_5_the_concierge_only_uses_it_after_it_is_published(conversation, outbox, monkeypatch):  # noqa: F811
    from shopman.storefront.presentation.public_information import search_public_faq

    card = _answered(conversation)
    _ai_says(monkeypatch, {
        "question": "Vocês têm estacionamento?",
        "answer": "Sim, temos vagas para clientes na rua de trás.",
        "search_terms": "estacionamento, vaga",
    })
    entry = FAQEntry.objects.get(ref=faq_promotion.promote(card.pk, actor="ana").detail)
    shop = Shop.load()

    def found() -> bool:
        return any(a.ref == f"curated-{entry.ref}" for a in search_public_faq("estacionamento", channel_ref="whatsapp", shop=shop))

    assert not found(), "rascunho não vale para o próximo cliente"
    entry.is_published = True
    entry.save()
    assert found()


def test_an_open_or_taken_over_question_is_not_promoted(conversation, outbox):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()

    assert faq_promotion.promote(card.pk, actor="ana").code == "not_answered"
    assert not FAQEntry.objects.exists()


def test_an_answer_about_today_is_promoted_with_the_warning(conversation, outbox, monkeypatch):  # noqa: F811
    card = _answered(conversation, answer="Hoje o estacionamento da rua de trás está fechado.")
    _without_ai(monkeypatch)

    result = faq_promotion.promote(card.pk, actor="ana")

    assert result.ok and result.sent_text == faq_promotion.DATED_WARNING


def test_the_endpoint_promotes_the_answered_card(conversation, outbox, client, gestor, monkeypatch, settings):  # noqa: F811
    settings.SHOPMAN_ADMIN_HOST = "admin.exemplo.com.br"
    _ask_parking(conversation)
    card = _cards().get()
    client.force_login(gestor)
    answered = client.post(
        f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/answer/", {"text": ANSWER},
        content_type="application/json",
    ).json()
    assert answered["promote_href"] == f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/promote-faq/"
    _without_ai(monkeypatch)

    body = client.post(answered["promote_href"]).json()

    entry = FAQEntry.objects.get()
    assert body == {
        "ok": True, "pk": card.pk, "already": False, "warning": "",
        "admin_url": f"https://admin.exemplo.com.br/admin/shop/faqentry/{entry.pk}/change/",
    }
    assert client.post(answered["promote_href"]).json()["already"] is True


def test_the_endpoint_refuses_a_question_still_open(conversation, outbox, client, gestor):  # noqa: F811
    _ask_parking(conversation)
    card = _cards().get()
    client.force_login(gestor)

    refused = client.post(f"/api/v1/backstage/alerts/{card.pk}/concierge-verification/promote-faq/")

    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_answered"


def _record_id(conversation):  # noqa: F811
    conversation.refresh_from_db()
    return conversation.flags[verification.FLAG_KEY]["id"]
