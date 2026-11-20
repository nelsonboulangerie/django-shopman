# ruff: noqa: F401, F811
"""Autoridade de compra sem identificador de mensagem (WP-11, ADR-050).

O ManyChat entrega "pelo menos uma vez", sem identificador nem horário verificado. Dois
níveis: a SACOLA (valor absoluto, reenvio repete sem dobrar) com cliente verificado; o
FECHAMENTO só com o código do orçamento que o resumo mostra. Os cinco cenários do "Pronto
quando" do plano, nesta ordem, e o "sim" sem código.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Order, Session

from shopman.shop.models import ConversationBinding
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import service, tools
from shopman.storefront.concierge.turn_outcome import collapse_repeats, current_customer_text
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    SKU,
    _binding,
    _create_inbound,
    _tomorrow,
    conversation,
    ctx,
    customer,
    surface,
)

pytestmark = pytest.mark.django_db


def _at_least_once(conversation, text: str):  # noqa: F811
    """Uma entrada sem identificador de mensagem: o ingresso de hoje do ManyChat."""
    message = _create_inbound(conversation, text, f"alo-{Message.objects.count()}")
    envelope = {**message.envelope, "input_assurance": "at_least_once", "event_identity_assurance": "unavailable"}
    envelope.pop("event_id", None)
    Message.objects.filter(pk=message.pk).update(envelope=envelope)
    return message


def _claim(ctx, *texts):  # noqa: F811
    for text in texts:
        _at_least_once(ctx.conversation, text)
    from shopman.shop.models import Conversation

    Conversation.objects.filter(pk=ctx.conversation.pk).update(claim_until=None)
    ctx.conversation, _binding_, inbound = service._claim(ctx.conversation.pk, _binding(ctx.conversation).pk)
    assert inbound
    assert ctx.conversation._limited_event_assurance is True
    assert ctx.conversation._commercial_authority is False
    return ctx


def _offer(ctx, review):  # noqa: F811
    """O resumo saiu ao cliente (o que o ``_code_confirmation`` procura)."""
    Message.objects.create(
        conversation=ctx.conversation, binding=_binding(ctx.conversation), role="assistant", kind="reply",
        text=tools.render_result("review_order", review), transport_state="accepted",
        envelope={"quote_token": review["quote_token"]},
    )


def _ready(ctx, qty=2):  # noqa: F811
    assert tools.set_item(ctx, SKU, qty)["ok"]
    assert tools.set_fulfillment(ctx, "pickup", _tomorrow(), "slot-12", "")["ok"]
    review = tools.review_order(ctx, "pix")
    assert review["ok"] and review.get("quote_token"), review
    return review


def _qty(ctx) -> int:
    session = Session.objects.get(session_key=ctx.conversation.session_key)
    return int(next(item["qty"] for item in session.items if item["sku"] == SKU))


def test_1_the_same_message_delivered_twice_does_not_double_the_cart(ctx):
    _claim(ctx, "mais 2", "mais 2")

    assert current_customer_text(ctx.conversation).count("mais 2") == 1, "o reenvio vale um comando só"
    assert collapse_repeats(["mais 2", "mais 2"], limited=False) == ["mais 2", "mais 2"]
    # A sacola muda em valor absoluto: a mesma ordem repetida dá o mesmo resultado.
    assert tools.set_item(ctx, SKU, 4)["ok"] and tools.set_item(ctx, SKU, 4)["ok"]
    assert _qty(ctx) == 4
    assert Message.objects.filter(conversation=ctx.conversation, text="mais 2").count() == 2, "nada é descartado"


def test_2_an_old_confirmation_after_a_new_summary_does_not_close(ctx):
    _claim(ctx, "quero 2 pães")
    first = _ready(ctx, 2)
    _offer(ctx, first)
    second = _ready(ctx, 3)
    _offer(ctx, second)
    assert first["confirmation_code"] != second["confirmation_code"] or first["quote_token"] != second["quote_token"]

    _claim(ctx, f"confirmo {first['confirmation_code']}")

    assert tools.place_order(ctx, second["quote_token"], "pix")["error"] in {"confirmation_required", "quote_stale"}
    assert not Order.objects.exists()


def test_3_a_repeated_confirmation_makes_one_order(ctx):
    _claim(ctx, "quero 2 pães")
    review = _ready(ctx)
    _offer(ctx, review)
    assert f"Responda ‘confirmo {review['confirmation_code']}’" in tools.render_result("review_order", review)

    code = review["confirmation_code"]
    _claim(ctx, f"confirmo {code}", f"confirmo {code}")
    first = tools.place_order(ctx, review["quote_token"], "pix")
    again = tools.place_order(ctx, review["quote_token"], "pix")

    assert first["ok"], first
    assert again["order_ref"] == first["order_ref"]
    assert Order.objects.count() == 1


def test_4_without_a_verified_customer_nothing_changes(ctx):
    ConversationBinding.objects.filter(conversation=ctx.conversation).update(identity_assurance="claimed")
    _at_least_once(ctx.conversation, "quero 2 pães")
    from shopman.shop.models import Conversation

    Conversation.objects.filter(pk=ctx.conversation.pk).update(claim_until=None)
    ctx.conversation, _b, _i = service._claim(ctx.conversation.pk, _binding(ctx.conversation).pk)

    assert ctx.conversation._cart_authority is False
    assert tools.set_item(ctx, SKU, 2)["error"] == "authority_unavailable"


def test_5_with_a_read_only_connection_nothing_changes(ctx, settings):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "read_only": True}
    _claim(ctx, "quero 2 pães")

    assert ctx.conversation._cart_authority is False
    assert tools.set_item(ctx, SKU, 2)["error"] == "authority_unavailable"


@pytest.mark.parametrize("text", ["sim", "confirmo", "0000", "confirmo, e muda para entrega"])
def test_a_plain_yes_or_a_wrong_code_does_not_close(ctx, text):
    _claim(ctx, "quero 2 pães")
    review = _ready(ctx)
    _offer(ctx, review)
    if text == "0000" and review["confirmation_code"] == "0000":
        text = "0001"

    _claim(ctx, text)

    assert tools.place_order(ctx, review["quote_token"], "pix")["error"] == "confirmation_required"
    assert not Order.objects.exists()


def test_add_to_order_and_web_link_still_need_full_authority(ctx):
    _claim(ctx, "manda o link")

    assert tools.send_web_link(ctx, "menu")["error"] == "authority_unavailable"
