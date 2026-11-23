"""A loja executa o recebimento que a conversa definiu (passo 3 do pedido pelo motor).

O comando ``set_fulfillment`` do framework chega ao sítio da Concierge, que chama os
executores que já existem: a retirada pelo ``tools.set_fulfillment`` com a janela da grade
que cobre a hora dita; o dia sem modo e a entrega pela régua de encomenda do checkout e pela
operação canônica da sessão. Estes testes seguram o que é aplicado, o que o recibo diz e cada
recusa no vocabulário do framework. E a sacola nova: o primeiro pedido pelo motor tem onde cair.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import PortError, TrustedContext
from django.db import transaction
from shopman.orderman.models import Session

from shopman.shop.models import Conversation
from shopman.storefront.concierge.effect_site import ConciergeEffectSite
from shopman.storefront.concierge.ports import new_cart_ref
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CTX = TrustedContext(tenant="t", environment="test", subject="conversation:1")
CHANNEL = "whatsapp"
DAY = "2026-11-24"
SLOTS = [{"ref": "slot-09", "label": "A partir das 9h", "available": True},
         {"ref": "slot-15", "label": "A partir das 15h", "available": True}]


def command(target="sess-1", **parameters):
    return SimpleNamespace(action="set_fulfillment", targets=(target,), parameters=parameters)


@pytest.fixture
def house(monkeypatch):
    """A sacola da conversa e os executores da casa, gravando o que foi chamado."""
    conversation = Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL, turn_fence=3)
    session = Session.objects.create(session_key="sess-1", channel_ref=CHANNEL, data={})
    calls: list = []
    state = SimpleNamespace(types=["pickup", "delivery"], tool={}, preorder={}, calls=calls, session=session)
    from shopman.storefront.concierge import order_closing, tools

    def execute(name, args, ctx):
        calls.append((name, dict(args)))
        if name == "list_fulfillment_slots":
            return {"ok": True, "pickup_slots": SLOTS, "delivery_slots": SLOTS}
        return state.tool.get(name, {"ok": True})

    monkeypatch.setattr(tools, "execute", execute)
    monkeypatch.setattr(tools, "_ensure_session", lambda ctx: Session.objects.get(session_key="sess-1"))
    monkeypatch.setattr(order_closing, "_fulfillment_types", lambda channel_ref: list(state.types))
    monkeypatch.setattr("shopman.storefront.intents.checkout._validate_preorder",
                        lambda day, **kw: dict(state.preorder))
    monkeypatch.setattr("shopman.shop.services.sessions.modify_session",
                        lambda **kw: calls.append(("modify_session", kw["ops"])))
    monkeypatch.setattr("shopman.shop.services.cart.set_delivery_draft",
                        lambda **kw: calls.append(("set_delivery_draft", kw["fulfillment_type"])))
    monkeypatch.setattr("shopman.storefront.concierge.effect_authority.lock_turn_authority",
                        lambda conv, *, channel_ref=None: Conversation.objects.get(pk=conv.pk))
    state.site = ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))
    return state


def test_pickup_tomorrow_at_four_takes_the_window_that_covers_the_hour(house):
    done = house.site.apply(CTX, command(date=DAY, mode="pickup", time="16:00"))
    assert done.applied and dict(done.domain_refs) == {"cart": "sess-1", "date": DAY, "mode": "pickup",
                                                       "window": "slot-15", "time": "16:00"}
    assert house.calls[-1] == ("set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": DAY,
                                                   "slot_ref": "slot-15"})


def test_an_hour_before_any_window_is_unavailable_and_nothing_is_set(house):
    done = house.site.apply(CTX, command(date=DAY, mode="pickup", time="07:00"))
    assert (done.applied, done.refusal) == (False, ErrorCode.FULFILLMENT_UNAVAILABLE.value)
    assert "set_fulfillment" not in [name for name, _ in house.calls]


def test_an_hour_without_mode_is_pickup(house):
    done = house.site.apply(CTX, command(date=DAY, time="10:00"))
    assert dict(done.domain_refs)["mode"] == "pickup" and dict(done.domain_refs)["window"] == "slot-09"


def test_the_day_alone_with_two_modes_keeps_only_the_day(house):
    done = house.site.apply(CTX, command(date=DAY))
    assert done.applied and dict(done.domain_refs) == {"cart": "sess-1", "date": DAY}  # o modo não se inventa
    assert house.calls == [("modify_session", [{"op": "set_data", "path": "delivery_date", "value": DAY},
                                               {"op": "set_data", "path": "delivery_time_slot", "value": ""}])]


def test_the_day_alone_with_one_mode_is_that_mode(house):
    house.types = ["pickup"]
    done = house.site.apply(CTX, command(date=DAY))
    assert dict(done.domain_refs)["mode"] == "pickup"
    assert house.calls[-1] == ("set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": DAY,
                                                   "slot_ref": ""})


def test_what_was_set_before_stays(house):
    Session.objects.filter(session_key="sess-1").update(
        data={"fulfillment_type": "pickup", "delivery_date": DAY, "delivery_time_slot": "slot-15"})
    done = house.site.apply(CTX, command(mode="pickup"))
    assert dict(done.domain_refs) == {"cart": "sess-1", "date": DAY, "mode": "pickup", "window": "slot-15"}


def test_delivery_sets_the_mode_and_the_day_and_leaves_the_address_to_the_closing(house):
    done = house.site.apply(CTX, command(date=DAY, mode="delivery"))
    assert dict(done.domain_refs) == {"cart": "sess-1", "date": DAY, "mode": "delivery"}
    assert ("set_delivery_draft", "delivery") in house.calls


@pytest.mark.parametrize("parameters", [{}, {"date": "amanhã"}, {"date": "2026-02-30"}, {"time": "4pm"},
                                        {"note": "x"}, {"window": "slot-15"}, {"date": ""}])
def test_a_malformed_command_is_invalid_content(house, parameters):
    done = house.site.apply(CTX, command(**parameters))
    assert (done.applied, done.refusal) == (False, ErrorCode.INVALID_CONTENT.value) and house.calls == []


def test_a_mode_the_channel_does_not_offer_is_unavailable(house):
    house.types = ["pickup"]
    done = house.site.apply(CTX, command(mode="delivery"))
    assert (done.applied, done.refusal) == (False, ErrorCode.FULFILLMENT_UNAVAILABLE.value)


def test_a_day_the_house_does_not_take_is_unavailable(house):
    house.preorder = {"delivery_date": "A loja não abre nesse dia."}
    done = house.site.apply(CTX, command(date=DAY))
    assert (done.applied, done.refusal) == (False, ErrorCode.FULFILLMENT_UNAVAILABLE.value)


@pytest.mark.parametrize(("refusal", "code"), [
    ({"ok": False, "error": "invalid_date"}, ErrorCode.INVALID_CONTENT),
    ({"ok": False, "error": "validation", "errors": {"delivery_date": "x"}}, ErrorCode.FULFILLMENT_UNAVAILABLE),
    ({"ok": False, "error": "revision_conflict"}, ErrorCode.REVISION_CONFLICT),
])
def test_the_house_refusal_is_said_in_the_framework_words(house, refusal, code):
    house.tool = {"set_fulfillment": refusal}
    done = house.site.apply(CTX, command(date=DAY, mode="pickup"))
    assert (done.applied, done.refusal) == (False, code.value)


# ── a sacola nova ──────────────────────────────────────────────────────────────────────


def test_the_first_order_falls_in_the_new_cart_of_the_conversation(house):
    with transaction.atomic():
        for action in ("change_cart", "set_fulfillment"):
            reading = house.site.lock(CTX, SimpleNamespace(action=action, targets=(new_cart_ref(1),), parameters={}))
            assert (reading.ownership_epoch, dict(reading.versions)) == (3, {new_cart_ref(1): 0})


def test_closing_the_order_never_targets_a_cart_that_does_not_exist(house):
    with transaction.atomic(), pytest.raises(PortError) as refused:
        house.site.lock(CTX, SimpleNamespace(action="commit_order", targets=(new_cart_ref(1),), parameters={}))
    assert refused.value.code == ErrorCode.OBJECT_FORBIDDEN


def test_without_a_cart_the_turn_subject_is_the_new_cart(db):
    from shopman.storefront.concierge.turn_framework import subject_for

    conversation = Conversation.objects.create(channel_ref=CHANNEL)
    subject = subject_for(conversation)(CTX, SimpleNamespace(identity_evidence=()))
    assert subject.cart_ref == new_cart_ref(conversation.pk)
    conversation.session_key = "sess-9"
    assert subject_for(conversation)(CTX, SimpleNamespace(identity_evidence=())).cart_ref == "sess-9"
