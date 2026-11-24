"""A sacola passa de um canal a outro antes do pedido, uma viva por vez (OC-15).

Contrato: §4.5 do plano da Etapa II omnicanal. Cada teste prova uma cláusula; os
cenários C01, C03, C05 e C07 do Relatório II e os invariantes X4 (um efeito por
intenção) e X5 (termos defasados nunca viram pedido) estão nomeados nos testes.
A corrida real com a edição na origem mora em ``test_session_transfer_postgres.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.exceptions import SessionError
from shopman.orderman.models import Session
from shopman.stockman.models import Hold

from shopman.shop.models import Channel, Shop
from shopman.shop.services import cart, sessions
from shopman.shop.services import session_transfer as transfer
from shopman.shop.services.session_transfer import TransferDestination, TransferOffer, TransferRefused

pytestmark = pytest.mark.django_db

CHAT = "whatsapp"
WEB = "web"
BREAD = "PAO-TRANSFER"
CAKE = "BOLO-TRANSFER"


def _stock(sku: str, qty: Decimal) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=qty, sku=sku, position=position, target_date=date.today(), reason="transfer test")


def _list(product: Product, channel_ref: str, price_q: int) -> None:
    listing, _ = Listing.objects.get_or_create(ref=channel_ref, defaults={"name": channel_ref, "is_active": True})
    ListingItem.objects.create(listing=listing, product=product, price_q=price_q, is_published=True, is_sellable=True)


@pytest.fixture
def store():
    Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson Boulangerie", short_name="Nelson")
    Channel.objects.create(ref=WEB, name="Loja online")
    Channel.objects.create(
        ref=CHAT,
        name="WhatsApp",
        config={"payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10}},
    )
    bread = Product.objects.create(sku=BREAD, name="Pão", base_price_q=90, is_published=True, is_sellable=True)
    cake = Product.objects.create(sku=CAKE, name="Bolo", base_price_q=500, is_published=True, is_sellable=True)
    for product, price in ((bread, 90), (cake, 500)):
        _list(product, CHAT, price)
        _list(product, WEB, price)
    _stock(BREAD, Decimal("10"))
    _stock(CAKE, Decimal("5"))
    return {"bread": bread, "cake": cake}


@pytest.fixture
def ana():
    return Customer.objects.create(ref="CUS-TRANSFER-ANA", first_name="Ana", phone="+5543999990001")


@pytest.fixture
def bia():
    return Customer.objects.create(ref="CUS-TRANSFER-BIA", first_name="Bia", phone="+5543999990002")


def _chat_cart(owner: Customer | None, *lines: tuple[str, int], data: dict | None = None) -> Session:
    key = None
    for sku, qty in lines:
        price, name = (90, "Pão") if sku == BREAD else (500, "Bolo")
        _, key = cart.add_item(session_key=key, channel_ref=CHAT, origin_channel="whatsapp", sku=sku, qty=qty,
                               unit_price_q=price, name=name)
    extra = dict(data or {})
    if owner is not None:
        extra["customer"] = {"ref": owner.ref, "name": owner.first_name, "phone": owner.phone}
    if extra:
        sessions.modify_session(session_key=key, channel_ref=CHAT,
                                ops=[{"op": "set_data", "path": k, "value": v} for k, v in extra.items()])
    return Session.objects.get(session_key=key)


def _held(key: str) -> Decimal:
    return sum((hold.quantity for hold in Hold.objects.filter(metadata__reference=key).active()), Decimal(0))


def _all_held(sku: str) -> Decimal:
    return sum((hold.quantity for hold in Hold.objects.filter(sku=sku).active()), Decimal(0))


def _as(customer: Customer | None, **extra) -> TransferDestination:
    return TransferDestination(customer_ref=customer.ref if customer else "", **extra)


def _offer(source: Session, owner: Customer | None) -> TransferOffer:
    return transfer.offer(CHAT, source.session_key, WEB, customer_ref=owner.ref if owner else "", actor="concierge")


# ── offer ─────────────────────────────────────────────────────────────


def test_offer_registers_revision_and_total_without_touching_the_source(store, ana):
    source = _chat_cart(ana, (BREAD, 2))
    before = (source.rev, source.state, source.data, source.items)

    offer = _offer(source, ana)

    source.refresh_from_db()
    assert (source.rev, source.state, source.data, source.items) == before
    assert offer.rev == source.rev and offer.total_q == 180 and offer.customer_ref == ana.ref
    assert TransferOffer.from_metadata(offer.as_metadata()) == offer
    assert not Session.objects.filter(channel_ref=WEB).exists()
    assert _held(source.session_key) == Decimal(2)


def test_offer_of_someone_elses_cart_is_refused(store, ana, bia):
    source = _chat_cart(ana, (BREAD, 1))
    with pytest.raises(TransferRefused) as refused:
        _offer(source, bia)
    assert refused.value.code == "not_authorized"


def test_offer_with_a_tampered_identity_is_invalid(store, ana):
    metadata = _offer(_chat_cart(ana, (BREAD, 1)), ana).as_metadata()
    metadata["rev"] = metadata["rev"] + 1
    with pytest.raises(TransferRefused) as refused:
        TransferOffer.from_metadata(metadata)
    assert refused.value.code == "invalid_offer"


# ── accept ────────────────────────────────────────────────────────────


def test_c01_cart_arrives_on_the_site_and_only_one_stays_alive(store, ana):
    """C01: a sacola chega ao site; a origem fica abandonada e diz para onde foi; sem reserva dupla."""
    source = _chat_cart(ana, (BREAD, 2), (CAKE, 1), data={"fulfillment_type": "pickup", "delivery_time_slot": "slot-12"})
    offer = _offer(source, ana)

    receipt = transfer.accept(offer, dest_context=_as(ana), actor="storefront")

    source.refresh_from_db()
    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert source.state == "abandoned" and target.state == "open" and target.channel_ref == WEB
    assert source.data["transferred_to"]["session_key"] == target.session_key
    assert source.data["transfer_receipt"] == receipt.as_dict()
    assert target.data["transferred_from"]["channel_ref"] == CHAT
    assert target.data["transferred_from"]["session_key"] == source.session_key
    assert target.data["transferred_from"]["rev"] == offer.rev
    assert target.data["delivery_time_slot"] == "slot-12" and target.data["fulfillment_type"] == "pickup"
    assert target.data["customer"]["ref"] == ana.ref and target.data["origin_channel"] == "whatsapp"
    assert {line["sku"]: Decimal(line["qty"]) for line in target.items} == {BREAD: Decimal(2), CAKE: Decimal(1)}
    assert receipt.differences == [] and receipt.source_total_q == receipt.dest_total_q == 680
    # Nenhuma reserva dupla: tudo que a origem segurava passou ao destino.
    assert _held(source.session_key) == 0
    assert _held(target.session_key) == _all_held(BREAD) + _all_held(CAKE) == Decimal(3)


def test_x5_revision_changed_after_the_offer_is_refused_as_source_changed(store, ana):
    source = _chat_cart(ana, (BREAD, 1))
    offer = _offer(source, ana)
    cart.add_item(session_key=source.session_key, channel_ref=CHAT, origin_channel="whatsapp", sku=CAKE, qty=1,
                  unit_price_q=500)

    with pytest.raises(TransferRefused) as refused:
        transfer.accept(offer, dest_context=_as(ana), actor="storefront")

    assert refused.value.code == "source_changed"
    source.refresh_from_db()
    assert source.state == "open" and "transfer_receipt" not in source.data
    assert not Session.objects.filter(channel_ref=WEB).exists()


def test_x5_owner_change_without_revision_bump_is_source_changed(store, ana):
    """Identificar não incrementa ``rev``: a oferta anônima não vale depois que a sacola ganhou dono."""
    source = _chat_cart(None, (BREAD, 1))
    offer = _offer(source, None)
    sessions.assign_customer(session_key=source.session_key, channel_ref=CHAT, customer_uuid=ana.uuid)

    with pytest.raises(TransferRefused) as refused:
        transfer.accept(offer, dest_context=_as(ana, identity_strength="device"), actor="storefront")
    assert refused.value.code == "source_changed"


def test_x5_the_old_cart_cannot_be_edited_or_closed_after_the_transfer(store, ana):
    """O orçamento da Nice fica velho por construção: a origem está abandonada."""
    source = _chat_cart(ana, (BREAD, 1))
    transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")
    with pytest.raises(SessionError) as refused:
        sessions.modify_session(session_key=source.session_key, channel_ref=CHAT, ops=[])
    assert refused.value.code == "already_abandoned"


def test_destination_with_items_is_a_conflict_and_never_merges(store, ana):
    source = _chat_cart(ana, (BREAD, 2))
    _, browser_key = cart.add_item(session_key=None, channel_ref=WEB, origin_channel="web", sku=CAKE, qty=1,
                                   unit_price_q=500)
    offer = _offer(source, ana)

    with pytest.raises(TransferRefused) as refused:
        transfer.accept(offer, dest_context=_as(ana, session_key=browser_key), actor="storefront")
    assert refused.value.code == "destination_conflict"
    source.refresh_from_db()
    assert source.state == "open" and _held(source.session_key) == Decimal(2)
    assert [line["sku"] for line in Session.objects.get(session_key=browser_key).items] == [CAKE]

    # "Substituir": a do destino é abandonada inteira, nunca mesclada.
    receipt = transfer.accept(offer, dest_context=_as(ana, session_key=browser_key, replace_existing=True),
                              actor="storefront")
    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert Session.objects.get(session_key=browser_key).state == "abandoned" and _held(browser_key) == 0
    assert [line["sku"] for line in target.items] == [BREAD]


def test_the_persons_own_site_cart_elsewhere_is_also_a_conflict(store, ana):
    source = _chat_cart(ana, (BREAD, 1))
    _, other_device = cart.add_item(session_key=None, channel_ref=WEB, origin_channel="web", sku=CAKE, qty=1,
                                    unit_price_q=500)
    sessions.assign_customer(session_key=other_device, channel_ref=WEB, customer_uuid=ana.uuid)

    with pytest.raises(TransferRefused) as refused:
        transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")
    assert refused.value.code == "destination_conflict"


def test_item_not_sold_on_the_site_becomes_an_explicit_difference(store, ana):
    source = _chat_cart(ana, (BREAD, 2), (CAKE, 1))
    ListingItem.objects.filter(listing__ref=WEB, product__sku=CAKE).update(is_sellable=False)

    receipt = transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")

    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert [line["sku"] for line in target.items] == [BREAD]
    assert receipt.differences == [{"kind": "unavailable", "sku": CAKE, "name": "Bolo", "qty": "1"}]
    assert _all_held(CAKE) == 0


def test_c07_price_of_the_destination_channel_wins_and_is_reported(store, ana):
    """C07: o preço muda entre canais; a sacola chega com o preço de lá e a diferença dita."""
    source = _chat_cart(ana, (BREAD, 2))
    ListingItem.objects.filter(listing__ref=WEB, product__sku=BREAD).update(price_q=110)

    receipt = transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")

    assert receipt.differences == [{"kind": "price_changed", "sku": BREAD, "name": "Pão", "from_q": 90, "to_q": 110}]
    assert (receipt.source_total_q, receipt.dest_total_q) == (180, 220)


def test_c07_stock_that_changed_meanwhile_arrives_reduced(store, ana):
    """C07: a reserva da origem venceu e outra pessoa levou o pão; chega o que há, dito."""
    source = _chat_cart(ana, (BREAD, 5))
    offer = _offer(source, ana)
    from shopman.shop.services.availability import release_session_holds

    release_session_holds(source.session_key)  # a reserva venceu enquanto a pessoa decidia
    cart.add_item(session_key=None, channel_ref=WEB, origin_channel="web", sku=BREAD, qty=8, unit_price_q=90)

    receipt = transfer.accept(offer, dest_context=_as(ana), actor="storefront")

    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert Decimal(target.items[0]["qty"]) == Decimal(2)
    assert receipt.differences == [{"kind": "qty_reduced", "sku": BREAD, "name": "Pão", "from_qty": "5", "to_qty": "2"}]
    assert _all_held(BREAD) == Decimal(10)


def test_nothing_available_refuses_and_keeps_the_source_alive(store, ana):
    source = _chat_cart(ana, (CAKE, 1))
    ListingItem.objects.filter(listing__ref=WEB, product__sku=CAKE).update(is_sellable=False)

    with pytest.raises(TransferRefused) as refused:
        transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")

    assert refused.value.code == "nothing_available"
    source.refresh_from_db()
    assert source.state == "open" and _held(source.session_key) == Decimal(1)
    assert not Session.objects.filter(channel_ref=WEB).exists()


def test_x4_the_same_acceptance_again_returns_the_same_receipt(store, ana):
    """X4: a mesma oferta aceita duas vezes é uma sacola só, o mesmo recibo."""
    source = _chat_cart(ana, (BREAD, 2))
    offer = _offer(source, ana)

    first = transfer.accept(offer, dest_context=_as(ana), actor="storefront")
    again = transfer.accept(TransferOffer.from_metadata(offer.as_metadata()), dest_context=_as(ana), actor="storefront")

    assert again.replayed and not first.replayed
    assert again.as_dict() == first.as_dict()
    assert Session.objects.filter(channel_ref=WEB).count() == 1
    assert _all_held(BREAD) == _held(first.dest_session_key) == Decimal(2)


def test_x4_the_recorded_receipt_is_not_handed_to_someone_else(store, ana, bia):
    source = _chat_cart(ana, (BREAD, 1))
    offer = _offer(source, ana)
    transfer.accept(offer, dest_context=_as(ana), actor="storefront")
    with pytest.raises(TransferRefused) as refused:
        transfer.accept(offer, dest_context=_as(bia), actor="storefront")
    assert refused.value.code == "not_authorized"


def test_c05_a_cart_with_an_owner_is_never_handed_to_another_person(store, ana, bia):
    """C05: dois clientes no mesmo navegador; a sacola de uma não vai para a outra."""
    source = _chat_cart(ana, (BREAD, 1))
    with pytest.raises(TransferRefused) as refused:
        transfer.accept(_offer(source, ana), dest_context=_as(bia, identity_strength="device"), actor="storefront")
    assert refused.value.code == "not_authorized"
    source.refresh_from_db()
    assert source.state == "open"


@pytest.mark.parametrize(
    ("strength", "verified", "accepted"),
    [("device", False, True), ("", True, True), ("number", False, False), ("", False, False)],
)
def test_anonymous_cart_goes_only_to_a_proven_person(store, ana, strength, verified, accepted):
    source = _chat_cart(None, (BREAD, 1))
    offer = _offer(source, None)
    destination = _as(ana, identity_strength=strength, verified_customer=verified)
    if accepted:
        receipt = transfer.accept(offer, dest_context=destination, actor="storefront")
        target = Session.objects.get(session_key=receipt.dest_session_key)
        assert target.data["customer"]["ref"] == ana.ref
    else:
        with pytest.raises(TransferRefused) as refused:
            transfer.accept(offer, dest_context=destination, actor="storefront")
        assert refused.value.code == "not_authorized"


def test_anonymous_cart_needs_someone_on_the_other_side(store):
    source = _chat_cart(None, (BREAD, 1))
    with pytest.raises(TransferRefused) as refused:
        transfer.accept(_offer(source, None), dest_context=_as(None, identity_strength="device"), actor="storefront")
    assert refused.value.code == "not_authorized"


def test_c05_anonymous_cart_does_not_carry_address_or_gift_into_the_account(store, ana):
    source = _chat_cart(None, (BREAD, 1), data={
        "fulfillment_type": "delivery",
        "delivery_address": "Rua de alguém, 1",
        "recipient": {"name": "Outra pessoa", "phone": "+5543999990009"},
        "is_gift": True,
    })
    receipt = transfer.accept(_offer(source, None), dest_context=_as(ana, identity_strength="device"),
                              actor="storefront")
    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert "delivery_address" not in target.data and "recipient" not in target.data and "is_gift" not in target.data
    assert {"kind": "details_not_carried", "fields": ["delivery_address", "is_gift", "recipient"]} in receipt.differences


def test_c03_a_cart_that_became_an_order_never_becomes_a_second_one(store, ana):
    """C03: depois do pedido (onde nasce o pagamento) a oferta velha não cria outra sacola."""
    source = _chat_cart(ana, (BREAD, 1))
    offer = _offer(source, ana)
    Session.objects.filter(pk=source.pk).update(state="committed")  # o pedido saiu pela conversa

    with pytest.raises(TransferRefused) as refused:
        transfer.accept(offer, dest_context=_as(ana), actor="storefront")
    assert refused.value.code == "source_changed"
    assert not Session.objects.filter(channel_ref=WEB).exists()


def test_c03_payment_never_travels_and_an_unaccepted_method_is_reported(store, ana):
    source = _chat_cart(ana, (BREAD, 1), data={"payment": {"method": "pix"}})
    receipt = transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")
    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert "payment" not in target.data
    assert receipt.differences == [{"kind": "payment_not_available", "method": "pix"}]


def test_coupon_exclusive_to_the_conversation_becomes_a_difference(store, ana):
    from shopman.shop.models import Coupon, Promotion

    promotion = Promotion.objects.create(
        ref="so-na-conversa", name="Só na conversa", type="percent", value=10,
        valid_from=timezone.now() - timedelta(days=1), valid_until=timezone.now() + timedelta(days=1),
    )
    promotion.channels.add(Channel.objects.get(ref=CHAT))
    Coupon.objects.create(code="CONVERSA10", promotion=promotion)
    source = _chat_cart(ana, (BREAD, 1), data={"coupon_code": "CONVERSA10"})

    receipt = transfer.accept(_offer(source, ana), dest_context=_as(ana), actor="storefront")

    target = Session.objects.get(session_key=receipt.dest_session_key)
    assert "coupon_code" not in target.data
    assert {"kind": "coupon_not_applied", "code": "CONVERSA10", "reason": "coupon_wrong_channel"} in receipt.differences


# ── mesmo canal: a sacola da loja que viaja dentro da loja ──────────


def test_same_channel_cart_is_adopted_not_recreated_and_wins_over_the_stale_one(store, ana):
    _, carried_key = cart.add_item(session_key=None, channel_ref=WEB, origin_channel="web", sku=BREAD, qty=2,
                                   unit_price_q=90)
    _, stale_key = cart.add_item(session_key=None, channel_ref=WEB, origin_channel="web", sku=CAKE, qty=1,
                                 unit_price_q=500)
    offer = transfer.carried_offer({"cart_session_key": carried_key}, channel_ref=WEB)

    receipt = transfer.accept(offer, dest_context=_as(ana, identity_strength="device", session_key=stale_key),
                              actor="storefront")

    assert receipt.dest_session_key == carried_key
    carried = Session.objects.get(session_key=carried_key)
    assert carried.state == "open" and carried.data["customer"]["ref"] == ana.ref
    assert "transferred_from" not in carried.data and "transfer_receipt" not in carried.data
    # A velha não é mesclada nem abandonada: é resíduo do mesmo canal.
    assert Session.objects.get(session_key=stale_key).state == "open"
    assert Session.objects.filter(channel_ref=WEB).count() == 2


def test_same_channel_ref_without_items_is_not_adopted(store, ana):
    offer = transfer.carried_offer({"cart_session_key": "sk-sem-sacola"}, channel_ref=WEB)
    with pytest.raises(TransferRefused) as refused:
        transfer.accept(offer, dest_context=_as(ana, identity_strength="device"), actor="storefront")
    assert refused.value.code == "no_cart"


def test_link_without_cart_carries_no_offer():
    assert transfer.carried_offer({"next": "/menu"}, channel_ref=WEB) is None
    assert transfer.carried_offer(None, channel_ref=WEB) is None
