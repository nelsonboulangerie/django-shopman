"""Estado de diálogo e a pergunta no ar (v2 5.7, 6.1; K29).

A pergunta no ar vence por acontecimento, não por relógio. Ela guarda a época de
posse em que foi feita: quando a pessoa devolve a conversa, a pergunta que a
automação tinha deixado no ar deixa de valer (a pessoa disse coisas que o
sistema não viu), e um "sim" depois disso não é lido contra ela.

Convenção da chave em ``ContextSnapshot.dialogue_state``:
``open_question = {question_id, need_id, asked_epoch}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

OPEN_QUESTION = "open_question"


def ask(dialogue_state: Mapping[str, Any], *, question_id: str, need_id: str, epoch: int) -> dict[str, Any]:
    """O estado de diálogo com a pergunta nova no ar (uma por vez, por necessidade)."""
    state = dict(dialogue_state)
    state[OPEN_QUESTION] = {"question_id": question_id, "need_id": need_id, "asked_epoch": epoch}
    return state


def answered(dialogue_state: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(dialogue_state)
    state.pop(OPEN_QUESTION, None)
    return state


def on_conversation_returned(dialogue_state: Mapping[str, Any]) -> dict[str, Any]:
    """A pessoa devolveu a conversa: a pergunta antiga deixa de valer."""
    return answered(dialogue_state)


def answer_refers_to(dialogue_state: Mapping[str, Any], current_epoch: int) -> str | None:
    """A pergunta a que uma resposta curta ("sim") se refere, ou ``None``.

    Só vale a pergunta feita na época de posse atual. Pergunta de época anterior
    nunca recebe resposta, mesmo que alguém tenha esquecido de limpá-la.
    """
    question = dialogue_state.get(OPEN_QUESTION)
    if not question or question.get("asked_epoch") != current_epoch:
        return None
    return question.get("question_id")
