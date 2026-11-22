"""A voz da casa no turno (spec 06, seção 2): o adaptador troca os moldes genéricos pelos dele.

O ``Engine`` recebia os ``formatters`` da casa, mas não os moldes: a resposta saía sempre na
frase genérica do pacote. Agora o adaptador passa ``house_templates`` pelo ``template_id``; a
frase muda, o movimento e os espaços (nome, lastro e faceta) ficam, e o que não for trocado
segue com o do pacote.
"""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.engine.moves import templates
from conversational_commerce.reply import SlotSpec, Template

from .helpers import CTX, engine, message

HOURS = templates()["inform.hours"]
CASA = Template("inform.hours", "casa-1", "inform", "Abrimos das {opens} às {closes}.", dict(HOURS.slots))


def _with(*house):
    turn_engine, world = engine()
    return dataclasses.replace(turn_engine, house_templates={t.template_id: t for t in house}), world


def test_the_house_template_is_what_the_customer_reads():
    turn_engine, _ = _with(CASA)
    result = turn_engine.turn(CTX, message("m1", "what are your hours?"))
    assert result.outcome == "answered"
    assert result.text == "Abrimos das 08:00 às 18:00."


def test_without_house_templates_the_package_phrase_stays():
    turn_engine, _ = engine()
    assert turn_engine.turn(CTX, message("m1", "what are your hours?")).text == "We are open from 08:00 to 18:00."


def test_a_house_template_without_a_package_pair_fails_loud():
    with pytest.raises(TypeError, match="sem par no pacote"):
        _with(Template("inform.weather", "1", "inform", "Hoje faz sol.", {}))


def test_the_house_cannot_move_a_template_to_another_move():
    with pytest.raises(TypeError, match="movimento"):
        _with(Template("inform.hours", "1", "acknowledge", "Abrimos das {opens} às {closes}.", dict(HOURS.slots)))


def test_the_house_cannot_change_what_fills_a_slot():
    loose = {**HOURS.slots, "opens": SlotSpec(("fact", "receipt:success"), "opens")}
    with pytest.raises(TypeError, match="espaços"):
        _with(Template("inform.hours", "1", "inform", "Abrimos das {opens} às {closes}.", loose))
    with pytest.raises(TypeError, match="espaços"):
        _with(Template("inform.hours", "1", "inform", "Abrimos às {opens}.", {"opens": HOURS.slots["opens"]}))
