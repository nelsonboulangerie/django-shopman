"""A casa com voz própria nunca fala com a voz do pacote (#3410).

Com ``house_voice_only``, a parte por molde que a casa não assina segura a mensagem
(``template_not_in_voice``): no ar, depois do efeito, onde a sombra não vê. Sem a opção, nada muda.
"""

from __future__ import annotations

import dataclasses

from conversational_commerce.reply import TEMPLATES_BY_ID
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine

PIX = JourneyStep(message=j4.message("pix", "pix"),
                  understanding={"acts": [{"act": "choose_payment", "fields": {"method": "pix"}}]},
                  expect_moves=(), expect_text=(), advance_seconds=30)


def _world():
    world = FakeWorld()
    world.state.payment_methods = ("pix", "card")
    return world


def _voiced(house_ids, *, only=True):
    turn_engine, world = engine(steps=(PIX,), world=_world())
    house = {template_id: dataclasses.replace(TEMPLATES_BY_ID[template_id], version="house")
             for template_id in house_ids}
    return dataclasses.replace(turn_engine, house_templates=house, house_voice_only=only), world


def test_a_part_outside_the_house_voice_holds_the_message_after_the_effect():
    voiced, world = _voiced(())
    result = voiced.turn(CTX, PIX.message)
    assert [c.action for c in result.commands] == ["set_payment"]  # o efeito aconteceu
    assert result.reply.verification.result == "hold" and result.text is None  # e nada sai na voz do pacote
    assert any(f.code == "template_not_in_voice" for f in result.reply.verification.findings)


def test_a_part_in_the_house_voice_goes_out():
    voiced, world = _voiced(("set_payment.done",))
    result = voiced.turn(CTX, PIX.message)
    assert result.reply.verification.result != "hold" and result.text


def test_without_the_option_the_package_voice_is_allowed():
    voiced, world = _voiced((), only=False)
    assert voiced.turn(CTX, PIX.message).text.startswith("Done: payment by pix.")
