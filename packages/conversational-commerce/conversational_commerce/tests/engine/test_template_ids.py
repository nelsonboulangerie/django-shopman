"""A resposta composta diz qual molde compôs cada parte (pré-requisito do N9a).

O adaptador decide por MOLDE se o turno sai pelo motor: classe sem molde da casa com a frase de
hoje fica no caminho antigo (decisão de 22/11/2026). O motor escolhe o molde dentro do turno
(``moves[x].reply``); sem o registro, o adaptador não teria como saber qual saiu. O registro não
muda texto, lastro nem verificação.
"""

from __future__ import annotations

import dataclasses

from conversational_commerce.engine.moves import templates
from conversational_commerce.reply import Template

from .helpers import CTX, engine, message


def test_the_composed_reply_names_the_template_of_each_part():
    turn_engine, _ = engine()
    result = turn_engine.turn(CTX, message("m1", "what are your hours?"))
    assert result.reply.template_ids == ("inform.hours",)
    assert result.text == "We are open from 08:00 to 18:00."  # o registro não muda a frase


def test_a_house_template_is_named_by_the_same_id():
    base = templates()["inform.hours"]
    house = Template("inform.hours", "casa-1", "inform", "Abrimos das {opens} às {closes}.", dict(base.slots))
    turn_engine, _ = engine()
    turn_engine = dataclasses.replace(turn_engine, house_templates={"inform.hours": house})
    result = turn_engine.turn(CTX, message("m1", "what are your hours?"))
    assert result.reply.template_ids == ("inform.hours",)
    assert result.text == "Abrimos das 08:00 às 18:00."
