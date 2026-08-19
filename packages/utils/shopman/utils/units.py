"""A física da unidade — tabela fechada, em código.

Este módulo responde uma pergunta só: **quanto vale uma unidade em outra, quando
a resposta é definicional**. Quilo vira grama, litro vira mililitro, dúzia vira
unidade — e mais nada. É a conversão do tipo 1 da
``docs/decisions/adr-024-material-unit-base-and-purchase.md``:

- **fechada em código**, porque constante de física não é configuração. Se
  morasse no banco, alguém salvaria "1 kg = 900 g" e o sistema obedeceria calado;
- **sem tela, sem migração, sem dono editorial**;
- **recusa em vez de adivinhar** (regra R4): ``kg`` → ``un`` levanta
  :class:`UnitError`, porque não existe caminho definicional entre massa e
  contagem. A ponte entre os dois é conversão **declarada por insumo** — mora no
  Buyman (``MaterialConversion``), não aqui.

As três dimensões e o vocabulário canônico:

======== ============================ ==================
Dimensão Unidades                     Menor unidade
======== ============================ ==================
massa    ``mg`` · ``g`` · ``kg``      ``mg``
volume   ``ml`` · ``l``               ``ml``
contagem ``un`` · ``dz``              ``un``
======== ============================ ==================

Os fatores são **inteiros na menor unidade da dimensão**, de propósito: toda
conversão vira uma divisão exata de inteiros em :class:`~decimal.Decimal`, sem
``0.001`` flutuando no meio do caminho. O arredondamento acontece só na ponta em
que o número vira dinheiro guardado (ver :mod:`shopman.utils.monetary`).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from shopman.utils.exceptions import BaseError

#: Dimensões físicas conhecidas.
MASS = "mass"
VOLUME = "volume"
COUNT = "count"

#: Unidade canônica → (dimensão, fator para a menor unidade da dimensão).
_UNITS: dict[str, tuple[str, Decimal]] = {
    "mg": (MASS, Decimal(1)),
    "g": (MASS, Decimal(1_000)),
    "kg": (MASS, Decimal(1_000_000)),
    "ml": (VOLUME, Decimal(1)),
    "l": (VOLUME, Decimal(1_000)),
    "un": (COUNT, Decimal(1)),
    "dz": (COUNT, Decimal(12)),
}

#: Apelidos que o sistema já aceitava (vinham da ficha técnica do Craftsman).
#: Apelido é grafia, não física: só aponta para uma unidade canônica de cima.
_ALIASES: dict[str, str] = {
    "un.": "un",
    "unit": "un",
    "units": "un",
    "lt": "l",
    "lts": "l",
    "liter": "l",
    "liters": "l",
    "litro": "l",
    "litros": "l",
}

_DIMENSION_LABELS = {MASS: "massa", VOLUME: "volume", COUNT: "contagem"}


class UnitError(BaseError):
    """Unidade desconhecida, ou par sem caminho definicional entre as duas."""

    _default_messages = {
        "unknown_unit": "Unidade desconhecida.",
        "incompatible_units": "Não existe conversão exata entre estas unidades.",
        "invalid_quantity": "Quantidade inválida para conversão.",
    }


def known_units() -> tuple[str, ...]:
    """Vocabulário canônico, em ordem estável — serve às mensagens de erro."""
    return tuple(_UNITS)


def normalize(unit: str | None) -> str:
    """Devolve a grafia canônica da unidade (``"L"`` → ``"l"``, ``"un."`` → ``"un"``).

    Comparação sem sensibilidade a maiúsculas. **Não levanta**: unidade que não
    reconhece volta como veio (só sem espaços em volta), porque quem decide se
    recusa é o chamador — a validação da ficha, o cadastro de custo, a tela.
    Para saber se reconheceu, use :func:`is_known`.
    """
    raw = str(unit or "").strip()
    if not raw:
        return ""
    if raw in _UNITS:
        return raw
    lowered = raw.lower()
    if lowered in _UNITS:
        return lowered
    return _ALIASES.get(raw, _ALIASES.get(lowered, raw))


def is_known(unit: str | None) -> bool:
    """``True`` quando a unidade está na tabela fechada."""
    return normalize(unit) in _UNITS


def dimension(unit: str | None) -> str:
    """Dimensão da unidade (:data:`MASS`, :data:`VOLUME`, :data:`COUNT`).

    Devolve ``""`` para unidade desconhecida — é a pergunta "isso é peso?" que
    o chamador faz antes de escolher o caminho, e ela não deve explodir.
    """
    entry = _UNITS.get(normalize(unit))
    return entry[0] if entry else ""


def same_dimension(first: str | None, second: str | None) -> bool:
    """``True`` quando as duas unidades são conhecidas e da mesma dimensão."""
    left = dimension(first)
    return bool(left) and left == dimension(second)


def convert(quantity, from_unit: str | None, to_unit: str | None) -> Decimal:
    """Converte ``quantity`` de ``from_unit`` para ``to_unit``, em ``Decimal``.

    Levanta :class:`UnitError` quando alguma das unidades é desconhecida ou
    quando não existe caminho definicional entre as duas (massa → contagem, por
    exemplo). Nunca devolve palpite: é a regra R4 da ADR-024 em uma linha.
    """
    source = normalize(from_unit)
    target = normalize(to_unit)
    for original, canonical in ((from_unit, source), (to_unit, target)):
        if canonical not in _UNITS:
            offender = str(original or "").strip()
            raise UnitError(
                "unknown_unit",
                f"Unidade desconhecida: '{offender}'. "
                f"Conhecidas: {', '.join(known_units())}.",
                unit=offender,
            )

    source_dimension, source_factor = _UNITS[source]
    target_dimension, target_factor = _UNITS[target]
    if source_dimension != target_dimension:
        raise UnitError(
            "incompatible_units",
            f"Não existe conversão exata entre "
            f"'{source}' ({_DIMENSION_LABELS[source_dimension]}) e "
            f"'{target}' ({_DIMENSION_LABELS[target_dimension]}). "
            f"A ponte entre as duas é uma conversão declarada no insumo.",
            from_unit=source,
            to_unit=target,
        )

    value = _as_decimal(quantity)
    if source == target:
        return value
    return value * source_factor / target_factor


def _as_decimal(quantity) -> Decimal:
    if isinstance(quantity, Decimal):
        return quantity
    try:
        return Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise UnitError(
            "invalid_quantity",
            f"Quantidade inválida para conversão: {quantity!r}.",
            quantity=quantity,
        ) from exc
