# ruff: noqa: F401, F811
"""OC-11: alterar o pedido já feito na conversa (Etapa III omnicanal, DEV-2026-085).

"Troca o horário", "tira um item", "troca o endereço" pela conversa inteira (ingresso sem
identificador de mensagem, o do ManyChat; leitura; executor; serviço do balcão de verdade).
O que se prova (N15 e os invariantes do §6):

- a Nice mostra o efeito (horário, item, endereço, taxa, total) e só aplica com o código da
  prévia (ADR-050), pelo MESMO ``order_edit`` do balcão, com o histórico "Pedido alterado
  pela Concierge a pedido do cliente" e UMA mensagem ao cliente (o aviso ``order_updated``
  não sai);
- X4: a mesma confirmação de novo não aplica duas vezes;
- X5: o pedido mudou entre a prévia e o código: o código antigo não aplica, e a prévia
  nova vem com outro código;
- a mesma elegibilidade do balcão (``order_edit.state_refusal``), caso a caso, com a recusa
  explicada; o dinheiro que o serviço não move sem gente (devolução, cobrança aberta) vai
  à equipe com o contexto;
- X1: a consulta só oferece a alteração que o serviço aceita agora; X3: nenhuma resposta
  traz endereço de API.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService

from shopman.shop.models import Conversation, ConversationMessage, DeliveryZone, Shop
from shopman.shop.services import order_composition, order_edit, stock
from shopman.storefront.concierge import order_amendment, tools
from shopman.storefront.tests import test_concierge_fechar_pedido as closing
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    FULL_TEXT,
    SKU,
    _geocode_text,
    conversation,
    customer,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_pix_e_cartao_na_conversa import _summary, shop

pytestmark = pytest.mark.django_db(transaction=True)

PAO_Q = 90
CROISSANT_Q = 1200


def _order(conversation, ref: str, *, pao: int = 3, croissant: int = 1, status=Order.Status.ACCEPTED,
           channel: str = CHANNEL, delivery: bool = False, **data) -> Order:
    """Um pedido do cliente da conversa, para amanhã, a pagar na retirada (nada recebido)."""
    day = timezone.localdate() + timedelta(days=1)
    lines = [("L1", SKU, "Pão Francês", pao, PAO_Q)]
    if croissant:
        lines.append(("L2", "CROISSANT", "Croissant", croissant, CROISSANT_Q))
    if delivery:
        lines.append(("FEE", order_edit.DELIVERY_FEE_SKU, "Taxa de entrega", 1, 500))
    total = sum(qty * price for _l, _s, _n, qty, price in lines)
    extra = {
        "fulfillment_type": "delivery",
        "delivery_address": "Rua Pará, 120 - Centro, Londrina - PR, CEP 86010-100",
        "delivery_address_structured": {
            "route": "Rua Pará", "street_number": "120", "neighborhood": "Centro", "city": "Londrina",
            "state_code": "PR", "postal_code": "86010-100", "complement": "", "latitude": -23.31, "longitude": -51.16,
            "formatted_address": "Rua Pará, 120 - Centro, Londrina - PR, CEP 86010-100",
        },
        "delivery_fee_q": 500,
        "delivery_time_slot": "slot-12",
    } if delivery else {"fulfillment_type": "pickup", "delivery_time_slot": "slot-12"}
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel,
        session_key=f"SESS-{ref}",
        status=status,
        handle_type="phone",
        handle_ref=conversation.phone,
        snapshot={"items": [
            {"line_id": line_id, "sku": sku, "name": name, "qty": qty, "unit_price_q": price,
             **({"meta": {"type": "delivery_fee", "non_production": True}} if sku.startswith("__") else {})}
            for line_id, sku, name, qty, price in lines
        ]},
        data={
            "customer_ref": conversation.customer_ref,
            "customer": {"ref": conversation.customer_ref, "phone": conversation.phone, "name": "Ana"},
            "payment": {"method": "cash"},
            "delivery_date": day.isoformat(),
            **extra,
            **data,
        },
        total_q=total,
    )
    for line_id, sku, name, qty, price in lines:
        OrderItem.objects.create(
            order=order, line_id=line_id, sku=sku, name=name, qty=qty, unit_price_q=price, line_total_q=qty * price,
            meta={"type": "delivery_fee", "non_production": True} if sku.startswith("__") else {},
        )
    if channel != "ifood":
        stock.hold(order)
    order.refresh_from_db()
    return order


def _turn(conversation, text, acts=()):
    return closing._turn(conversation, text, list(acts))


def _no_api(replies) -> None:
    assert not any("/api/" in text for text in replies), replies


def _code(reply: str) -> str:
    return closing._code(reply)


def _unchanged(order) -> bool:
    order.refresh_from_db()
    return not order.events.filter(type="order_edited").exists()


def _notices(order):
    return Directive.objects.filter(
        topic="notification.send", payload__order_ref=order.ref, payload__template="order_updated",
    )


# ── A fala ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "kind", "said"),
    [
        ("troca o horário do meu pedido para as 15h", order_amendment.RESCHEDULE, {"minutes": 900}),
        ("dá pra remarcar meu pedido pra amanhã?", order_amendment.RESCHEDULE, {}),
        ("tira o croissant do meu pedido", order_amendment.REMOVE_ITEM, {"item": "croissant"}),
        ("tira 1 pão francês da encomenda", order_amendment.REMOVE_ITEM, {"item": "pao frances", "qty": 1}),
        ("troca o endereço da entrega para Rua das Flores, 10, Centro", order_amendment.CHANGE_ADDRESS,
         {"address": "Rua das Flores, 10, Centro"}),
        ("quero mudar o endereço", order_amendment.CHANGE_ADDRESS, {"address": ""}),
        ("quero 2 croissant", None, {}),
        ("vou retirar amanhã às 15h", None, {}),
        ("tira o croissant", None, {}),
        ("que horas vocês abrem?", None, {}),
    ],
)
def test_the_speech_is_read_as_an_amendment_only_when_it_asks_for_one(text, kind, said):
    request = order_amendment.read(text)
    if kind is None:
        assert request is None, request
        return
    assert request is not None and request.kind == kind, request
    for key, value in said.items():
        assert getattr(request, key) == value, (key, request)


# ── N15: remarcar, com o código ──────────────────────────────────────


def test_n15_reschedule_shows_the_effect_applies_only_with_the_code_once(shop):
    order = _order(shop, "NB-AM-1")

    asked = _turn(shop, "troca o horário do meu pedido para as 15h")

    lines = asked[0].splitlines()
    assert lines[0] == tools.AMEND_PREVIEW_LEAD.format(ref=order.ref), asked
    assert "Retirada passa para amanhã, a partir das 15h." in lines, asked
    assert "Total: continua R$ 14,70." in lines, asked
    code = _code(asked[0])
    assert lines[-1] == tools.AMEND_CONFIRM.format(code=code)
    assert _unchanged(order) and order.data["delivery_time_slot"] == "slot-12", "a prévia não muda nada"

    done = _turn(shop, f"confirmo {code}")

    order.refresh_from_db()
    assert done[0].splitlines()[0] == tools.AMEND_DONE["applied"].format(ref=order.ref), done
    assert "Retirada passa para amanhã, a partir das 15h." in done[0].splitlines()
    assert order.data["delivery_time_slot"] == "slot-15"
    assert order.data["reschedule_history"][-1]["actor"] == order_amendment.ACTOR
    event = order.events.get(type="order_edited")
    assert event.payload["source"] == order_edit.CONCIERGE_AMEND_SOURCE and event.actor == order_amendment.ACTOR
    from shopman.backstage.projections.order_queue import _build_timeline

    assert order_amendment.HISTORY_NOTE in [row.label for row in _build_timeline(order)], "o Gestor lê quem alterou"
    assert not _notices(order).exists(), "uma mensagem só: a resposta da Nice"
    assert ConversationMessage.objects.filter(
        conversation=shop, kind="note", text__startswith=order_amendment.HISTORY_NOTE).count() == 1

    # X4: a mesma confirmação de novo (reenvio, ou o cliente repetindo) não aplica outra vez.
    again = _turn(shop, f"confirmo {code}")

    assert again == [tools.AMEND_DONE["already_applied"].format(ref=order.ref)], again
    assert order.events.filter(type="order_edited").count() == 1
    _no_api(asked + done + again)
    shop.refresh_from_db()
    assert shop.state == Conversation.State.ACTIVE


def test_a_plain_yes_or_a_wrong_code_asks_for_the_code_and_changes_nothing(shop):
    order = _order(shop, "NB-AM-2")
    code = _code(_turn(shop, "troca o horário do meu pedido para as 15h")[0])
    wrong = "0000" if code != "0000" else "1111"

    for text in ("sim", f"confirmo {wrong}"):
        reply = _turn(shop, text)
        assert reply == [tools.AMEND_CONFIRM.format(code=code)], (text, reply)
    assert _unchanged(order)

    assert _turn(shop, f"confirmo {code}")[0].startswith("Pronto, alterei")


def test_another_subject_in_the_middle_drops_the_question(shop):
    order = _order(shop, "NB-AM-3")
    code = _code(_turn(shop, "troca o horário do meu pedido para as 15h")[0])

    _turn(shop, "obrigada", [_act("thanks", "obrigada")])
    _turn(shop, f"confirmo {code}")

    assert _unchanged(order), "um código depois de outra fala não altera pedido"
    assert order_amendment.pending(Conversation.objects.get(pk=shop.pk)) is None


def test_reschedule_without_a_time_asks_with_the_grid_and_takes_the_choice(shop):
    order = _order(shop, "NB-AM-4")

    asked = _turn(shop, "quero trocar o horário do meu pedido")

    assert asked == ["Qual horário fica melhor para amanhã? 1) A partir das 9h; 2) A partir das 12h; 3) A partir das 15h"], asked
    preview = _turn(shop, "o 1")
    assert "Retirada passa para amanhã, a partir das 9h." in preview[0].splitlines(), preview
    _turn(shop, f"confirmo {_code(preview[0])}")
    order.refresh_from_db()
    assert order.data["delivery_time_slot"] == "slot-09"


def test_a_time_outside_the_grid_is_refused_with_the_true_reason(shop):
    order = _order(shop, "NB-AM-5")

    reply = _turn(shop, "troca o horário do meu pedido para as 7h")

    assert reply[0].startswith("Não tenho horário de retirada às 7h para amanhã."), reply
    assert "1) A partir das 9h" in reply[0]
    assert _unchanged(order)


# ── Tirar um item ─────────────────────────────────────────────────────


def test_remove_an_item_shows_the_new_total_and_applies_with_the_code(shop):
    order = _order(shop, "NB-AM-6")

    asked = _turn(shop, "tira o croissant do meu pedido")

    lines = asked[0].splitlines()
    assert "Sai do pedido: 1 Croissant." in lines, asked
    assert "Total: R$ 2,70 (era R$ 14,70)." in lines, asked
    done = _turn(shop, f"confirmo {_code(asked[0])}")

    assert done[0].startswith(tools.AMEND_DONE["applied"].format(ref=order.ref)), done
    order.refresh_from_db()
    assert [item.sku for item in order_composition.effective_items(order)] == [SKU]
    assert order_composition.effective_total_q(order) == 270
    _no_api(asked + done)


def test_remove_one_unit_lowers_the_line(shop):
    order = _order(shop, "NB-AM-7")

    asked = _turn(shop, "tira 1 pão francês do meu pedido")

    assert "Pão Francês passa de 3 para 2." in asked[0].splitlines(), asked
    _turn(shop, f"confirmo {_code(asked[0])}")
    order.refresh_from_db()
    assert {item.sku: int(item.qty) for item in order_composition.effective_items(order)} == {SKU: 2, "CROISSANT": 1}


def test_the_only_item_is_not_removed_the_way_out_is_said(shop):
    order = _order(shop, "NB-AM-8", croissant=0, pao=1)

    reply = _turn(shop, "tira o pão francês do meu pedido")

    assert reply == [tools.AMEND_REFUSED["empty_order"].format(ref=order.ref)], reply
    assert _unchanged(order)


# ── X5: termos defasados ──────────────────────────────────────────────


def test_x5_the_order_changed_after_the_preview_the_old_code_does_not_apply(shop):
    order = _order(shop, "NB-AM-9", pao=3)
    old = _code(_turn(shop, "tira o croissant do meu pedido")[0])
    # O balcão mexeu no pedido depois da prévia (mais um pão): o total da prévia mudou.
    order_edit.edit(order, lines=[{"line_id": "L1", "sku": SKU, "qty": 4}, {"line_id": "L2", "sku": "CROISSANT", "qty": 1}],
                    actor="balcao")

    stale = _turn(shop, f"confirmo {old}")

    order.refresh_from_db()
    lines = stale[0].splitlines()
    assert lines[0] == tools.AMEND_STALE.format(ref=order.ref), stale
    assert "Total: R$ 3,60 (era R$ 15,60)." in lines, stale
    fresh = _code(stale[0])
    assert fresh != old
    assert order.events.filter(type="order_edited").count() == 1, "só a do balcão: o código antigo não aplicou"

    _turn(shop, f"confirmo {fresh}")
    order.refresh_from_db()
    assert order_composition.effective_total_q(order) == 360


# ── A mesma elegibilidade do balcão ───────────────────────────────────


@pytest.mark.parametrize(
    ("status", "channel", "data", "code", "team"),
    [
        # Os casos de ``test_order_edit`` (pronto, encerrado, iFood, nota autorizada) e os
        # outros estados que a régua recusa.
        (Order.Status.READY, CHANNEL, {}, "order_not_editable", False),
        (Order.Status.DISPATCHED, CHANNEL, {}, "order_not_editable", False),
        (Order.Status.COMPLETED, CHANNEL, {}, "order_not_editable", False),
        (Order.Status.CANCELLED, CHANNEL, {}, "order_not_editable", False),
        (Order.Status.ACCEPTED, "ifood", {}, "marketplace_order", False),
        (Order.Status.ACCEPTED, CHANNEL, {"nfce_access_key": "4125" + "0" * 40}, "fiscal_authorized", True),
    ],
)
def test_same_eligibility_as_the_counter_refused_with_the_reason(shop, status, channel, data, code, team):
    order = _order(shop, "NB-EL-1", status=status, channel=channel, **data)
    assert order_edit.state_refusal(order)[0] == code, "a régua do balcão"

    reply = _turn(shop, "troca o horário do meu pedido para as 15h")

    expected = tools.AMEND_STATUS_REFUSED.get(str(status)) if code == "order_not_editable" else tools.AMEND_REFUSED[code]
    assert reply[0].startswith(expected.format(ref=order.ref)), reply
    assert _unchanged(order)
    shop.refresh_from_db()
    assert (shop.state == Conversation.State.HANDOFF) is team
    if team:
        assert tools.AMEND_TEAM_SUFFIX in reply[0]


# ── O dinheiro que o serviço não move sem gente ───────────────────────


def test_paid_order_that_gets_cheaper_goes_to_the_team_with_the_context(shop):
    order = _order(shop, "NB-AM-10")
    intent = PaymentService.settle(order.ref, 1470, "cash", idempotency_key=f"test:{order.ref}:cash")
    Order.objects.filter(pk=order.pk).update(data={**order.data, "payment": {"method": "cash", "intent_ref": intent.ref}})

    reply = _turn(shop, "tira o croissant do meu pedido")

    assert reply[0] == (
        f"{tools.AMEND_REFUSED['manager_approval_required'].format(ref=order.ref, amount='R$ 12,00')} "
        f"{tools.AMEND_TEAM_SUFFIX}"
    ), reply
    assert _unchanged(order)
    shop.refresh_from_db()
    assert shop.state == Conversation.State.HANDOFF
    assert shop.handoff_reason == (
        f"Cliente pediu para tirar um item no pedido {order.ref}: "
        f"{tools.AMEND_REFUSED['manager_approval_required'].format(ref=order.ref, amount='R$ 12,00')}"
    )


def test_open_pix_charge_keeps_the_value_and_goes_to_the_team(shop):
    summary = _summary(shop, "pix")
    closing._turn(shop, f"confirmo {closing._code(summary)}")
    order = Order.objects.get()

    reply = _turn(shop, "tira 1 pão francês do meu pedido")

    assert reply[0].startswith(tools.AMEND_REFUSED["open_digital_charge"].format(ref=order.ref)), reply
    assert _unchanged(order)
    shop.refresh_from_db()
    assert shop.state == Conversation.State.HANDOFF


# ── Trocar o endereço ─────────────────────────────────────────────────


def test_change_address_shows_the_fee_difference_and_applies(shop, monkeypatch):
    _geocode_text(monkeypatch, **FULL_TEXT)
    DeliveryZone.objects.create(shop=Shop.objects.get(), name="Centro", zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
                                match_value="860", fee_q=600)
    order = _order(shop, "NB-AM-11", delivery=True)

    asked = _turn(shop, "troca o endereço da entrega do meu pedido para Rua das Flores, 10, Centro, Londrina")

    lines = asked[0].splitlines()
    assert "Novo endereço: Rua das Flores, 10 - Centro, Londrina - PR, CEP 86010-000." in lines, asked
    assert "Taxa de entrega: R$ 6,00 (era R$ 5,00)." in lines, asked
    assert "Total: R$ 20,70 (era R$ 19,70)." in lines, asked
    assert "A pagar na entrega: R$ 20,70." in lines, "nada foi pago: o total novo fica para a porta"
    done = _turn(shop, f"confirmo {_code(asked[0])}")

    assert done[0].startswith(tools.AMEND_DONE["applied"].format(ref=order.ref)), done
    order.refresh_from_db()
    assert order.data["delivery_address_structured"]["route"] == "Rua das Flores"
    assert order.data["delivery_fee_q"] == 600
    _no_api(asked + done)


def test_pickup_order_has_no_address_to_change(shop):
    order = _order(shop, "NB-AM-12")

    reply = _turn(shop, "troca o endereço do meu pedido para Rua das Flores, 10")

    assert reply == [tools.AMEND_REFUSED["pickup_order"].format(ref=order.ref)], reply
    assert _unchanged(order)


# ── X1: a consulta oferece só o que o serviço aceita agora ────────────


def test_status_offers_only_the_amendments_the_service_takes_now(shop):
    _order(shop, "NB-AM-13")

    status = _turn(shop, "como está meu pedido?", [_act("order_status", "como está meu pedido?")])

    offer = tools.AMEND_OFFER.format(gestures="remarcar ou tirar um item")
    assert offer == "Se quiser remarcar ou tirar um item, é só me dizer."
    assert offer in status[0].splitlines(), status
    _no_api(status)


def test_status_of_an_order_with_an_open_pix_does_not_offer_to_remove(shop):
    summary = _summary(shop, "pix")
    closing._turn(shop, f"confirmo {closing._code(summary)}")

    status = _turn(shop, "como está meu pedido?", [_act("order_status", "como está meu pedido?")])

    lines = status[0].splitlines()
    assert tools.CONVERSATION_EQUIVALENTS["reschedule_order"] in lines, status
    assert not any("tirar um item" in line for line in lines), status


def test_change_address_without_the_address_asks_and_takes_the_answer(shop, monkeypatch):
    _geocode_text(monkeypatch, **FULL_TEXT)
    DeliveryZone.objects.create(shop=Shop.objects.get(), name="Centro", zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
                                match_value="860", fee_q=600)
    order = _order(shop, "NB-AM-14", delivery=True)

    asked = _turn(shop, "quero mudar o endereço do pedido")

    assert asked == [tools.AMEND_ASK["change_address"]], asked
    preview = _turn(shop, "Rua das Flores, 10, Centro, Londrina")
    assert "Taxa de entrega: R$ 6,00 (era R$ 5,00)." in preview[0].splitlines(), preview
    _turn(shop, f"confirmo {_code(preview[0])}")
    order.refresh_from_db()
    assert order.data["delivery_fee_q"] == 600


def test_remove_without_saying_which_asks_from_the_order_and_takes_the_choice(shop):
    order = _order(shop, "NB-AM-15")

    asked = _turn(shop, "quero tirar um item do meu pedido")

    assert asked == [f"Qual item sai do pedido {order.ref}? 1) 3 Pão Francês; 2) 1 Croissant"], asked
    preview = _turn(shop, "o 2")
    assert "Sai do pedido: 1 Croissant." in preview[0].splitlines(), preview


def test_an_item_not_in_the_order_is_said_with_what_the_order_has(shop):
    order = _order(shop, "NB-AM-16")

    reply = _turn(shop, "tira o brioche do meu pedido")

    assert reply == [f"Não achei brioche no pedido {order.ref}. O pedido tem: 3 Pão Francês; 1 Croissant."], reply
    assert _unchanged(order)
