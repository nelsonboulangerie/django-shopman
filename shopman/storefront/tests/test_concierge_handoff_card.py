"""Todo handoff abre aviso (dono, 20/11/2026; caso real de 19/11, 22h16Z).

"com quem eu falo?" foi para a equipe e NENHUM aviso nasceu: o cartão de antes da mesma
conversa ainda estava aberto (visto), e o debounce por texto calou o novo. Agora:

- um cartão aberto por conversa e tipo; todo handoff novo o traz de volta (mensagem nova,
  sem o Visto) ou abre outro;
- cor de erro, no topo do Gestor, com o botão "Abrir conversa";
- voltou à Concierge, o cartão sai.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Conversation
from shopman.storefront.concierge import service
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    CONCIERGE_SETTINGS,
    _binding,
    _receive,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db


def _cards():
    return OperatorAlert.objects.filter(type="concierge_handoff").order_by("pk")


def _to_team(conversation, text, event_id):  # noqa: F811
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.ACTIVE, claim_until=None)
    _receive(conversation, text, event_id)
    return service.run_turn(conversation.pk, _binding(conversation).pk)


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "human_return_enabled": True})
def test_every_handoff_brings_the_card_back_even_after_it_was_seen(conversation, outbox):  # noqa: F811
    first = _to_team(conversation, "quero falar com um atendente", "h1")
    assert first.handoff
    [card] = _cards()
    assert card.severity == "error" and card.resolved_at is None
    card.acknowledged = True
    card.save(update_fields=["acknowledged"])

    # A conversa voltou e foi para a equipe de novo, como às 22h16Z: o aviso volta.
    second = _to_team(conversation, "quero falar com uma pessoa da equipe", "h2")

    assert second.handoff
    open_cards = list(_cards().filter(resolved_at__isnull=True))
    assert len(open_cards) == 1
    card = open_cards[0]
    assert card.acknowledged is False  # o Visto de antes não vale para o acontecimento novo
    assert "/admin/" not in card.message and "Dedupe" not in card.message


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "human_return_enabled": True})
def test_a_resolved_card_does_not_silence_the_next_handoff(conversation, outbox):  # noqa: F811
    _to_team(conversation, "quero falar com um atendente", "h3")
    _cards().update(resolved_at=OperatorAlert.objects.first().created_at)

    _to_team(conversation, "quero falar com uma pessoa, por favor", "h4")

    assert _cards().filter(resolved_at__isnull=True).count() == 1


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "human_return_enabled": True})
def test_the_card_has_the_button_that_opens_the_conversation_and_asks_for_the_top(conversation, outbox, settings):  # noqa: F811
    from shopman.backstage.projections.alerts import build_operator_alerts_projection
    from shopman.backstage.services import alerts as alert_service

    settings.SHOPMAN_ADMIN_HOST = "admin.exemplo.com.br"
    _to_team(conversation, "quero falar com um atendente", "h5")

    rows = build_operator_alerts_projection(
        alerts=list(_cards()), counts=alert_service.active_counts(scope="orders"), surface="orders"
    ).alerts
    [row] = rows
    assert row.on_screen is True and row.severity == "error"
    [action] = [a for a in row.actions if a.kind == "open_alert_context"]
    path = reverse("admin:shop_conversation_change", args=[conversation.pk])
    assert (action.label, action.href) == ("Abrir conversa", f"https://admin.exemplo.com.br{path}")


@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS, "human_return_enabled": True})
def test_back_to_the_concierge_the_card_goes_away(conversation, outbox):  # noqa: F811
    _to_team(conversation, "quero falar com um atendente", "h6")
    assert _cards().filter(resolved_at__isnull=True).count() == 1

    assert service.return_to_concierge(conversation) is True

    assert _cards().filter(resolved_at__isnull=True).count() == 0
