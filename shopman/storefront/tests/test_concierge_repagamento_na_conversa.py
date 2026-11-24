# ruff: noqa: F401, F811
"""OC-12: pagar de novo e trocar a forma na conversa (Etapa III omnicanal, DEV-2026-085).

A J4 do pagamento ("manda outro Pix", "o Pix venceu", "quero pagar com Pix") pela conversa
inteira (ingresso, leitura em partes, executor e serviço de pagamento de verdade). A Nice
só faz o que a página do pedido oferece agora (X1), pelo mesmo serviço do botão:

- a cobrança que não nasceu é refeita (``check_payment``, o "Tentar novamente"), com o
  código novo em mensagem própria e UMA cobrança vigente, mesmo pedindo duas vezes (X4);
- o cartão recusado vira Pix (``switch_declined_card_to_pix``, o "Pagar com Pix");
- Pix por cartão, cartão por Pix sem recusa, forma que o canal não aceita, pedido pago,
  cancelado ou com o prazo de pagar vencido: a recusa com o motivo, sem cobrança nova;
- nenhuma resposta traz endereço de API (X3).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.adapters.payment_types import PaymentResult
from shopman.shop.models import Channel, Conversation
from shopman.shop.services import payment as payment_service
from shopman.storefront.concierge import tools
from shopman.storefront.tests import test_concierge_fechar_pedido as closing
from shopman.storefront.tests.test_concierge_engine import CHANNEL, conversation, customer, surface
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_pix_e_cartao_na_conversa import CHECKOUT_URL, _no_copy_link, _summary, shop

pytestmark = pytest.mark.django_db(transaction=True)


def _pix_order(conversation) -> Order:
    summary = _summary(conversation, "pix")
    closing._turn(conversation, f"confirmo {closing._code(summary)}")
    return Order.objects.get()


def _status(conversation, text):
    return closing._turn(conversation, text, [_act("order_status", text)])


def _live_intents(order) -> list[PaymentIntent]:
    return list(PaymentIntent.objects.filter(order_ref=order.ref, status__in=["pending", "authorized"]))


def _no_api(replies) -> None:
    assert not any("/api/" in text for text in replies), replies


class _CardGateway:
    """O Stripe do teste: o cartão não foi pago, e a anulação passa."""

    def check_gateway_status(self, intent_ref):
        return "declined"

    def cancel(self, intent_ref, **config):
        return PaymentResult(success=True)


def _route_card_to(gateway):
    original = payment_service._adapter_for_persisted_intent

    def route(intent_ref, *, method):
        return gateway if str(method).lower() == "card" else original(intent_ref, method=method)

    return patch.object(payment_service, "_adapter_for_persisted_intent", side_effect=route)


def _card_order(order, *, declined: bool) -> PaymentIntent:
    """O pedido passa a ser de cartão, com o link aberto (e a última tentativa recusada)."""
    for intent in _live_intents(order):
        PaymentService.cancel(intent.ref, reason="test_card")
    card = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="card")
    payment = {
        "method": "card",
        "intent_ref": card.ref,
        "idempotency_key": "oc12-card",
        "checkout_url": CHECKOUT_URL,
        "expires_at": (timezone.now() + timedelta(minutes=30)).isoformat(),
    }
    if declined:
        payment["last_decline"] = {"code": "card_declined", "at": timezone.now().isoformat()}
    Order.objects.filter(pk=order.pk).update(data={**order.data, "payment": payment})
    return card


def _accepts(methods):
    channel = Channel.objects.get(ref=CHANNEL)
    channel.config = {**channel.config, "payment": {**channel.config["payment"], "method": methods}}
    channel.save(update_fields=["config"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("o pix venceu, manda outro", "pix"),
        ("manda o pix de novo", "pix"),
        ("o cartão não passou, quero pagar com pix", "pix"),
        ("troca o pix pelo cartão", "card"),
        ("dá pra tentar pagar de novo?", ""),
        ("cadê o meu pedido?", None),
        ("vocês aceitam pix?", None),
    ],
)
def test_payment_request_reads_the_ask_and_the_form(text, expected):
    assert tools.payment_request(text) == expected


def test_the_order_read_from_the_domain_is_a_receipt_for_registered():
    """"Seu pedido está registrado" (a frase da página na cobrança que não nasceu) é fato
    quando a consulta ou a cobrança refeita leram o pedido; sem pedido achado, não é (R6)."""
    from shopman.storefront.concierge import house_rules
    from shopman.storefront.concierge.turn_outcome import TurnOutcome

    def receipts(*events):
        return house_rules.receipts_for(TurnOutcome(reply_text="", tool_events=list(events)))

    assert receipts({"name": "order_status", "ok": True, "order_found": True}) == {house_rules.ORDER}
    assert receipts({"name": "repay_order", "ok": True, "order_found": True}) == {house_rules.ORDER}
    assert receipts({"name": "order_status", "ok": True, "order_found": False}) == frozenset()
    assert receipts({"name": "order_status", "ok": True}) == frozenset()


def test_pix_that_was_not_born_is_regenerated_once_and_the_code_comes_alone(shop):
    order = _pix_order(shop)
    # A cobrança refeita falhou no gateway (o que ``payment.initiate`` grava quando o
    # ``create_intent`` levanta): sem código, com o erro, e a anterior já fechada.
    for intent in _live_intents(order):
        PaymentService.cancel(intent.ref, reason="test_retired")
    Order.objects.filter(pk=order.pk).update(
        data={**order.data, "payment": {"method": "pix", "error": "gateway fora do ar"}}
    )
    assert not _live_intents(order)
    before = PaymentIntent.objects.filter(order_ref=order.ref).count()
    # A consulta oferece o "Tentar novamente" como conversa, nunca como endereço de API.
    asked = _status(shop, "como está meu pedido?")
    assert tools.CONVERSATION_EQUIVALENTS["retry_payment"] in asked[0].splitlines(), asked
    _no_api(asked)

    again = _status(shop, "o pix não veio, manda outro")

    order.refresh_from_db()
    pix = order.data["payment"]["copy_paste"]
    assert pix, order.data["payment"]
    assert again[0].startswith(tools.REPAY_DONE["retried"].format(ref=order.ref)), again
    assert tools.PIX_CODE_FOLLOWS in again[0].splitlines(), again
    assert again[1:] == [pix], "o código novo, sozinho na mensagem seguinte"
    _no_copy_link(again[0])
    _no_api(again)
    assert len(_live_intents(order)) == 1

    # X4: pedir de novo devolve o MESMO código, sem outra cobrança.
    twice = _status(shop, "manda outro pix")

    assert twice[1:] == [pix], twice
    assert not twice[0].startswith("Pronto"), "nada foi refeito: o Pix de pé é o mesmo"
    assert [intent.ref for intent in _live_intents(order)] == [order.data["payment"]["intent_ref"]]
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == before + 1


def test_declined_card_becomes_pix_in_the_conversation_without_calling_the_team(shop):
    order = _pix_order(shop)
    card = _card_order(order, declined=True)
    asked = _status(shop, "como está meu pedido?")
    assert tools.CONVERSATION_EQUIVALENTS["pay_with_pix"] in asked[0].splitlines(), asked
    assert f"Pagar com cartão: {CHECKOUT_URL}" in asked[0].splitlines(), asked
    _no_api(asked)

    text = "o cartão não passou, quero pagar com pix"
    with _route_card_to(_CardGateway()):
        switched = closing._turn(shop, text, [_act("complaint", text)])

    order.refresh_from_db()
    pix = order.data["payment"]["copy_paste"]
    assert order.data["payment"]["method"] == "pix" and pix
    assert switched[0].startswith(tools.REPAY_DONE["switched_to_pix"].format(ref=order.ref)), switched
    assert tools.PIX_CODE_FOLLOWS in switched[0].splitlines(), switched
    assert switched[1:] == [pix], switched
    _no_api(switched)
    assert PaymentService.get(card.ref).status == "cancelled"
    assert [intent.method for intent in _live_intents(order)] == ["pix"]
    shop.refresh_from_db()
    assert shop.state == Conversation.State.ACTIVE, "a Nice resolveu: a equipe não foi chamada"

    # Pedir Pix de novo não troca nada outra vez (X4).
    twice = _status(shop, "manda o pix de novo")
    assert twice[1:] == [pix], twice
    assert len(_live_intents(order)) == 1


def test_pix_to_card_is_refused_with_the_reason_and_the_pix_stays(shop):
    order = _pix_order(shop)
    pix = order.data["payment"]["copy_paste"]

    refused = _status(shop, "quero pagar com cartão")

    assert refused[0].splitlines()[0] == tools.REPAY_REFUSED["pix_to_card"], refused
    assert refused[1:] == [pix], "o Pix que vale continua, para pagar"
    assert len(_live_intents(order)) == 1
    _no_api(refused)


def test_card_the_channel_does_not_take_is_refused(shop):
    order = _pix_order(shop)
    _accepts(["pix"])

    refused = _status(shop, "quero pagar com cartão")

    assert refused[0].splitlines()[0] == "Por aqui, não aceitamos pagamento com cartão.", refused
    assert len(_live_intents(order)) == 1


def test_card_not_declined_does_not_switch_to_pix_and_keeps_the_gateway_link(shop):
    order = _pix_order(shop)
    card = _card_order(order, declined=False)

    refused = _status(shop, "quero pagar com pix")

    assert refused[0].splitlines()[0] == tools.REPAY_REFUSED["card_to_pix_after_decline"], refused
    assert f"Pagar com cartão: {CHECKOUT_URL}" in refused[0].splitlines(), refused
    assert len(refused) == 1
    order.refresh_from_db()
    assert order.data["payment"]["method"] == "card"
    assert [intent.ref for intent in _live_intents(order)] == [card.ref]


def test_paid_order_refuses_with_the_reason(shop):
    order = _pix_order(shop)
    assert payment_service.mock_confirm(order) is True

    refused = _status(shop, "manda o pix de novo")

    assert refused[0].splitlines()[0] == tools.REPAY_REFUSED["already_paid"].format(ref=order.ref), refused
    assert len(refused) == 1, "pedido pago não recebe código"
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1


def test_pix_past_its_deadline_is_not_reborn_the_order_is_cancelled_and_said(shop):
    order = _pix_order(shop)
    payment = {**order.data["payment"], "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat()}
    Order.objects.filter(pk=order.pk).update(data={**order.data, "payment": payment})

    refused = _status(shop, "o pix venceu, manda outro")

    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    expected = f"{tools.REPAY_REFUSED['payment_expired_cancelled']} {tools.OLD_PIX_CODE_WARNING}"
    assert refused[0].splitlines()[0] == expected.format(ref=order.ref), refused
    assert len(refused) == 1, "nenhum código: o Pix vencido não se paga"
    assert not _live_intents(order)
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1


def test_cancelled_order_refuses_with_the_reason(shop):
    from shopman.shop.services import customer_orders

    order = _pix_order(shop)
    assert customer_orders.cancel(order) is True

    refused = _status(shop, "manda o pix de novo")

    assert refused[0].splitlines()[0] == tools.REPAY_REFUSED["order_cancelled"].format(ref=order.ref), refused
    assert len(refused) == 1
    assert not _live_intents(order)
    assert tools.REPEAT_OFFER not in refused[0], "só o pedido vencido sem pagamento é oferecido de novo"


# ── Variante "oferecer" (OC-12): o pedido vencido pode ser remontado ─────


def _expired(conversation) -> Order:
    order = _pix_order(conversation)
    payment = {**order.data["payment"], "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat()}
    Order.objects.filter(pk=order.pk).update(data={**order.data, "payment": payment})
    return order


@pytest.mark.parametrize(
    ("text", "offered", "expected"),
    [
        ("monta de novo", False, True),
        ("pode repetir o pedido", False, True),
        ("sim", True, True),
        ("sim", False, False),
        ("manda o pix de novo", False, False),
    ],
)
def test_asks_to_repeat_reads_the_phrase_or_the_yes_to_the_offer(text, offered, expected):
    assert tools.asks_to_repeat(text, offered=offered) is expected


def test_expired_order_is_offered_and_rebuilt_in_the_bag_at_todays_price_with_a_new_confirmation(shop):
    from shopman.offerman.models import ListingItem

    from shopman.storefront.tests.test_concierge_engine import SKU

    order = _expired(shop)
    refused = _status(shop, "o pix venceu, manda outro")
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert tools.REPEAT_OFFER in refused[0].splitlines(), refused
    # O preço de agora, não o do pedido vencido.
    ListingItem.objects.filter(product__sku=SKU, listing__ref=CHANNEL).update(price_q=120)

    rebuilt = closing._say(shop, "sim")

    assert rebuilt.startswith(tools.REPEAT_DONE.format(ref=order.ref)), rebuilt
    assert "2,40" in rebuilt and "1,80" not in rebuilt, rebuilt
    assert rebuilt.splitlines()[-1].endswith("“pode fechar”."), rebuilt
    assert Order.objects.count() == 1, "remontar não faz pedido: o pedido novo pede o fechamento e o código"
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
    # A confirmação nova: o fechamento de sempre, desde o dia.
    assert closing._say(shop, "pode fechar") == "Para quando é o pedido? Hoje, amanhã ou outro dia (dia/mês)?"


def test_yes_without_the_offer_rebuilds_nothing(shop):
    from shopman.orderman.models import Session

    _expired(shop)
    _status(shop, "como está meu pedido?")

    closing._say(shop, "sim")

    shop.refresh_from_db()
    sessions = Session.objects.filter(session_key=shop.session_key) if shop.session_key else []
    assert all(not session.items for session in sessions)
