"""O sítio da Concierge para o executor do framework: o que ele trava, lê e traduz (N6).

O sítio não inventa efeito: chama os quatro executores que já existem (pedido, desconto,
cancelamento, acréscimo) e a reconferência de posse do N2 (``lock_turn_authority``). Estes
testes seguram a tradução: posse que mudou vira ``authority_revoked``, alvo alheio vira
``object_forbidden``, a época de posse é o ``turn_fence``, a versão da sacola é a
``Session.rev``, os termos vigentes são o ``quote_token`` só no fechamento, e cada recusa
dos executores vira o código do framework. As corridas de posse no instante do efeito
(K11, K12 no mecanismo real) já são as do N2 (``test_concierge_posse_no_efeito``), e ligar
o sítio no turno da Nice é o N9.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import PortError, TrustedContext
from django.db import transaction
from shopman.orderman.models import Session

from shopman.shop.models import Conversation
from shopman.storefront.concierge import effect_site
from shopman.storefront.concierge.effect_site import ACTIONS, ConciergeEffectSite
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CTX = TrustedContext(tenant="t", environment="test", subject="conversation:1")
CHANNEL = "whatsapp"


EPISODE = "ep-site"
AT = "2026-11-23T12:00:00.000000Z"


def command(action, target, **parameters):
    return SimpleNamespace(action=action, targets=(target,), parameters=parameters, episode_id=EPISODE,
                           expected_ownership_epoch=0)


def _episode_store():
    """O episódio do motor gravado no livro durável da casa, na época 0 (a automação dona)."""
    from conversational_commerce.contracts import Producer
    from conversational_commerce.ports.store import Transition
    from conversational_commerce.workflow.machine import open_episode

    from shopman.shop.conversational.store import ShopmanStore

    store = ShopmanStore()
    episode = open_episode(record_id="eprec-site-1", episode_id=EPISODE, tenant=CTX.tenant,
                           environment=CTX.environment, trace_id="trace-site", at=AT,
                           producer=Producer(name="test", version="1"), subject="whatsapp:conversation:1")
    store.commit_transition(CTX, Transition(episode=episode, expected_version=0), (episode,), ())
    return store, episode


def _owner_change(store, episode, kind, minute, **event):
    from conversational_commerce.contracts.episode import Wait
    from conversational_commerce.ports.store import Transition
    from conversational_commerce.workflow.machine import EpisodeEvent, transition

    at = f"2026-11-23T12:{minute:02d}:00.000000Z"
    if kind == "handoff_requested":
        event["wait"] = Wait(condition="a pessoa aceita", owner="queue", deadline="2026-11-23T13:00:00.000000Z")
    changed = transition(episode, EpisodeEvent(kind=kind, at=at, cause_id=f"cause-{kind}", **event),
                         expected_version=episode.version, record_id=f"eprec-{kind}")
    return store.commit_transition(CTX, Transition(episode=changed, expected_version=episode.version),
                                   (changed,), ())


@pytest.fixture
def site(monkeypatch):
    _episode_store()
    conversation = Conversation.objects.create(session_key="sess-1", channel_ref=CHANNEL,
                                               quote={"token": "tok-1"}, turn_fence=7)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    monkeypatch.setattr("shopman.storefront.concierge.effect_authority.lock_turn_authority",
                        lambda conv, *, channel_ref=None: Conversation.objects.get(pk=conv.pk))
    return ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))


def test_the_site_declares_the_existing_effects(site):
    assert site.actions == ACTIONS == ("change_cart", "set_fulfillment", "set_delivery_address", "set_payment",
                                      "commit_order", "grant_discount", "cancel_order", "amend_order")


def test_change_cart_locks_the_cart_without_terms(site):
    with transaction.atomic():
        reading = site.lock(CTX, command("change_cart", "sess-1", lines=[{"item": "CROISSANT", "quantity": "2"}]))
    assert reading.versions == {"sess-1": Session.objects.get(session_key="sess-1").rev}
    assert reading.terms_ref is None  # mudar a sacola é reversível e não fecha nada


@pytest.mark.parametrize("result, applied, code", [
    ({"ok": True, "items": []}, True, None),
    ({"ok": False, "code": "unknown_sku"}, False, ErrorCode.INVALID_CONTENT.value),
    ({"ok": False, "code": "invalid_qty"}, False, ErrorCode.INVALID_CONTENT.value),
    ({"ok": False, "code": "insufficient_supply"}, False, ErrorCode.FACT_UNAVAILABLE.value),
])
def test_change_cart_is_the_existing_set_item(site, monkeypatch, result, applied, code):
    calls = []
    monkeypatch.setattr("shopman.storefront.concierge.tools.set_item",
                        lambda ctx, sku, qty: calls.append((sku, qty)) or result)
    done = site.apply(CTX, command("change_cart", "sess-1", lines=[{"item": "CROISSANT", "quantity": "3"}]))
    assert calls == [("CROISSANT", 3)]  # quantidade absoluta, a do pedido
    assert done.applied is applied
    if applied:
        assert done.domain_refs == {"effect": "sess-1", "cart": "sess-1", "items": "CROISSANT"}
    else:
        assert done.refusal == code


@pytest.mark.parametrize("parameters", [{"item": "CROISSANT"}, {"quantity": "2"}, {"item": "X", "quantity": "-1"},
                                        {"item": "X", "quantity": "1.5"}])
def test_change_cart_without_item_or_whole_quantity_is_invalid_content(site, monkeypatch, parameters):
    monkeypatch.setattr("shopman.storefront.concierge.tools.set_item", lambda *a: pytest.fail("não deveria chamar"))
    done = site.apply(CTX, command("change_cart", "sess-1", lines=[parameters]))
    assert (done.applied, done.refusal) == (False, ErrorCode.INVALID_CONTENT.value)


def test_lock_reads_epoch_version_and_terms_of_the_conversation(site):
    with transaction.atomic():
        reading = site.lock(CTX, command("commit_order", "sess-1"))
        discount = site.lock(CTX, command("grant_discount", "sess-1"))
    rev = Session.objects.get(session_key="sess-1").rev
    # A época é a do episódio, lida no livro (0), nunca a cerca do turno da casa (7) nem a do comando.
    assert (reading.ownership_epoch, reading.versions, reading.terms_ref) == (0, {"sess-1": rev}, "tok-1")
    assert discount.terms_ref is None  # termos só no fechamento do pedido


def test_lock_refuses_a_cart_that_is_not_the_conversation(site):
    with transaction.atomic(), pytest.raises(PortError) as refused:
        site.lock(CTX, command("commit_order", "sess-2"))
    assert refused.value.code == ErrorCode.OBJECT_FORBIDDEN


def test_lock_turns_a_revoked_turn_into_authority_revoked(site, monkeypatch):
    from shopman.storefront.concierge.service import TurnRevoked

    def revoked(conv, *, channel_ref=None):
        raise TurnRevoked("handoff")

    monkeypatch.setattr("shopman.storefront.concierge.effect_authority.lock_turn_authority", revoked)
    with transaction.atomic(), pytest.raises(PortError) as refused:
        site.lock(CTX, command("commit_order", "sess-1"))
    assert refused.value.code == ErrorCode.AUTHORITY_REVOKED


def test_lock_refuses_an_order_of_someone_else(site, monkeypatch):
    monkeypatch.setattr("shopman.storefront.concierge.order_addition.own_order", lambda conv, ref: None)
    with transaction.atomic(), pytest.raises(PortError) as refused:
        site.lock(CTX, command("cancel_order", "ORD-9"))
    assert refused.value.code == ErrorCode.OBJECT_FORBIDDEN
    monkeypatch.setattr("shopman.storefront.concierge.order_addition.own_order", lambda conv, ref: object())
    with transaction.atomic():
        assert site.lock(CTX, command("amend_order", "ORD-1")).ownership_epoch == 0


@pytest.mark.parametrize(("result", "applied", "code"), [
    ({"ok": True, "order_ref": "ORD-1"}, True, None),
    ({"ok": False, "code": "quote_stale"}, False, ErrorCode.TERMS_CHANGED),
    ({"ok": False, "code": "authority_unavailable"}, False, ErrorCode.AUTHORITY_REVOKED),
    ({"ok": False, "code": "something_new"}, False, ErrorCode.PROVIDER_UNAVAILABLE),
])
def test_commit_order_maps_the_place_order_result(site, monkeypatch, result, applied, code):
    from shopman.storefront.concierge import tools

    monkeypatch.setattr(tools, "place_order", lambda ctx, token, method, notes: result)
    done = site.apply(CTX, command("commit_order", "sess-1", terms_ref="tok-1", payment_method="pix"))
    assert done.applied is applied
    assert (done.domain_refs == {"effect": "ORD-1", "order": "ORD-1"}) if applied else (done.refusal == code.value)


def test_commit_order_without_terms_is_invalid_content(site):
    done = site.apply(CTX, command("commit_order", "sess-1", payment_method="pix"))
    assert (done.applied, done.refusal) == (False, ErrorCode.INVALID_CONTENT.value)


def test_the_other_three_effects_map_their_outcomes(site, monkeypatch):
    from shopman.storefront.concierge import cancellation, discount, order_addition

    monkeypatch.setattr(discount, "handle_request",
                        lambda **kw: SimpleNamespace(code="granted", coupon_code="NICE1"))
    assert site.apply(CTX, command("grant_discount", "sess-1")).domain_refs == {"coupon": "NICE1", "cart": "sess-1"}
    monkeypatch.setattr(cancellation, "_execute", lambda conv, state: SimpleNamespace(code="refused", order_ref=""))
    assert site.apply(CTX, command("cancel_order", "ORD-1")).refusal == ErrorCode.REVISION_CONFLICT.value
    monkeypatch.setattr(order_addition, "apply", lambda conv, pending: SimpleNamespace(code="asked", order_ref=""))
    assert site.apply(CTX, command("amend_order", "ORD-1", add=[])).refusal == ErrorCode.TERMS_CHANGED.value


def test_a_turn_revoked_inside_the_effect_is_a_refusal(site, monkeypatch):
    from shopman.storefront.concierge import tools
    from shopman.storefront.concierge.service import TurnRevoked

    def revoked(*args):
        raise TurnRevoked("handoff")

    monkeypatch.setattr(tools, "place_order", revoked)
    done = site.apply(CTX, command("commit_order", "sess-1", terms_ref="tok-1", payment_method="pix"))
    assert (done.applied, done.refusal) == (False, ErrorCode.AUTHORITY_REVOKED.value)
    assert effect_site.ORDER_REFUSALS["revision_conflict"] == ErrorCode.REVISION_CONFLICT


def test_change_cart_applies_every_line_or_none(site, monkeypatch):
    """Várias linhas são um comando só: a recusa de uma desfaz as anteriores (o executor reverte a transação)."""
    calls = []

    def set_item(ctx, sku, qty):
        calls.append(sku)
        return {"ok": sku != "BAGUETE", "code": "insufficient_supply"}

    monkeypatch.setattr("shopman.storefront.concierge.tools.set_item", set_item)
    lines = [{"item": "CROISSANT", "quantity": "2"}, {"item": "BAGUETE", "quantity": "1"}]
    done = site.apply(CTX, command("change_cart", "sess-1", lines=lines))
    assert calls == ["CROISSANT", "BAGUETE"] and (done.applied, done.refusal) == (False, ErrorCode.FACT_UNAVAILABLE.value)
    monkeypatch.setattr("shopman.storefront.concierge.tools.set_item", lambda ctx, sku, qty: {"ok": True})
    both = site.apply(CTX, command("change_cart", "sess-1", lines=lines))
    assert both.applied and both.domain_refs["items"] == "CROISSANT,BAGUETE"


def test_the_epoch_is_read_from_the_episode_and_a_stale_command_is_revoked(site):
    """#3414: a leitura lê a época VIGENTE do episódio. A equipe assumiu e devolveu (a época subiu duas vezes):
    o comando decidido antes, retomado num turno seguinte, encontra outra época, e a guarda do Core revoga."""
    from shopman.shop.conversational.store import ShopmanStore

    store = ShopmanStore()
    episode = store.load_episode(CTX, EPISODE)
    episode = _owner_change(store, episode, "handoff_requested", 1)
    episode = _owner_change(store, episode, "handoff_accepted", 2, holder_ref="ana")
    episode = _owner_change(store, episode, "returned", 3)
    assert episode.ownership.epoch == 3  # pediu, aceitou, devolveu: a época sobe a cada troca de dono
    stale = command("commit_order", "sess-1")  # decidido na época 0
    with transaction.atomic():
        reading = site.lock(CTX, stale)
    assert reading.ownership_epoch == 3 != stale.expected_ownership_epoch  # a guarda: "a posse mudou" (revoga)


def test_a_command_whose_episode_cannot_be_read_is_revoked(site):
    lost = SimpleNamespace(action="commit_order", targets=("sess-1",), parameters={}, episode_id="ep-que-nao-existe",
                           expected_ownership_epoch=0)
    with transaction.atomic(), pytest.raises(PortError) as refused:
        site.lock(CTX, lost)
    assert refused.value.code == ErrorCode.AUTHORITY_REVOKED
