"""Forma canônica, valor JSON congelado e hash.

Forma canônica (plano, decisão 2c; ``spec/01-contracts.md``):

- JSON com chaves de objeto ordenadas por ponto de código Unicode;
- separadores ``,`` e ``:`` sem espaço; nenhum espaço fora de string;
- UTF-8, sem escapar caractere não ASCII; escapes só os obrigatórios do JSON
  (``\\"``, ``\\\\``, ``\\b``, ``\\f``, ``\\n``, ``\\r``, ``\\t`` e
  ``\\u00XX`` minúsculo para os demais controles abaixo de U+0020);
- **sem número de ponto flutuante** (nem ``NaN``, nem ``Infinity``): dinheiro é
  inteiro na menor unidade, quantidade e probabilidade são decimal em texto;
- inteiro só dentro de ``±(2**53 - 1)``, para ler igual em qualquer linguagem;
- chave de objeto só string.

Hash: ``sha256:`` seguido dos 64 dígitos hexadecimais minúsculos do SHA-256 da
forma canônica.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from typing import Any

from .errors import invalid

MAX_SAFE_INTEGER = 2**53 - 1
HASH_PREFIX = "sha256:"


class FrozenMap(Mapping[str, Any]):
    """Mapa imutável e com hash: o ``dict`` de um registro imutável (N14)."""

    __slots__ = ("_data", "_hash")

    def __init__(self, data: Mapping[str, Any] | None = None):
        object.__setattr__(self, "_data", dict(data or {}))
        object.__setattr__(self, "_hash", None)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("FrozenMap é imutável")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("FrozenMap é imutável")

    def __hash__(self) -> int:
        if self._hash is None:
            object.__setattr__(self, "_hash", hash(frozenset(self._data.items())))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self._data == dict(other.items())
        return NotImplemented

    def __repr__(self) -> str:
        return f"FrozenMap({self._data!r})"


def freeze_json(value: Any, path: tuple[str | int, ...] = ()) -> Any:
    """Valida um valor JSON e o devolve congelado (``dict`` → ``FrozenMap``, lista → tupla).

    Recusa ``float``, inteiro fora da faixa segura, chave não string e qualquer
    tipo que não seja JSON.
    """
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise invalid("inteiro fora da faixa segura ±(2**53 - 1)", *path)
        return value
    if isinstance(value, float):
        raise invalid("número de ponto flutuante não é permitido; use inteiro ou decimal em texto", *path)
    if isinstance(value, Mapping):
        frozen = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise invalid("chave de objeto JSON precisa ser string", *path)
            frozen[key] = freeze_json(item, (*path, key))
        return FrozenMap(frozen)
    if isinstance(value, list | tuple):
        return tuple(freeze_json(item, (*path, index)) for index, item in enumerate(value))
    raise invalid(f"tipo {type(value).__name__} não é valor JSON", *path)


def thaw_json(value: Any) -> Any:
    """O contrário de ``freeze_json``: ``FrozenMap`` → ``dict``, tupla → lista."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [thaw_json(item) for item in value]
    return value


def canonical_bytes(document: Any) -> bytes:
    """A forma canônica de um valor JSON, em bytes UTF-8."""
    plain = thaw_json(freeze_json(document))
    text = json.dumps(plain, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return text.encode("utf-8")


def canonical_text(document: Any) -> str:
    return canonical_bytes(document).decode("utf-8")


def sha256_hash(document: Any) -> str:
    """``sha256:<hex>`` da forma canônica de ``document``."""
    return HASH_PREFIX + hashlib.sha256(canonical_bytes(document)).hexdigest()
