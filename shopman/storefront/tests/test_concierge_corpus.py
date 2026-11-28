"""O corpus anonimizado de aprendizado conversacional (dono, 20/11/2026, #2851).

Protege o que a issue pede:

1. **Nenhum identificador passa**: nem subject, vínculo, conversa, ``external_id`` ou
   hora exata, nem o dado pessoal que sobrou no texto livre e que a segunda passada pega.
2. **O resultado sai do turno**: entendeu, vou verificar, equipe, só observada.
3. **Conferência humana**: a amostra da semana vai ao curador; achado de dado pessoal
   pausa a cópia até a linha ser apagada.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage
from shopman.storefront.concierge import corpus
from shopman.storefront.models import ConversationCorpusEntry, CorpusOutcome, CorpusReview

pytestmark = pytest.mark.django_db

SUBJECT = "sub-9988776655"
CUSTOMER = "Joaquim Pereira"


def _conversation():
    conversation = Conversation.objects.create(channel_ref="whatsapp", customer_name=CUSTOMER, phone="+5543999887766")
    binding = ConversationBinding.objects.create(
        conversation=conversation, provider="manychat", account="acc-1", transport_channel="whatsapp",
        subject=SUBJECT, connection_key="manychat-whatsapp-primary", status=ConversationBinding.Status.ACTIVE,
    )
    return conversation, binding


def _inbound(conversation, binding, text, *, observed, at=None, fence=None, envelope=None):
    message = ConversationMessage.objects.create(
        conversation=conversation, binding=binding, role="user", kind=ConversationMessage.Kind.INBOUND,
        text=text, external_id=f"ext-digest-{ConversationMessage.objects.count()}",
        automation_eligible=not observed,
        retention_until=timezone.now() + timedelta(days=7) if observed else None,
        consumed_by=fence,
        envelope={"version": 3, **({"processing_mode": "observe"} if observed else {}), **(envelope or {})},
    )
    if at is not None:
        ConversationMessage.objects.filter(pk=message.pk).update(created_at=at)
    return message


def _reply(conversation, binding, *, fence, receipts=(), purpose="reply"):
    return ConversationMessage.objects.create(
        conversation=conversation, binding=binding, role="assistant", kind=ConversationMessage.Kind.REPLY,
        text="ok", envelope={"version": 3, "turn_fence": fence, "purpose": purpose, "receipts": sorted(receipts)},
    )


def _all_fields(entry) -> str:
    return " ".join(str(getattr(entry, field.attname)) for field in entry._meta.concrete_fields)


# ── 1. A segunda passada ──────────────────────────────────────────────


def test_the_second_pass_takes_what_the_first_left():
    text, found = corpus.anonymize(
        "Oi, aqui é pra entregar pro Joaquim Pereira na Vila Nova, placa ABC1D23, me liga 43 99887-7665, "
        "manda no joaquim@exemplo.com ou www.exemplo.com, chego 14h30 do dia 12/03. Tem croissant?"
    )
    for leaked in ("Joaquim", "Pereira", "Vila", "Nova", "ABC1D23", "99887", "joaquim@", "exemplo", "14h30", "12/03"):
        assert leaked not in text, (leaked, text)
    assert text.startswith("Oi,") and "croissant" in text  # o começo da frase e o produto ficam
    assert {"proper_name", "plate", "long_number", "email", "link", "time", "date"} <= set(found)


# ── 2. A cópia ────────────────────────────────────────────────────────


def test_an_observed_message_is_copied_without_anything_that_links_to_the_person():
    conversation, binding = _conversation()
    at = datetime(2026, 11, 18, 14, 37, tzinfo=ZoneInfo("America/Sao_Paulo"))  # quarta-feira
    message = _inbound(conversation, binding, "tem pão de queijo hoje? sou o Joaquim", observed=True, at=at,
                       envelope={"triage_shadow": {"rules": "product_question", "jev": ""}})

    assert corpus.copy() == {"copied": 1, "skipped": 0, "paused": False}
    entry = ConversationCorpusEntry.objects.get()
    assert entry.outcome == CorpusOutcome.OBSERVED and entry.intent == "product_question"
    assert (entry.weekday, entry.hour_band) == (2, 12)
    flat = _all_fields(entry)
    for identifier in (SUBJECT, message.external_id, "Joaquim", "99887766", "14:37", "2026-11-18"):
        assert identifier not in flat, identifier
    message.refresh_from_db()
    assert message.envelope[corpus.COPIED_KEY] is True
    assert corpus.copy()["copied"] == 0  # não copia duas vezes


def test_the_answered_turn_gives_the_outcome():
    conversation, binding = _conversation()
    cases = [
        ((), "reply", CorpusOutcome.UNDERSTOOD),
        (("verify", "team_notified"), "reply", CorpusOutcome.VERIFYING),
        (("handoff",), "handoff_ack", CorpusOutcome.TEAM),
        (("order",), "reply", CorpusOutcome.ORDER),
    ]
    for fence, (receipts, purpose, _expected) in enumerate(cases, start=1):
        _inbound(conversation, binding, f"pergunta {fence}", observed=False, fence=fence,
                 envelope={"triage": {"intent": "hours_delivery"}})
        _reply(conversation, binding, fence=fence, receipts=receipts, purpose=purpose)

    corpus.copy()

    outcomes = list(ConversationCorpusEntry.objects.order_by("id").values_list("outcome", flat=True))
    assert outcomes == [expected for _r, _p, expected in cases]
    assert set(ConversationCorpusEntry.objects.values_list("intent", flat=True)) == {"hours_delivery"}


def test_the_known_name_of_an_answered_conversation_never_reaches_the_corpus():
    conversation, binding = _conversation()
    _inbound(conversation, binding, "aqui é o joaquim pereira, abre domingo?", observed=False, fence=7)
    _reply(conversation, binding, fence=7)

    corpus.copy()

    assert "joaquim" not in ConversationCorpusEntry.objects.get().text.casefold()


def test_a_turn_still_without_a_reply_waits_for_the_next_cycle():
    conversation, binding = _conversation()
    _inbound(conversation, binding, "tem bolo?", observed=False, fence=3)
    assert corpus.copy() == {"copied": 0, "skipped": 1, "paused": False}
    _reply(conversation, binding, fence=3)
    assert corpus.copy()["copied"] == 1


# ── 3. A conferência ──────────────────────────────────────────────────


def test_the_first_copies_of_the_week_go_to_the_curator(monkeypatch):
    monkeypatch.setattr(corpus, "SAMPLE_PER_WEEK", 2)
    conversation, binding = _conversation()
    for index in range(4):
        _inbound(conversation, binding, f"mensagem {index}", observed=True)

    corpus.copy(now=timezone.now())

    reviews = list(ConversationCorpusEntry.objects.order_by("id").values_list("review", flat=True))
    assert reviews == [CorpusReview.PENDING] * 2 + [CorpusReview.NOT_SAMPLED] * 2


def test_personal_data_found_pauses_the_copy_until_the_line_is_deleted():
    conversation, binding = _conversation()
    _inbound(conversation, binding, "primeira", observed=True)
    corpus.copy()
    ConversationCorpusEntry.objects.update(review=CorpusReview.PERSONAL_DATA)
    _inbound(conversation, binding, "segunda", observed=True)

    assert corpus.copy() == {"copied": 0, "paused": True}

    ConversationCorpusEntry.objects.filter(review=CorpusReview.PERSONAL_DATA).delete()
    assert corpus.copy()["copied"] == 1


def test_only_the_curator_sees_the_sample_in_the_admin():
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(defaults={"name": "Loja"})
    _conversation_, binding = _conversation()
    _inbound(_conversation_, binding, "tem croissant?", observed=True)
    corpus.copy()
    staff = User.objects.create_user("operador", password="x", is_staff=True)
    staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_conversationcorpusentry"]))
    client = Client()
    client.force_login(staff)
    url = "/admin/storefront/conversationcorpusentry/"
    assert client.get(url).status_code == 403

    staff.user_permissions.add(Permission.objects.get(codename="review_conversation_observations"))
    staff = User.objects.get(pk=staff.pk)
    client.force_login(staff)
    page = client.get(url)
    assert page.status_code == 200 and "tem croissant?" in page.content.decode()
