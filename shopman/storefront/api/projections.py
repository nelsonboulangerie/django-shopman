"""JSON helpers for immutable storefront projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

# Tipos que saem como estão. Conferidos por ``type(...) is``, e não por
# ``isinstance``: um ``Enum`` que herda de ``str`` (o ``Availability``) é
# instância de ``str`` e tem de virar o ``.value``, não passar direto.
_PLAIN = frozenset({str, int, float, bool, type(None)})

# Nomes dos campos por classe de dataclass; ``fields()`` refaz a lista a cada
# chamada, e o cardápio converte o mesmo tipo de card centenas de vezes.
_FIELD_NAMES: dict[type, tuple[str, ...]] = {}


def projection_data(value: Any) -> Any:
    """Convert projection dataclasses into JSON-safe primitives.

    O mesmo card do cardápio aparece em ``items`` e de novo em ``featured`` (as
    seções carregam só SKUs) — é o MESMO objeto. A conversão de uma dataclass é
    lembrada por identidade durante esta chamada, e as duas posições recebem o
    mesmo dict. O JSON que sai é byte a byte o de antes: o dict é só serializado
    mais de uma vez. Quem recebe o resultado não deve mutá-lo (ninguém muta; a
    projeção é um selo de leitura).
    """
    return _convert(value, {})


def _convert(value: Any, memo: dict[int, tuple[Any, Any]]) -> Any:
    kind = type(value)
    if kind in _PLAIN:
        return value
    if kind is dict:
        return {str(key): _convert(item, memo) for key, item in value.items()}
    if kind is tuple or kind is list:
        return [_convert(item, memo) for item in value]
    if is_dataclass(value):
        key = id(value)
        hit = memo.get(key)
        if hit is not None:
            return hit[1]
        if isinstance(value, type):
            names = tuple(field.name for field in fields(value))
        else:
            names = _FIELD_NAMES.get(kind)
            if names is None:
                names = _FIELD_NAMES[kind] = tuple(field.name for field in fields(value))
        converted = {name: _convert(getattr(value, name), memo) for name in names}
        # O memo guarda a própria dataclass ao lado do resultado: viva até o fim
        # da chamada, o ``id`` dela não pode ser reaproveitado por outro objeto.
        memo[key] = (value, converted)
        return converted
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _convert(item, memo) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_convert(item, memo) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_convert(item, memo) for item in value]
    return value
