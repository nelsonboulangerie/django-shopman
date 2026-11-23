"""A porta de leitura do comércio sobre o Shopman, pela suíte de conformidade do framework (N4).

O que estes testes seguram:

- a checagem de forma da porta do framework (``run_checks("commerce_read", ...)``) passa com
  o arnês do Shopman: fato com fonte, promessa, cotação selada que confere o hash, escassez
  ``Unavailable`` e cliente alheio recusado;
- K04: a fonte que falha vira ``Unknown``, nunca o valor velho;
- ``promise()`` devolve o pronto, o esperado e o planejado separados, e o que se pode
  prometer como decisão à parte (K27: "pode prometer" não é "há unidade separada");
- autorização por objeto: sacola, cliente e pedido só do sujeito do contexto.
"""

from __future__ import annotations

from unittest import mock

import pytest
from conversational_commerce.contracts import Known, Quantity, Unknown
from conversational_commerce.contracts.common import Unavailable
from conversational_commerce.ports import PortError, TrustedContext
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks
from conversational_commerce.testing.fakes.clock import FakeClock
from shopman.offerman.models import Product
from shopman.orderman.models import Session

from shopman.shop.conversational.commerce_read import DenyAll, ShopmanCommerceRead
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
SKU = "PAO-TESTE"
CTX = TrustedContext(tenant="nelson-boulangerie", environment="test", subject="conversation:1")


class Owns:
    """A posse de teste: a conversa 1 tem a sacola ``sess-1`` e o cliente ``cust-1``."""

    def __init__(self, cart="sess-1", customer="cust-1", orders=()):
        self._cart, self._customer, self._orders = cart, customer, set(orders)

    def cart(self, ctx):
        return self._cart if ctx.subject == CTX.subject else None

    def customer(self, ctx):
        return self._customer if ctx.subject == CTX.subject else None

    def owns_order(self, ctx, ref):
        return ctx.subject == CTX.subject and ref in self._orders


@pytest.fixture
def shop():
    Shop.objects.create(name="Nelson Boulangerie")
    Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={})
    Product.objects.create(sku=SKU, name="Pão de teste", base_price_q=450, is_published=True, is_sellable=True)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL,
                           items=[{"sku": SKU, "qty": 2, "unit_price_q": 450}])


def port(**kwargs) -> ShopmanCommerceRead:
    return ShopmanCommerceRead(channel_ref=CHANNEL, ownership=kwargs.pop("ownership", Owns()), **kwargs)


def test_the_framework_shape_check_passes_on_the_shopman_harness(shop):
    clock = FakeClock()
    env = HarnessEnv(ctx=CTX, clock=clock, item_ref=SKU, cart_ref="sess-1", other_subject="cust-2", currency="BRL")
    assert run_checks("commerce_read", port(), env) == []


@conformance("K04", invariants=("N21",), scope="core")
def test_k04_a_failing_source_is_unknown_never_the_old_value(shop):
    reader = port()
    first = reader.read_item(CTX, SKU)
    assert isinstance(first, Known) and first.value["price_minor"] == 450 and first.source == "offerman:whatsapp"
    with mock.patch("shopman.shop.services.display_prices.resolve_prices", side_effect=RuntimeError("fora")):
        failed = reader.read_item(CTX, SKU)
    assert failed == Unknown(reason="source_failed")
    assert reader.read_item(CTX, "NAO-EXISTE") == Unknown(reason="not_found")
    with mock.patch("shopman.shop.services.availability.decide", side_effect=RuntimeError("fora")):
        reading = reader.promise(CTX, SKU, Quantity(value="1", unit="unit"), "2026-11-19T12:00:00.000000Z")
    assert {reading.factual, reading.expected, reading.planned, reading.promisable} == {
        Unknown(reason="source_failed")}


def test_every_known_fact_has_source_and_validity(shop):
    fact = port(fact_validity_seconds=120).read_item(CTX, SKU)
    assert fact.source and fact.valid_until > fact.observed_at


def test_promise_keeps_the_four_readings_apart(shop):
    stock = {"approved": True, "sku": SKU, "requested_qty": 1, "available_qty": 3, "orderable_ceiling": 8,
             "is_tracked": True, "reason_code": None, "target_date": None, "source": "stock.promise_decision"}
    decision = mock.Mock(available=3, expected=5, planned=8, available_qty=3)
    reader = port()
    with mock.patch("shopman.shop.services.availability.decide", return_value=stock), \
            mock.patch.object(ShopmanCommerceRead, "_stock_reading", return_value=decision):
        reading = reader.promise(CTX, SKU, Quantity(value="1", unit="unit"), "2026-11-19T12:00:00.000000Z")
    assert (reading.factual.value, reading.expected.value, reading.planned.value) == ("3", "5", "8")
    assert reading.promisable.value == {"approved": True, "reason": None, "orderable_ceiling": "8"}
    assert {reading.factual.source, reading.expected.source, reading.planned.source} == {
        "stockman:ready", "stockman:expected", "stockman:planned"}


