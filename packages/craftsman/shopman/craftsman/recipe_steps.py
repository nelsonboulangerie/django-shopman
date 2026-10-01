"""Etapas de produção: a forma única de ``Recipe.steps`` e ``RecipeVersion.steps``.

Cada etapa é um objeto::

    {"name": "Fermentação", "instructions": "Até dobrar de volume.", "target_seconds": 5400,
     "temperature_celsius": 26, "note": "..."}

``name`` é obrigatório; ``instructions`` (o modo de fazer), ``target_seconds``
(tempo alvo, inteiro maior que zero), ``temperature_celsius`` (temperatura da
etapa em °C, inteira ou com uma casa decimal, preenchida só na receita que
precisa: forno, massa, câmara) e ``note`` (anotação prática) são opcionais e só
ficam gravados quando têm conteúdo.

``normalize_steps`` é o funil: os ``clean()`` das duas tabelas passam por ele,
o ``Recipe.save`` chama ``full_clean`` e o ``RecipeVersion.save`` normaliza as
etapas, então nada chega ao banco em outra forma (nem um backup anterior à
``craftsman/0015`` restaurado pelo cofre). Texto puro na entrada é atalho aceito (``"Mistura"`` vira
``{"name": "Mistura"}``); o que não for texto nem objeto com as chaves acima é
recusado apontando a etapa.

Quem lê ``steps`` hoje: as telas do inventário de receitas (autoria) e o
snapshot da fornada (``_recipe_snapshot.production.steps``), que só copia. Nenhuma
tela de execução lê as etapas: levá-las ao chão de fábrica é decisão à parte.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

#: Chaves que uma etapa pode ter, na ordem em que são gravadas.
STEP_KEYS = ("name", "instructions", "target_seconds", "temperature_celsius", "note")


def _invalid(number: int, message: str) -> ValidationError:
    return ValidationError({"steps": f"Etapa {number}: {message}"})


def _normalize_step(step: Any, number: int) -> dict:
    if isinstance(step, str):
        step = {"name": step}
    if not isinstance(step, dict):
        raise _invalid(number, "precisa ser um texto ou um objeto com nome.")
    unknown = sorted(str(key) for key in step if key not in STEP_KEYS)
    if unknown:
        raise _invalid(number, f"chave desconhecida ({', '.join(unknown)}). Use {', '.join(STEP_KEYS)}.")

    name = step.get("name")
    if not isinstance(name, str) or not name.strip():
        raise _invalid(number, "precisa de um nome.")
    out: dict = {"name": name.strip()}

    instructions = step.get("instructions")
    if instructions is not None:
        if not isinstance(instructions, str):
            raise _invalid(number, "as instruções precisam ser texto.")
        if instructions.strip():
            out["instructions"] = instructions.strip()

    seconds = step.get("target_seconds")
    if seconds is not None:
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise _invalid(number, "o tempo alvo precisa ser um número inteiro de segundos maior que zero.")
        out["target_seconds"] = seconds

    celsius = step.get("temperature_celsius")
    if celsius is not None:
        out["temperature_celsius"] = _celsius(celsius, number)

    note = step.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise _invalid(number, "a anotação precisa ser texto.")
        if note.strip():
            out["note"] = note.strip()
    return out


def _celsius(value: Any, number: int) -> int | float:
    """Temperatura em °C: número inteiro ou com UMA casa decimal (``24`` ou ``24.5``).

    Número, não texto (``"230 °C"`` é recusado, como o tempo alvo). Valor com
    casa decimal zerada vira inteiro (``24.0`` grava ``24``). Mais de uma casa é
    recusado em vez de arredondado em silêncio.
    """
    message = "a temperatura precisa ser um número em °C, inteiro ou com uma casa decimal."
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(number, message)
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        raise _invalid(number, message)
    tenths = Decimal(str(value)) * 10
    if tenths != tenths.to_integral_value():
        raise _invalid(number, message)
    return int(value) if value.is_integer() else value


def normalize_steps(value: Any) -> list[dict]:
    """A lista de etapas na forma única. Levanta ``ValidationError({"steps": ...})``."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValidationError({"steps": "Deve ser uma lista de etapas."})
    return [_normalize_step(step, index + 1) for index, step in enumerate(value)]


def steps_from_names(names: Iterable[str], previous: Iterable[dict] = ()) -> list[dict]:
    """Uma etapa por nome, guardando o que a etapa de MESMO nome já tinha.

    Para editores que só mexem nos nomes (o textarea do Admin, uma linha por
    etapa): renomear, reordenar ou apagar uma linha não pode apagar as
    instruções, o tempo, a temperatura e a anotação das outras. Nome repetido casa com a
    próxima etapa ainda não usada daquele nome.
    """
    pool: dict[str, list[dict]] = {}
    for step in previous or ():
        pool.setdefault(step["name"], []).append(step)
    out: list[dict] = []
    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        matches = pool.get(name)
        out.append(dict(matches.pop(0)) if matches else {"name": name})
    return out
