# ruff: noqa: F401, F811
"""OC-05: Pix e cartão como ações de conversa (Etapa III omnicanal, DEV-2026-085).

O laudo da Etapa II (T2) mediu o rótulo que mente: na consulta, "Copiar código Pix"
apontava para a página do pedido, porque a ação ``copy_pix`` não tinha o que copiar e a
Nice caía no link de acompanhamento. E o cartão só ganhava o link do gateway na consulta,
nunca no pedido. Aqui, pela conversa inteira (ingresso, leitura em partes, executor e
commit de verdade):

- X3: a ação ``copy_pix`` entrega o código, não um link;
- N10: o Pix na conversa no pedido, sozinho na mensagem seguinte;
- N11: "manda o Pix de novo" devolve o código, não o link;
- N12: no pedido com cartão, o link do gateway já sai no pedido.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent

from shopman.storefront.concierge import tools
from shopman.storefront.tests import test_concierge_engine as fixtures
from shopman.storefront.tests import test_concierge_fechar_pedido as closing
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _create_inbound,
    _listed,
    _reclaim,
    conversation,
    customer,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act

pytestmark = pytest.mark.django_db(transaction=True)

CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_oc05"
STATUS_PIX_AGAIN = [_act("order_status", "manda o pix de novo")]


@pytest.fixture
def shop(conversation, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr("shopman.storefront.concierge.intents._model", lambda: "modelo-de-teste")
    monkeypatch.setattr(
        "shopman.storefront.concierge.transport.send_for",
        lambda binding, text: fixtures.SendOutcome("accepted", "accepted", f"test:{binding.subject}:{text[:8]}"),
    )
    _listed("CROISSANT", "Croissant", description="Folhado amanteigado", stock="50")
    return conversation


def _summary(conversation, payment: str) -> str:
    """Do pedido ao resumo com o código, como o cliente fala; ``payment`` é a resposta à forma."""
    closing._bag(conversation)
    closing._say(conversation, "pode fechar")
    closing._say(conversation, "amanhã")
    closing._say(conversation, "vou retirar")
    asked = closing._say(conversation, "às 13h")
    assert asked == "Como você prefere pagar? 1) Pix; 2) Cartão (link seguro)", asked
    return closing._say(conversation, payment)


def _no_copy_link(text: str) -> None:
    """X3: nenhuma linha com o rótulo da cópia apontando para um link."""
    for line in text.splitlines():
        assert not ("Copiar" in line and "http" in line), line


def test_x3_copy_pix_action_carries_the_code_and_the_reply_never_links_it(shop):
    summary = _summary(shop, "pix")
    closing._turn(shop, f"confirmo {closing._code(summary)}")
    order = Order.objects.get()
    pix = order.data["payment"]["copy_paste"]

    ctx = tools.ToolContext(conversation=shop, channel_ref=shop.channel_ref)
    _create_inbound(shop, "manda o pix de novo", "oc05-x3-status")
    _reclaim(ctx)
    result = tools.order_status(ctx, order.ref)

    action = next(a for a in result["orders"][0]["actions"] if a["ref"] == "copy_pix")
    assert action["kind"] == "copy" and action["value"] == pix and action["href"] == ""
    assert tools.copy_texts(result) == [pix]
    rendered = tools.render_result("order_status", result)
    _no_copy_link(rendered)
    assert tools.PIX_CODE_FOLLOWS in rendered or "Mando de novo na próxima mensagem." in rendered
    assert pix not in rendered, "o código vai sozinho na mensagem seguinte, não no meio do texto"


def test_n10_the_pix_goes_in_its_own_message_when_the_order_is_placed(shop):
    summary = _summary(shop, "pix")

    placed = closing._turn(shop, f"confirmo {closing._code(summary)}")

    order = Order.objects.get()
    pix = order.data["payment"]["copy_paste"]
    assert placed[0].startswith(f"Pedido {order.ref} registrado."), placed
    assert tools.PIX_CODE_FOLLOWS in placed[0], placed
    assert placed[1:] == [pix], "o código Pix numa mensagem só dele"
    _no_copy_link(placed[0])


def test_n11_pix_again_later_returns_the_code_not_a_link(shop):
    summary = _summary(shop, "pix")
    closing._turn(shop, f"confirmo {closing._code(summary)}")
    order = Order.objects.get()
    pix = order.data["payment"]["copy_paste"]

    again = closing._turn(shop, "manda o pix de novo", STATUS_PIX_AGAIN)

    assert len(again) == 2, again
    assert again[0].startswith(f"Pedido {order.ref}"), again
    _no_copy_link(again[0])
    lines = again[0].splitlines()
    assert len(lines) == len(set(lines)), "nenhuma linha duplicada"
    # Com o OC-10, o que já foi e o que vem numa linha só: "Já te mandei o código Pix por
    # aqui às HHhMM. Mando de novo na próxima mensagem."
    sent = [line for line in lines if line.startswith("Já te mandei o código Pix por aqui ")]
    assert len(sent) == 1 and sent[0].endswith(" Mando de novo na próxima mensagem."), lines
    assert tools.PIX_CODE_FOLLOWS not in lines, "o aviso do código não se repete"
    assert again[1] == pix, "o código, sozinho, para copiar no WhatsApp"
    # X3 também para os comandos: cancelar é instrução de conversa, nunca endereço de API.
    assert not any("/api/" in text for text in again), again
    assert any(line.startswith("Posso ") and "cancelar, se quiser." in line for line in lines), again
    from shopman.shop.services import order_view_link

    assert f"Acompanhar: {order_view_link.path_for(order)}" in again[0].splitlines()[-1], again
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1, "consultar não cria outra cobrança"


def test_n12_card_order_prints_the_gateway_link_at_placement(shop, settings, monkeypatch):
    settings.SHOPMAN_PAYMENT_ADAPTERS = {
        **settings.SHOPMAN_PAYMENT_ADAPTERS,
        "card": "shopman.shop.adapters.payment_stripe",
    }
    stripe = MagicMock()
    session = MagicMock(id="cs_test_oc05", url=CHECKOUT_URL, payment_intent=None, status="open")
    stripe.checkout.Session.create.return_value = session
    stripe.checkout.Session.retrieve.return_value = session
    monkeypatch.setattr("shopman.shop.adapters.payment_stripe._get_stripe", lambda: stripe)
    summary = _summary(shop, "cartão")
    assert "Pagamento: Cartão (link seguro)." in summary, summary

    placed = closing._turn(shop, f"confirmo {closing._code(summary)}")

    order = Order.objects.get()
    assert order.data["payment"]["method"] == "card"
    assert order.data["payment"]["checkout_url"] == CHECKOUT_URL
    assert placed[0].startswith(f"Pedido {order.ref} registrado."), placed
    assert f"Pagar com cartão: {CHECKOUT_URL}" in placed[0].splitlines(), placed
    assert len(placed) == 1, "no cartão não há código para copiar"


def test_x3_command_actions_become_conversation_or_vanish_and_pages_stay_links():
    """Pela natureza do destino: página abre como link; comando (POST/API) vira a frase da
    conversa quando a Nice sabe fazer, e some quando não sabe. Nunca ``/api/`` na resposta."""
    def action(ref, kind, href="", method="", label="Rótulo"):
        return {"ref": ref, "kind": kind, "label": label, "href": href, "method": method, "enabled": True}

    result = {"ok": True, "orders": [{
        "order_ref": "ORD-1", "title": "Recebemos seu pedido", "message": "", "total": "R$ 10,00",
        "tracking_url": "https://loja.example/pedido/ORD-1/",
        "actions": [
            action("cancel_order", "mutation", "/api/v1/orders/ORD-1/cancel/", "POST", "Cancelar pedido"),
            action("rate_order", "mutation", "/api/v1/orders/ORD-1/rating/", "POST", "Avaliar pedido"),
            action("api_get", "link", "https://loja.example/api/v1/orders/ORD-1/", "GET", "Ver dados"),
            action("pay_card", "external", CHECKOUT_URL, "", "Pagar com cartão"),
            action("track_courier", "external", "https://entregas.example/r/abc", "", "Ver o entregador"),
            action("no_href", "link", "", "", "Sem destino"),
        ],
    }]}

    rendered = tools.render_result("order_status", result)
    lines = rendered.splitlines()

    assert "/api/" not in rendered, rendered
    assert tools.CONVERSATION_EQUIVALENTS["cancel_order"] in lines
    assert "Avaliar pedido" not in rendered and "Ver dados" not in rendered and "Sem destino" not in rendered
    assert f"Pagar com cartão: {CHECKOUT_URL}" in lines
    assert "Ver o entregador: https://entregas.example/r/abc" in lines
    assert lines[-1] == "Acompanhar: https://loja.example/pedido/ORD-1/"
