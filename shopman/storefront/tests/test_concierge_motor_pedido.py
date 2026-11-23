# ruff: noqa: F401, F811
"""O pedido pela leitura da casa, dentro do motor do framework (passo "a" do plano de 22/11/2026).

O leitor do motor da Nice (``ports.LocalReader``) lê o pedido com a leitura da casa
(``order_talk``) quando ela entende a fala inteira, e entrega o que o ``change_cart`` do framework
pede: o SKU e a quantidade ABSOLUTA. O motor, em sombra, escolhe o ``change_cart``. O pedido só
sai pelo motor quando a classe "pedido" estiver ligada E houver molde da Nice para ele (passo "c").
"""

from __future__ import annotations

import pytest
from conversational_commerce.engine.acts import ACTS
from conversational_commerce.ports import InterpretRequest, ModelRequest, TrustedContext

from shopman.storefront.concierge import turn_framework
from shopman.storefront.concierge.ports import LocalReader, subject_of
from shopman.storefront.tests.test_concierge_engine import _create_inbound, conversation, customer, outbox, surface
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _cart, _turn, menu
from shopman.storefront.tests.test_concierge_turn_framework import _channel

pytestmark = pytest.mark.django_db


def _read(conversation, text):
    ctx = TrustedContext(tenant="nelson-boulangerie", environment="shadow", subject=subject_of(conversation.pk))
    request = InterpretRequest(request=ModelRequest(purpose="interpret", data_class="redacted",
                                                    budget={"max_calls": 1, "max_spend": {
                                                        "amount_minor": 0, "currency": "BRL"}}),
                               event_id="evt-motor", content_ref=f"text:{text}", allowed_acts=ACTS)
    understanding, consumption = LocalReader().interpret(ctx, request)
    assert consumption.calls == 0  # a leitura da casa não chama modelo
    return [(a.act, dict(a.fields)) for a in understanding.acts]


def test_an_order_read_whole_by_the_house_gives_sku_and_absolute_quantity(conversation, menu):
    assert _read(conversation, "quero 2 croissants pra retirar amanhã às 16h") == [
        ("change_quantity", {"item": "CROISSANT", "quantity": "2"})]
    assert _read(conversation, "queria 2 croissants e 3 pain au chocolat") == [
        ("change_quantity", {"item": "CROISSANT", "quantity": "2"}),
        ("change_quantity", {"item": "PAIN-CHOCO", "quantity": "3"})]


def test_more_two_is_the_cart_plus_two_because_the_framework_only_takes_absolute(conversation, outbox, menu):
    _turn(conversation, "quero 2 croissant", [_act("order", "quero 2 croissant", "croissant", 2)])
    assert _cart(conversation) == {"CROISSANT": 2}

    assert _read(conversation, "mais 2 croissant") == [("change_quantity", {"item": "CROISSANT", "quantity": "4"})]
    assert _read(conversation, "tira o croissant") == [("change_quantity", {"item": "CROISSANT", "quantity": "0"})]


def test_what_the_house_does_not_understand_whole_goes_by_the_local_split(conversation, menu):
    acts = _read(conversation, "quero 2 croissant e o de ontem veio queimado")
    # A casa não decide: a divisão local devolve o que sobrou como desconhecido, e o motor não
    # trata a fala como um pedido limpo.
    assert "unknown" in [name for name, _ in acts]


def _order_line_approved(monkeypatch):
    """A linha P08 aprovada SÓ no teste: no ar, aprovar é decisão do dono."""
    import dataclasses

    from shopman.storefront.concierge import profile, profile_lines

    line = profile_lines.BY_LINE_ID["commerce.order_in_conversation"]
    approved = dataclasses.replace(line, state="approved", decided_at="2026-11-22T00:00:00.000000Z")
    monkeypatch.setattr(profile_lines, "LINES",
                        tuple(approved if x.line_id == line.line_id else x for x in profile_lines.LINES))
    monkeypatch.setattr(profile_lines, "BY_LINE_ID", {**profile_lines.BY_LINE_ID, line.line_id: approved})
    monkeypatch.setattr(profile, "LINES", profile_lines.LINES)  # o ``profile`` importa o nome


def _shadow(conversation, text, key):
    message = _create_inbound(conversation, text, key)
    shadow = turn_framework.build_engine(conversation, environment="shadow", channel=_channel())
    ctx = TrustedContext(tenant=shadow.profile.tenant, environment="shadow", subject=shadow.ports.clock.ctx.subject)
    return shadow, shadow.turn(ctx, turn_framework._raw(message))


def _candidate(result, move):
    return next(c for record in result.decisions for c in record.candidates if c.move == move)


def test_the_order_line_still_waits_for_the_owner_so_change_cart_is_blocked(conversation, menu):
    _shadow_engine, result = _shadow(conversation, "quero 2 croissants", "motor-1")

    candidate = _candidate(result, "change_cart")
    assert dict(candidate.content) == {"item": "CROISSANT", "quantity": "2"}  # a leitura chegou inteira
    assert not candidate.eligible and "profile_line_not_approved" in candidate.blocked_by
    assert "change_cart" not in result.chosen_moves


def test_with_the_order_line_approved_the_engine_chooses_change_cart_for_the_first_order(conversation, menu,
                                                                                     monkeypatch):
    _order_line_approved(monkeypatch)
    shadow, result = _shadow(conversation, "quero 2 croissants", "motor-2")

    assert "change_cart" in result.chosen_moves, result.chosen_moves  # sem sacola ainda: a sacola nova
    assert isinstance(shadow.ports.model, LocalReader)  # a casa leu: a porta do leitor não chama modelo
    verdict = turn_framework.judge(result, enabled=frozenset({"order"}), approved=frozenset(shadow.house_templates))
    # Sem molde da Nice para o pedido (passo "c"), o turno fica no caminho de hoje: na sombra o
    # efeito não roda, e o ``change_cart.done`` da casa ainda não existe.
    assert not verdict.eligible and verdict.moves == ("change_cart",)
