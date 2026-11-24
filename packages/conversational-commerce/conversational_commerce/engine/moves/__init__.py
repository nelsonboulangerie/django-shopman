"""Movimentos executáveis pelo turno, um módulo por movimento, descobertos pelo nome.

Sem lista central: um WP que acrescenta movimento (F8, F9, F10) cria
``engine/moves/<movimento>.py`` e o laço o encontra. Cada módulo define:

- ``MOVE``: o nome do movimento, igual ao nome do módulo e presente no catálogo (F2);
- ``TEMPLATES``: os moldes de que precisa (F6);
- ``propose(state, need) -> Proposal | None``: a candidata para a necessidade, ou nada;
- ``reply(state, need) -> PartSpec``: a parte da resposta quando escolhido.
"""

from __future__ import annotations

import functools
import importlib.util
import pkgutil
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

from conversational_commerce.catalog import MOVES

REQUIRED = ("MOVE", "TEMPLATES", "propose", "reply")


HERE = Path(__file__).resolve().parent


def _load(name: str) -> ModuleType:
    """Carrega ``engine/moves/<name>.py``, e só dali.

    Não é import de nome livre: o arquivo é do próprio pacote, e o K38 lê todos
    eles pelo AST. A carga recusa qualquer arquivo fora deste diretório.
    """
    qualified = f"{__name__}.{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]
    path = (HERE / f"{name}.py").resolve()
    if path.parent != HERE or not path.is_file():
        raise TypeError(f"movimento fora de engine/moves: {name}")
    spec = importlib.util.spec_from_file_location(qualified, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


@cache
def registry() -> dict[str, ModuleType]:
    found: dict[str, ModuleType] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = _load(info.name)
        missing = [name for name in REQUIRED if not hasattr(module, name)]
        if missing:
            raise TypeError(f"movimento {info.name} sem {missing}")
        if module.MOVE != info.name or module.MOVE not in MOVES:
            raise TypeError(f"movimento {info.name}: MOVE={module.MOVE!r} precisa ser o nome do módulo e do catálogo")
        found[module.MOVE] = module
    return found


def templates() -> dict:
    return {template.template_id: template for module in registry().values() for template in module.TEMPLATES}


@functools.cache
def yes_no_conditions() -> frozenset[str]:
    """As condições que se respondem com sim ou não, declaradas pelos movimentos que as cumprem
    (``ANSWERS_CONDITIONS``). Lidas uma vez: o registro não muda em execução."""
    return frozenset(code for module in registry().values() for code in getattr(module, "ANSWERS_CONDITIONS", ()))