def test_promise_without_ledger_is_unknown_never_unlimited(shop):
    """``available_qty=None`` no Stockman é "sem ledger": não se sabe, nunca "ilimitado"."""
    stock = {"approved": True, "sku": SKU, "available_qty": None, "orderable_ceiling": None, "is_tracked": False,
             "source": "stock.promise_decision"}
    decision = mock.Mock(available=0, expected=0, planned=0, available_qty=None)
    with mock.patch("shopman.shop.services.availability.decide", return_value=stock), \
            mock.patch.object(ShopmanCommerceRead, "_stock_reading", return_value=decision):
        reading = port().promise(CTX, SKU, Quantity(value="1", unit="unit"), "2026-11-19T12:00:00.000000Z")
    assert {reading.factual, reading.expected, reading.planned} == {Unknown(reason="not_supported")}
    assert isinstance(reading.promisable, Known) and reading.promisable.value["orderable_ceiling"] is None


def test_quote_seals_the_subject_cart_only(shop):
    terms = port().quote(CTX, "sess-1")
    assert terms.total.amount_minor == 900 and terms.items[0].ref == SKU and terms.hash
    assert terms.recipient.subject_ref == CTX.subject
    stranger = TrustedContext(tenant=CTX.tenant, environment="test", subject="conversation:2")
    for ctx, cart in ((stranger, "sess-1"), (CTX, "sess-2")):
        with pytest.raises(PortError) as refused:
            port().quote(ctx, cart)
        assert refused.value.code.value == "object_forbidden"


def test_quote_carries_the_day_and_the_window_of_the_cart(shop):
    """Passo 3 do pedido pelo motor: os termos dizem o dia e a janela combinados, não só o modo."""
    from datetime import datetime

    from django.utils import timezone

    Session.objects.filter(session_key="sess-1").update(
        data={"fulfillment_type": "pickup", "delivery_date": "2026-11-24", "delivery_time_slot": "slot-15"})
    terms = port().quote(CTX, "sess-1")
    start = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.get_current_timezone())
    assert terms.fulfillment.mode == "pickup"
    assert terms.fulfillment.window_start == start.astimezone(timezone.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert terms.fulfillment.window_end is None  # "a partir das 15h" não tem fim
    assert {c.code: c.value for c in terms.conditions} == {"fulfillment_date": "2026-11-24",
                                                          "fulfillment_window": "slot-15"}


def test_quote_without_a_day_has_no_window(shop):
    terms = port().quote(CTX, "sess-1")
    assert (terms.fulfillment.window_start, terms.conditions) == (None, ())


def test_customer_and_order_are_the_subject_only(shop):
    reader = port(ownership=Owns(orders=("ORD-1",)))
    assert reader.read_customer(CTX, "cust-1").value == {"ref": "cust-1"}  # só a referência sai (P17)
    for call in (lambda: reader.read_customer(CTX, "cust-2"), lambda: reader.read_order(CTX, "ORD-9")):
        with pytest.raises(PortError) as refused:
            call()
        assert refused.value.code.value == "object_forbidden"
    assert reader.read_order(CTX, "ORD-1") == Unknown(reason="not_found")


def test_without_ownership_nothing_personal_is_read(shop):
    reader = ShopmanCommerceRead(channel_ref=CHANNEL)
    assert isinstance(reader.ownership, DenyAll)
    with pytest.raises(PortError):
        reader.quote(CTX, "sess-1")


def test_declared_but_unsupported_operations_answer_honestly(shop):
    reader = port()
    assert set(reader.capabilities().unsupported) == {"knowledge", "scarcity"}
    assert reader.knowledge(CTX, "anything") == ()
    assert isinstance(reader.scarcity(CTX, SKU), Unavailable)
    assert reader.read_policy(CTX, "returns") == Unknown(reason="not_found")


def test_read_policy_states_only_the_house_hours(shop):
    """A política que a porta sabe afirmar é o horário, lido do calendário da casa; o resto não se sabe."""
    reader = ShopmanCommerceRead(channel_ref=CHANNEL)
    fact = ShopmanCommerceRead.read_policy(reader, CTX, "hours")
    assert isinstance(fact, Known) and fact.source == "shop:business_calendar"
    assert set(fact.value) == {"open", "opens", "closes"}
    for unknown in ("returns", "delivery_fee", ""):
        assert ShopmanCommerceRead.read_policy(reader, CTX, unknown) == Unknown(reason="not_found")
