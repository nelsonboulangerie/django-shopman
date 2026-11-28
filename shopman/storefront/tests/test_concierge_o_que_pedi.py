# ruff: noqa: F401, F811
""""O que pedi" é a sacola de agora; status de pedido sem "Total: ." (ensaio do dono, 21/11/2026).

No ensaio, "as 2 baguettes que pedi" trouxe "Pedido NB-261117-R44: Preparando…. … Total: .", um
pedido de 17/11, com o total vazio e reticências com ponto. E toda sacola mostrada termina com o
próximo passo: a conferência antes do envio achou "sua sacola ficou assim ... Total" sem saída.
"""

from __future__ import annotations

import pytest

from shopman.storefront.concierge import tools
from shopman.storefront.tests.test_concierge_engine import conversation, customer, outbox, surface
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _cart, _turn, menu

pytestmark = pytest.mark.django_db

NEXT = "Quer mais alguma coisa? Quando terminar, é só escrever “pode fechar”."


def test_status_line_has_the_date_no_double_period_and_no_empty_total():
    text = tools.render_result("order_status", {"ok": True, "orders": [{
        "order_ref": "NB-261117-R44", "title": "Preparando…", "message": "", "total": "",
        "created_at": "17/11 10:00", "tracking_url": "https://loja/pedido/NB-261117-R44", "actions": [],
    }]})
    first = text.splitlines()[0]
    assert first == "Pedido NB-261117-R44, de 17/11 10:00: Preparando…"
    assert "…." not in text and "Total: ." not in text


def test_status_line_with_total_and_message():
    text = tools.render_result("order_status", {"ok": True, "orders": [{
        "order_ref": "W29", "title": "Pronto para retirar", "message": "Pode passar no balcão", "total": "R$ 24,00",
        "created_at": "21/11 09:10", "tracking_url": "https://loja/pedido/W29", "actions": [],
    }]})
    assert text.splitlines()[0] == "Pedido W29, de 21/11 09:10: Pronto para retirar. Pode passar no balcão. Total: R$ 24,00."


def test_what_i_ordered_with_an_open_cart_is_the_cart_now(conversation, outbox, menu):
    _turn(conversation, "quero 2 croissant", [_act("order", "quero 2 croissant", "croissant", 2)])

    reply = _turn(conversation, "as 2 croissants que pedi", [_act("order_status", "as 2 croissants que pedi")])

    assert reply.startswith("Sua sacola de agora:"), reply
    assert "2 × " in reply and "Total:" in reply and reply.endswith(NEXT)
    assert "Pedido " not in reply


def test_every_cart_shown_ends_with_the_next_step(conversation, outbox, menu):
    reply = _turn(conversation, "quero 2 croissant", [_act("order", "quero 2 croissant", "croissant", 2)])
    assert reply.startswith("Pronto, sua sacola ficou assim:") and reply.endswith(NEXT), reply
