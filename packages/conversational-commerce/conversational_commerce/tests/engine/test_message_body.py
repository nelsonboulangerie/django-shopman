"""O canal de verdade recebe o texto da mensagem pronta, pelo ``body_ref`` (#3198, peça 2).

O ``PreparedMessage`` leva ``body_ref="reply:<plano>"`` e o hash do conteúdo, e o ``ReplyPlan``
guarda as partes e o lastro, não o texto. O canal de teste não precisava do texto (só ecoa o
hash); um canal de verdade precisa. O ``Engine`` guarda o texto em ``bodies``, em memória e nunca
num registro, e o canal do adaptador o lê pelo ``body_ref``.
"""

from __future__ import annotations

import dataclasses

from conversational_commerce.contracts import ReplyPlan
from conversational_commerce.testing.fakes import FakeChannel

from .helpers import CTX, engine, message


class BodyChannel(FakeChannel):
    """Canal que envia o texto lido pelo ``body_ref``, como o adaptador de verdade faz."""

    def __init__(self, clock, bodies):
        super().__init__(clock)
        self.bodies, self.sent = bodies, []

    def send(self, ctx, prepared, idempotency_key):
        self.sent.append(self.bodies[prepared.body_ref])
        return super().send(ctx, prepared, idempotency_key)


def test_the_channel_sends_exactly_the_text_the_turn_composed():
    turn_engine, world = engine()
    bodies: dict[str, str] = {}
    channel = BodyChannel(world.clock, bodies)
    turn_engine = dataclasses.replace(turn_engine, bodies=bodies)
    turn_engine.ports.channel = channel

    result = turn_engine.turn(CTX, message("m1", "what are your hours?"))

    assert result.outcome == "answered"
    assert channel.sent == [result.text] == ["We are open from 08:00 to 18:00."]
    assert bodies == {f"reply:{result.reply.plan.id}": result.text}


def test_the_text_never_goes_into_a_record():
    turn_engine, world = engine()
    result = turn_engine.turn(CTX, message("m1", "what are your hours?"))
    plan = result.reply.plan
    assert isinstance(plan, ReplyPlan)
    assert result.text not in str(plan.to_document())  # o plano guarda partes e lastro, não a frase
